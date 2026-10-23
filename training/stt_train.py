#!/usr/bin/env python3
"""V8 STT: full fine-tune of whisper-large-v3-turbo on ~60 h of clips.

fp32 master weights + fp16 autocast + GradScaler (the T4 has no bf16 and fp16
master weights make GradScaler refuse), 8-bit AdamW, gradient checkpointing,
SDPA, the bottom 8 encoder layers frozen for the first 30% of steps, WSD 5/75/20.
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time

import numpy as np
import torch
from transformers import WhisperForConditionalGeneration, WhisperProcessor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()
    common.add_common_args(parser, "VAANI_STT_MODEL")
    args = parser.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    args.config = args.config or os.path.join(here, "configs", "stt.json")
    if args.smoke:
        args.eval_every = args.eval_every or 20
        args.save_every = args.save_every or 10
        args.eval_limit = args.eval_limit or 8
        args.max_steps = args.max_steps or 20
    args.overrides = {
        "data_dir": args.data or common.env_default("VAANI_DATA_DIR", None),
        "out_dir": args.out or common.env_default("VAANI_OUT_DIR", None),
        "model": args.model or common.env_default("VAANI_STT_MODEL", None),
        "max_steps": args.max_steps,
        "session_limit_min": args.session_limit_min,
        "eval_every": args.eval_every,
        "save_every": args.save_every,
        "eval_limit": args.eval_limit,
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "lr": args.lr,
    }
    return args


def apply_freeze(model, layers, frozen):
    for layer in model.model.encoder.layers[:layers]:
        for param in layer.parameters():
            param.requires_grad = not frozen


def batch_tensors(processor, rows, order, pos, size, data_dir, max_target_tokens):
    indices = [order[(pos + i) % len(rows)] for i in range(size)]
    audios = [common.load_wav_16k(common.stt_audio_path(data_dir, rows[i])) for i in indices]
    features = processor.feature_extractor(
        audios, sampling_rate=16000, return_tensors="pt", padding="max_length"
    ).input_features
    labels = processor.tokenizer(
        [rows[i]["text"] for i in indices], return_tensors="pt", padding=True,
        truncation=True, max_length=max_target_tokens,
    ).input_ids
    labels[labels == processor.tokenizer.pad_token_id] = -100
    return features, labels


@torch.inference_mode()
def eval_wer(model, processor, rows, data_dir, limit, device, max_new_tokens):
    import jiwer

    model.eval()
    model.config.use_cache = True   # generation is no_grad; training turns it off again
    max_new_tokens = min(max_new_tokens, model.config.max_target_positions - 1)
    references, hypotheses = [], []
    for row in rows[:limit]:
        audio = common.load_wav_16k(common.stt_audio_path(data_dir, row))
        features = processor.feature_extractor(
            audio, sampling_rate=16000, return_tensors="pt", padding="max_length"
        ).input_features.to(device)
        tokens = model.generate(features, max_new_tokens=max_new_tokens)
        text = processor.tokenizer.batch_decode(tokens, skip_special_tokens=True)[0].strip()
        references.append(row["text"])
        hypotheses.append(text)
    model.config.use_cache = False
    model.train()
    if not references:
        return None
    return float(jiwer.wer(references, hypotheses))


def main():
    args = parse_args()
    cfg = common.load_config(args.config, args.overrides)
    if not cfg.get("out_dir") or not cfg.get("data_dir"):
        raise SystemExit("out_dir and data_dir are required (env or --out/--data)")
    stage = "stt"
    stage_root = os.path.join(cfg["out_dir"], stage)
    os.makedirs(stage_root, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        print("[warn] no CUDA: running the CPU smoke path (fp32, no autocast)", flush=True)
    torch.manual_seed(cfg["seed"])
    np.random.seed(cfg["seed"])

    rows = common.stt_split(cfg["data_dir"], args.split)
    dev = common.stt_split(cfg["data_dir"], cfg["eval_split"])
    if not rows or not dev:
        raise SystemExit(f"no rows: {cfg['data_dir']}/stt/{{{args.split},{cfg['eval_split']}}}.jsonl")

    processor = WhisperProcessor.from_pretrained(cfg["model"])
    if processor.tokenizer.pad_token_id is None:
        processor.tokenizer.pad_token = processor.tokenizer.eos_token
    model = WhisperForConditionalGeneration.from_pretrained(
        cfg["model"], torch_dtype=torch.float32, attn_implementation="sdpa"
    ).to(device)
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.train()

    optimizer = common.make_optimizer(model.parameters(), cfg["lr"], cfg["weight_decay"])
    scaler = torch.amp.GradScaler("cuda", enabled=(device == "cuda"))

    steps_per_epoch = max(1, (len(rows) // cfg["batch_size"]) // cfg["grad_accum"])
    total_steps = cfg["epochs"] * steps_per_epoch
    if cfg.get("max_steps"):
        total_steps = min(total_steps, int(cfg["max_steps"]))
    freeze_layers = int(cfg.get("freeze_encoder_layers", 0))
    freeze_until = int(cfg.get("freeze_fraction", 0.0) * total_steps)

    # --- resume -------------------------------------------------------------
    start_step = 0
    best = None
    checkpoints = common.list_checkpoints(stage_root)
    scored = [c["meta"]["metric"] for c in checkpoints
              if isinstance(c["meta"].get("metric"), (int, float))]
    best = min(scored) if scored else None
    resumable = common.stage_status(common.read_state(cfg["out_dir"]), stage) in ("running", "resumable")
    if common.resume_enabled(args) and resumable and checkpoints:
        last = checkpoints[-1]
        model.load_state_dict(torch.load(os.path.join(last["dir"], "model.pt"), map_location=device))
        blob = torch.load(os.path.join(last["dir"], "optimizer.pt"), map_location=device)
        optimizer.load_state_dict(blob["optimizer"])
        if "grad_scaler" in blob:
            scaler.load_state_dict(blob["grad_scaler"])
        start_step = last["step"]
        print(f"resumed from step {start_step} ({last['dir']})", flush=True)
    elif checkpoints:
        print(f"fresh start; keeping {len(checkpoints)} old checkpoint(s) for pruning", flush=True)

    common.write_state(cfg["out_dir"], stage=stage, status="running", step=start_step,
                       epoch=start_step // steps_per_epoch, best=best)

    hb = common.Heartbeat(stage)
    hb.update(step=start_step)
    t0 = time.time()
    order, current_epoch, frozen = [], -1, None
    loss_value = 0.0
    lr = cfg["lr"]

    with hb:
        for step in range(start_step, total_steps):
            epoch = step // steps_per_epoch
            if common.session_limit_reached(t0, cfg.get("session_limit_min")):
                common.save_checkpoint(stage_root, step, model, optimizer,
                                       {"epoch": epoch, "metric": best, "metric_name": "wer"},
                                       scaler)
                common.prune_checkpoints(stage_root, keep_last=1, keep_best=3)
                common.write_state(cfg["out_dir"], stage=stage, status="resumable",
                                   step=step, epoch=epoch, best=best)
                print(f"SESSION LIMIT: saved step {step}, resumable", flush=True)
                return 0

            if epoch != current_epoch:
                current_epoch = epoch
                generator = torch.Generator().manual_seed(cfg["seed"] + epoch)
                order = torch.randperm(len(rows), generator=generator).tolist()

            should_freeze = step < freeze_until and freeze_layers > 0
            if should_freeze != frozen:
                apply_freeze(model, freeze_layers, should_freeze)
                frozen = should_freeze
                print(f"step {step}: encoder bottom {freeze_layers} layers "
                      f"{'frozen' if should_freeze else 'unfrozen'}", flush=True)

            lr = cfg["lr"] * common.wsd_factor(step, total_steps, cfg["warmup"], cfg["stable"],
                                               cfg["decay"], cfg.get("min_lr_ratio", 0.0))
            common.set_lr(optimizer, lr)
            optimizer.zero_grad(set_to_none=True)
            # shortcut: a short tail wraps to the start of the same epoch (~<32 clips), fine for 66k
            pos = (step % steps_per_epoch) * cfg["grad_accum"] * cfg["batch_size"]
            loss_value = 0.0
            for _ in range(cfg["grad_accum"]):
                features, labels = batch_tensors(processor, rows, order, pos, cfg["batch_size"],
                                                 cfg["data_dir"], cfg["max_target_tokens"])
                with torch.autocast("cuda", dtype=torch.float16, enabled=(device == "cuda")):
                    loss = model(input_features=features.to(device), labels=labels.to(device)).loss
                scaler.scale(loss / cfg["grad_accum"]).backward()
                loss_value += float(loss.detach())
                pos += cfg["batch_size"]

            scaler.unscale_(optimizer)
            trainable = [p for p in model.parameters() if p.requires_grad]
            grad_norm = torch.nn.utils.clip_grad_norm_(trainable, cfg["max_grad_norm"])
            if not torch.isfinite(grad_norm):
                print(f"step {step}: non-finite grad norm, skipped", flush=True)
                scaler.update()
                continue
            scaler.step(optimizer)
            scaler.update()

            hb.update(step=step + 1, loss=loss_value, lr=lr, mem=common.gpu_mem_gb())
            if (step + 1) % cfg["log_every"] == 0:
                print(f"STEP {step + 1} loss={loss_value:.4f} lr={lr:.3g} "
                      f"mem={common.gpu_mem_gb():.2f}GB", flush=True)

            done = step + 1
            if done % cfg["eval_every"] == 0 or done == total_steps:
                wer = eval_wer(model, processor, dev, cfg["data_dir"], cfg["eval_limit"],
                               device, cfg["max_new_tokens"])
                if wer is not None and (best is None or wer < best):
                    best = wer
                print(f"EVAL step={done} wer={wer}", flush=True)
                common.save_checkpoint(stage_root, done, model, optimizer,
                                       {"epoch": epoch, "metric": wer, "metric_name": "wer"},
                                       scaler)
                common.prune_checkpoints(stage_root, keep_last=1, keep_best=3)
                common.write_state(cfg["out_dir"], stage=stage, status="running",
                                   step=done, epoch=epoch, best=best)
            elif done % cfg["save_every"] == 0:
                common.save_checkpoint(stage_root, done, model, optimizer,
                                       {"epoch": epoch, "metric": None}, scaler)
                common.prune_checkpoints(stage_root, keep_last=1, keep_best=3)
                common.write_state(cfg["out_dir"], stage=stage, status="running",
                                   step=done, epoch=epoch, best=best)

    # --- average the top-3 checkpoints, then hand an HF dir to the exporters ---
    del optimizer, model
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()
    averaged_dir = os.path.join(stage_root, "averaged")
    averaged, source_steps = common.average_top_checkpoints(stage_root, lower_is_better=True)
    if averaged is not None:
        final = WhisperForConditionalGeneration.from_pretrained(
            cfg["model"], torch_dtype=torch.float32, attn_implementation="sdpa")
        final.load_state_dict(averaged)
        final.save_pretrained(averaged_dir)
        processor.save_pretrained(averaged_dir)
        common.write_json(os.path.join(averaged_dir, "average.json"),
                          {"source_steps": source_steps, "metric_name": "wer", "best": best})
        print(f"wrote averaged model -> {averaged_dir}", flush=True)

    common.write_state(cfg["out_dir"], stage=stage, status="done", step=total_steps,
                       epoch=total_steps // steps_per_epoch, best=best)
    print(f"DONE stt steps={total_steps} best_wer={best}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
