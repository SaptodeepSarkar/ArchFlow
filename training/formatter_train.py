#!/usr/bin/env python3
"""V8 formatter: full fine-tune of Qwen2.5-1.5B-Instruct on ~20k pairs.

The T4 path that fits: fp16 master weights (no fp32 copy, no GradScaler, which
would refuse fp16 grads), a fixed loss scale of 128 with the same 128x clip,
NaN/Inf steps skipped, 8-bit AdamW, gradient checkpointing, SDPA, WSD.
"""

from __future__ import annotations

import argparse
import gc
import os
import sys
import time

import torch
from transformers import AutoTokenizer, Qwen2ForCausalLM

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()
    common.add_common_args(parser, "VAANI_FMT_MODEL")
    parser.add_argument("--pack", action="store_true",
                        help="pack rows into max_seq_len blocks (off by default)")
    args = parser.parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    args.config = args.config or os.path.join(here, "configs", "formatter.json")
    if args.smoke:
        args.eval_every = args.eval_every or 2
        args.save_every = args.save_every or 1
        args.eval_limit = args.eval_limit or 4
        args.max_steps = args.max_steps or 2
    args.overrides = {
        "data_dir": args.data or common.env_default("VAANI_DATA_DIR", None),
        "out_dir": args.out or common.env_default("VAANI_OUT_DIR", None),
        "model": args.model or common.env_default("VAANI_FMT_MODEL", None),
        "max_steps": args.max_steps,
        "session_limit_min": args.session_limit_min,
        "eval_every": args.eval_every,
        "save_every": args.save_every,
        "eval_limit": args.eval_limit,
        "batch_size": args.batch_size,
        "grad_accum": args.grad_accum,
        "lr": args.lr,
        "pack": True if args.pack else None,
    }
    return args


def encode_row(tokenizer, row, max_seq_len, eos_id):
    """Prompt = chat template up to the assistant turn; loss only on the answer."""
    prompt = tokenizer.apply_chat_template(common.chat_messages(row)[:2], tokenize=False,
                                           add_generation_prompt=True)
    prompt_ids = tokenizer(prompt, add_special_tokens=False).input_ids
    answer_ids = tokenizer(row["output"], add_special_tokens=False).input_ids + [eos_id]
    if len(answer_ids) >= max_seq_len:
        prompt_ids, answer_ids = [], answer_ids[:max_seq_len]
    elif len(prompt_ids) > max_seq_len - len(answer_ids):
        prompt_ids = prompt_ids[-(max_seq_len - len(answer_ids)):]
    return prompt_ids + answer_ids, [-100] * len(prompt_ids) + answer_ids


def collate(encodings, pad_id, device):
    width = max(len(ids) for ids, _ in encodings)
    input_ids, labels, masks = [], [], []
    for ids, target in encodings:
        pad = width - len(ids)
        input_ids.append(ids + [pad_id] * pad)
        labels.append(target + [-100] * pad)
        masks.append([1] * len(ids) + [0] * pad)
    return (torch.tensor(input_ids, device=device), torch.tensor(masks, device=device),
            torch.tensor(labels, device=device))


def pack_epoch(encodings, order, max_len):
    """Greedy fill; a pack holds whole rows so no token crosses a row boundary."""
    packs, ids, labels, segments = [], [], [], []
    for index in order:
        row_ids, row_labels = encodings[index]
        if ids and len(ids) + len(row_ids) > max_len:
            packs.append((ids, labels, segments))
            ids, labels, segments = [], [], []
        ids.extend(row_ids)
        labels.extend(row_labels)
        segments.extend([len(packs)] * len(row_ids))
    if ids:
        packs.append((ids, labels, segments))
    return packs


def collate_packed(packs, pad_id, device, dtype):
    """Block-diagonal causal mask + per-segment position ids: no cross-row attention."""
    width = max(len(pack[0]) for pack in packs)
    rows = len(packs)
    floor = torch.finfo(dtype).min
    input_ids = torch.full((rows, width), pad_id, dtype=torch.long)
    labels = torch.full((rows, width), -100, dtype=torch.long)
    attention = torch.zeros((rows, width), dtype=torch.long)
    position_ids = torch.zeros((rows, width), dtype=torch.long)
    mask = torch.full((rows, 1, width, width), floor, dtype=dtype)
    for row, (ids, target, segments) in enumerate(packs):
        length = len(ids)
        input_ids[row, :length] = torch.tensor(ids)
        labels[row, :length] = torch.tensor(target)
        attention[row, :length] = 1
        position = torch.zeros(length, dtype=torch.long)
        segment = torch.tensor(segments)
        for i in range(1, length):
            position[i] = position[i - 1] + 1 if segment[i] == segment[i - 1] else 0
        position_ids[row, :length] = position
        allowed = (segment[:, None] == segment[None, :]) & torch.tril(torch.ones(length, length, dtype=torch.bool))
        mask[row, 0, :length, :length] = torch.where(allowed, torch.tensor(0.0), torch.tensor(floor))
    return (input_ids.to(device), attention.to(device), mask.to(device),
            position_ids.to(device), labels.to(device))


@torch.inference_mode()
def eval_em(model, tokenizer, rows, limit, max_new_tokens, device):
    model.eval()
    model.config.use_cache = True   # generation is no_grad; training turns it off again
    correct = total = 0
    for row in rows[:limit]:
        prompt = tokenizer.apply_chat_template(common.chat_messages(row)[:2], tokenize=False,
                                               add_generation_prompt=True)
        ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(device)
        generated = model.generate(ids, max_new_tokens=max_new_tokens, do_sample=False,
                                   pad_token_id=tokenizer.pad_token_id)
        text = tokenizer.decode(generated[0][ids.shape[1]:], skip_special_tokens=True).strip()
        correct += int(text == row["output"].strip())
        total += 1
    model.config.use_cache = False
    model.train()
    return (correct / total) if total else None


def main():
    args = parse_args()
    cfg = common.load_config(args.config, args.overrides)
    if not cfg.get("out_dir") or not cfg.get("data_dir"):
        raise SystemExit("out_dir and data_dir are required (env or --out/--data)")
    stage = "formatter"
    stage_root = os.path.join(cfg["out_dir"], stage)
    os.makedirs(stage_root, exist_ok=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    if device == "cpu":
        print("[warn] no CUDA: running the CPU smoke path (fp32, no loss scaling)", flush=True)
    torch.manual_seed(cfg["seed"])

    rows = common.formatter_split(cfg["data_dir"], args.split)
    dev = common.formatter_split(cfg["data_dir"], cfg["eval_split"])
    if not rows or not dev:
        raise SystemExit(f"no rows in {cfg['data_dir']}/formatter")

    tokenizer = AutoTokenizer.from_pretrained(cfg["model"])
    model = Qwen2ForCausalLM.from_pretrained(
        cfg["model"], torch_dtype=dtype, attn_implementation="sdpa"
    ).to(device)
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.train()

    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    encodings = [encode_row(tokenizer, row, cfg["max_seq_len"], tokenizer.eos_token_id) for row in rows]
    optimizer = common.make_optimizer(model.parameters(), cfg["lr"], cfg["weight_decay"])
    pack = bool(cfg.get("pack"))

    def epoch_of(epoch):
        generator = torch.Generator().manual_seed(cfg["seed"] + epoch)
        order = torch.randperm(len(encodings), generator=generator).tolist()
        return pack_epoch(encodings, order, cfg["max_seq_len"]) if pack else order

    epochs_data = epoch_of(0)
    per_epoch = max(1, (len(epochs_data) // cfg["batch_size"]) // cfg["grad_accum"])
    total_steps = cfg["epochs"] * per_epoch
    if cfg.get("max_steps"):
        total_steps = min(total_steps, int(cfg["max_steps"]))
    loss_scale = float(cfg["loss_scale"]) if device == "cuda" else 1.0
    clip_value = cfg["max_grad_norm"] * loss_scale

    start_step = 0
    checkpoints = common.list_checkpoints(stage_root)
    scored = [c["meta"]["metric"] for c in checkpoints
              if isinstance(c["meta"].get("metric"), (int, float))]
    best = max(scored) if scored else None
    resumable = common.stage_status(common.read_state(cfg["out_dir"]), stage) in ("running", "resumable")
    if common.resume_enabled(args) and resumable and checkpoints:
        last = checkpoints[-1]
        model.load_state_dict(torch.load(os.path.join(last["dir"], "model.pt"), map_location=device))
        optimizer.load_state_dict(torch.load(os.path.join(last["dir"], "optimizer.pt"),
                                             map_location=device)["optimizer"])
        start_step = last["step"]
        print(f"resumed from step {start_step} ({last['dir']})", flush=True)

    common.write_state(cfg["out_dir"], stage=stage, status="running", step=start_step,
                       epoch=start_step // per_epoch, best=best)

    hb = common.Heartbeat(stage)
    hb.update(step=start_step)
    t0 = time.time()
    current_epoch, epoch_data = -1, epochs_data
    skipped = 0
    lr = cfg["lr"]

    with hb:
        for step in range(start_step, total_steps):
            epoch = step // per_epoch
            if common.session_limit_reached(t0, cfg.get("session_limit_min")):
                common.save_checkpoint(stage_root, step, model, optimizer,
                                       {"epoch": epoch, "metric": best, "metric_name": "exact_match"})
                common.prune_checkpoints(stage_root, keep_last=1, keep_best=3, lower_is_better=False)
                common.write_state(cfg["out_dir"], stage=stage, status="resumable",
                                   step=step, epoch=epoch, best=best)
                print(f"SESSION LIMIT: saved step {step}, resumable", flush=True)
                return 0
            if epoch != current_epoch:
                current_epoch = epoch
                epoch_data = epochs_data if epoch == 0 else epoch_of(epoch)

            lr = cfg["lr"] * common.wsd_factor(step, total_steps, cfg["warmup"], cfg["stable"],
                                               cfg["decay"], cfg.get("min_lr_ratio", 0.0))
            common.set_lr(optimizer, lr)
            optimizer.zero_grad(set_to_none=True)
            # shortcut: a short tail wraps to the start of the epoch, fine for 20k pairs
            pos = (step % per_epoch) * cfg["grad_accum"] * cfg["batch_size"]
            loss_value = 0.0
            bad = False
            for _ in range(cfg["grad_accum"]):
                if pack:
                    batch = [epoch_data[(pos + i) % len(epoch_data)] for i in range(cfg["batch_size"])]
                    input_ids, attention, mask4, position_ids, labels = collate_packed(
                        batch, pad_id, device, dtype)
                    loss = model(input_ids=input_ids, attention_mask=mask4,
                                 position_ids=position_ids, labels=labels).loss
                else:
                    batch = [encodings[epoch_data[(pos + i) % len(epoch_data)]]
                             for i in range(cfg["batch_size"])]
                    input_ids, attention, labels = collate(batch, pad_id, device)
                    loss = model(input_ids=input_ids, attention_mask=attention, labels=labels).loss
                if not torch.isfinite(loss):
                    bad = True
                    break
                (loss * loss_scale / cfg["grad_accum"]).backward()
                loss_value += float(loss.detach())
                pos += cfg["batch_size"]

            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), clip_value)
            if bad or not torch.isfinite(grad_norm):
                optimizer.zero_grad(set_to_none=True)
                skipped += 1
                print(f"step {step}: non-finite loss/grad, step skipped ({skipped} total)", flush=True)
                hb.update(step=step + 1, lr=lr, mem=common.gpu_mem_gb())
                continue
            optimizer.step()

            hb.update(step=step + 1, loss=loss_value, lr=lr, mem=common.gpu_mem_gb())
            if (step + 1) % cfg["log_every"] == 0:
                print(f"STEP {step + 1} loss={loss_value:.4f} lr={lr:.3g} "
                      f"mem={common.gpu_mem_gb():.2f}GB", flush=True)

            done = step + 1
            if done % cfg["eval_every"] == 0 or done == total_steps:
                em = eval_em(model, tokenizer, dev, cfg["eval_limit"], cfg["max_new_tokens"], device)
                if em is not None and (best is None or em > best):
                    best = em
                print(f"EVAL step={done} em={em}", flush=True)
                common.save_checkpoint(stage_root, done, model, optimizer,
                                       {"epoch": epoch, "metric": em, "metric_name": "exact_match"})
                common.prune_checkpoints(stage_root, keep_last=1, keep_best=3, lower_is_better=False)
                common.write_state(cfg["out_dir"], stage=stage, status="running",
                                   step=done, epoch=epoch, best=best)
            elif done % cfg["save_every"] == 0:
                common.save_checkpoint(stage_root, done, model, optimizer,
                                       {"epoch": epoch, "metric": None})
                common.prune_checkpoints(stage_root, keep_last=1, keep_best=3, lower_is_better=False)
                common.write_state(cfg["out_dir"], stage=stage, status="running",
                                   step=done, epoch=epoch, best=best)

    del optimizer, model
    gc.collect()
    if device == "cuda":
        torch.cuda.empty_cache()
    averaged_dir = os.path.join(stage_root, "averaged")
    averaged, source_steps = common.average_top_checkpoints(stage_root, lower_is_better=False)
    if averaged is not None:
        final = Qwen2ForCausalLM.from_pretrained(cfg["model"], torch_dtype=dtype,
                                                 attn_implementation="sdpa")
        final.load_state_dict({k: v.to(dtype) if v.is_floating_point() else v
                               for k, v in averaged.items()})
        final.save_pretrained(averaged_dir)
        tokenizer.save_pretrained(averaged_dir)
        common.write_json(os.path.join(averaged_dir, "average.json"),
                          {"source_steps": source_steps, "metric_name": "exact_match",
                           "best": best, "skipped_steps": skipped})
        print(f"wrote averaged model -> {averaged_dir}", flush=True)

    common.write_state(cfg["out_dir"], stage=stage, status="done", step=total_steps,
                       epoch=total_steps // per_epoch, best=best)
    print(f"DONE formatter steps={total_steps} best_em={best}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
