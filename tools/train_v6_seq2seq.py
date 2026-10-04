#!/usr/bin/env python3
"""Train the V6 constrained copy-biased formatter on approved foundation rows.

The runtime protocol is fixed tokens plus the current raw utterance; no natural-
language system prompt is required.  Only the clean target contributes loss.
"""
from __future__ import annotations
import argparse, hashlib, json, platform, sys
import re
from pathlib import Path
import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
from torch.utils.data import Dataset
import peft
import transformers
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training/cleanup-llm/scripts"))
from formatter_protocol import IN_TAG, OUT_TAG, initialize_v6_token_embeddings
from render_v6_edit_plan import render


def source_text(row):
    source = row.get("source")
    if isinstance(source, dict):
        source = source.get("raw_stt")
    if not isinstance(source, str):
        utterance = row.get("utterance", {})
        source = utterance.get("raw_stt") if isinstance(utterance, dict) else None
    return source.strip() if isinstance(source, str) else ""


def unrequested_list_structure(source, target):
    """Return True when multiline structure lacks a spoken formatting cue."""
    if "\n" not in target:
        return False
    request = re.search(
        r"\b(?:please\s+list|list\s+(?:these|the|my)\b|"
        r"(?:make|create|format|give\s+me|write)\s+(?:this\s+as\s+)?"
        r"(?:a\s+)?(?:(?:shopping|bullet|numbered|unordered|ordered)\s+)?"
        r"(?:list|bullet\s+points?|numbered\s+steps)|"
        r"turn\s+(?:this|these|it)\s+into\s+(?:a\s+)?list|"
        r"continue\s+(?:the\s+)?list|add\s+(?:this\s+)?to\s+(?:the\s+)?list)\b",
        source, re.I,
    )
    requested_layout = re.search(
        r"\b(?:make|create|format|add|write|use|put|turn)\b.{0,48}\b"
        r"(?:heading|title|table|paragraphs?|line\s+breaks?|new\s+lines?|"
        r"quote|bullets?|numbered\s+steps)\b|"
        r"\bturn\s+(?:this|these|it)\s+into\s+(?:a\s+)?"
        r"(?:table|paragraphs?|bullets?)\b",
        source, re.I,
    )
    ordinals = re.findall(r"\b(?:first|second|third|fourth|fifth)\b", source, re.I)
    ordinal_sequence = len(ordinals) >= 2
    return not (request or requested_layout or ordinal_sequence)


def read_excluded_sources(paths):
    excluded = set()
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                source = source_text(json.loads(line))
                if source:
                    excluded.add(source.casefold())
    return excluded


def read_rows(paths, counts=None, excluded_sources=None):
    rows = []
    counts = counts if counts is not None else {}
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            source = source_text(row)
            if excluded_sources and source.casefold() in excluded_sources:
                counts["rejected_heldout_source"] = counts.get("rejected_heldout_source", 0) + 1
                continue
            annotation = row.get("annotation", {})
            status = annotation.get("review_status") if isinstance(annotation, dict) else None
            utterance = row.get("utterance")
            if status in {"approved", "automated_validated"} and isinstance(utterance, dict):
                source = utterance.get("raw_stt")
                target = utterance.get("clean_target")
                source_record = row.get("source")
                origin = (source_record.get("type")
                          if isinstance(source_record, dict) else None)
                route = (f"real_derived_{status}" if origin == "real_derived"
                         else f"foundation_{status}")
            else:
                metadata = row.get("metadata", {})
                origin = metadata.get("source") if isinstance(metadata, dict) else None
                if origin not in {"generated-template", "hard-replay-generated"}:
                    counts["rejected_schema_or_provenance"] = counts.get("rejected_schema_or_provenance", 0) + 1
                    continue
                source, target = row.get("source"), row.get("target_text")
                if not isinstance(source, str) or not isinstance(target, str):
                    counts["rejected_schema_or_provenance"] = counts.get("rejected_schema_or_provenance", 0) + 1
                    continue
                plan = {key: row[key] for key in (
                    "source_tokens", "token_labels", "punctuation_after", "structure",
                    "speech_act", "emoji_intent",
                ) if key in row}
                try:
                    renderer_match = render(plan) == target
                except (KeyError, TypeError, ValueError):
                    renderer_match = False
                if not renderer_match:
                    counts["rejected_renderer_mismatch"] = counts.get("rejected_renderer_mismatch", 0) + 1
                    continue
                route = str(origin)
            if not isinstance(source, str) or not isinstance(target, str) or not source.strip() or not target.strip():
                counts["rejected_empty_text"] = counts.get("rejected_empty_text", 0) + 1
                continue
            if unrequested_list_structure(source, target):
                counts["rejected_unrequested_list"] = counts.get("rejected_unrequested_list", 0) + 1
                continue
            rows.append({"source": source.strip(), "target": target.strip()})
            counts[route] = counts.get(route, 0) + 1
    return rows


def encode_rows(rows, tokenizer, max_length):
    encoded = []
    for row in rows:
        prefix = f"{IN_TAG}\n{row['source']}\n{OUT_TAG}\n"
        prefix_ids = tokenizer(prefix, truncation=True, max_length=max_length)["input_ids"]
        item = tokenizer(prefix + row["target"] + tokenizer.eos_token,
                         truncation=True, max_length=max_length)
        labels = list(item["input_ids"])
        labels[:min(len(prefix_ids), len(labels))] = [-100] * min(len(prefix_ids), len(labels))
        if not any(label != -100 for label in labels):
            continue
        encoded.append({"input_ids": item["input_ids"],
                        "attention_mask": item["attention_mask"], "labels": labels})
    return encoded


def fingerprint_file(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": digest.hexdigest()}


def input_manifest(groups):
    return {name: [fingerprint_file(path) for path in paths]
            for name, paths in groups.items()}


def append_replay_rows(rows, replay, counts, excluded_sources, replay_factor):
    replay_counts = {}
    replay_rows = read_rows([replay], replay_counts, excluded_sources)
    rows.extend(replay_rows * replay_factor)
    for route, count in replay_counts.items():
        counts[route] = counts.get(route, 0) + count * replay_factor


def model_manifest(path):
    root = Path(path).resolve()
    files = []
    # Hash model/tokenizer/config artifacts for exact lineage without storing
    # any model inputs or generated text in the manifest.
    for item in sorted(root.rglob("*")):
        if item.is_file() and (item.name in {
            "config.json", "generation_config.json", "tokenizer.json",
            "tokenizer_config.json", "special_tokens_map.json",
            "model.safetensors", "pytorch_model.bin",
        } or item.name.startswith("model-") and item.suffix == ".safetensors"
          or item.name.startswith("pytorch_model-") and item.suffix == ".bin"):
            files.append(fingerprint_file(item))
    if not files:
        raise SystemExit(f"no recognized model/tokenizer artifacts under: {root}")
    return {"path": str(root), "files": files}

def argument_parser():
    ap=argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, nargs="+", required=True)
    ap.add_argument("--dev", type=Path, nargs="+", required=True)
    ap.add_argument("--replay", type=Path, action="append", default=[],
                    help="small validated semantic-control files to replay during training")
    ap.add_argument("--replay-factor", type=int, default=1)
    ap.add_argument("--exclude", type=Path, nargs="*", default=[],
                    help="held-out source manifests to exclude from train and dev")
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--resume-from-checkpoint", type=Path,
                    help="resume optimizer/model state from an existing Trainer checkpoint")
    ap.add_argument("--max-length", type=int, default=512)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--eval-steps", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--preflight-only", action="store_true",
                    help="validate/filter/encode inputs and print aggregate metadata; do not train")
    return ap


def main():
    args=argument_parser().parse_args()
    if args.replay_factor < 1:
        raise SystemExit("--replay-factor must be positive")
    if args.steps < 1 or args.eval_steps < 1:
        raise SystemExit("steps and eval-steps must be positive")
    repo_root = Path(__file__).resolve().parents[1]
    out_resolved = args.out.expanduser().resolve()
    if out_resolved == repo_root or repo_root in out_resolved.parents:
        raise SystemExit("model outputs must stay outside the Git worktree")
    if args.resume_from_checkpoint is not None and not args.resume_from_checkpoint.is_dir():
        raise SystemExit("resume checkpoint directory does not exist")
    if args.preflight_only and args.resume_from_checkpoint is not None:
        raise SystemExit("--preflight-only cannot be combined with --resume-from-checkpoint")
    if args.out.exists() and any(args.out.iterdir()) and args.resume_from_checkpoint is None:
        raise SystemExit(f"refusing to overwrite non-empty output directory: {args.out}")
    excluded_sources = read_excluded_sources(args.exclude)
    train_counts = {}
    rows=read_rows(args.train, train_counts, excluded_sources)
    for replay in args.replay:
        append_replay_rows(rows, replay, train_counts, excluded_sources, args.replay_factor)
    dev_counts = {}
    dev_rows = read_rows(args.dev, dev_counts, excluded_sources)
    if not rows or not dev_rows:
        raise SystemExit("training and dev inputs must contain validated V6 rows")
    tok=AutoTokenizer.from_pretrained(args.model)
    added=tok.add_special_tokens({"additional_special_tokens":[IN_TAG,OUT_TAG]})
    if tok.pad_token is None: tok.pad_token=tok.eos_token
    encoded=encode_rows(rows, tok, args.max_length)
    dev_encoded=encode_rows(dev_rows, tok, args.max_length)
    if not encoded or not dev_encoded:
        raise SystemExit("no target tokens remain after encoding/truncation")
    inputs = input_manifest({
        "train": args.train, "dev": args.dev, "replay": args.replay,
        "excluded": args.exclude,
    })
    base = model_manifest(args.model)
    manifest = {
        "schema": "vaani-v6-formatter-run-v1",
        "base_model": base,
        "code": [fingerprint_file(Path(__file__).resolve()),
                 fingerprint_file(Path(__file__).resolve().parents[1]
                                  / "training/cleanup-llm/scripts/formatter_protocol.py"),
                 fingerprint_file(Path(__file__).resolve().parent / "render_v6_edit_plan.py"),
                 fingerprint_file(Path(__file__).resolve().parent / "eval_v6_seq2seq.py"),
                 fingerprint_file(Path(__file__).resolve().parent / "compare_v6_seq2seq.py"),
                 fingerprint_file(Path(__file__).resolve().parent / "v6_eval_aggregate.py"),
                 fingerprint_file(Path(__file__).resolve().parents[1]
                                  / "pipelines/formatter/train-v6-seq2seq.sh")],
        "inputs": inputs,
        "settings": {
            "steps": args.steps, "eval_steps": args.eval_steps,
            "batch_size": args.batch_size, "gradient_accumulation_steps": args.grad_accum,
            "max_length": args.max_length, "replay_factor": args.replay_factor,
            "seed": args.seed, "learning_rate": 1e-4,
            "optimizer": "adamw_torch", "lr_scheduler": "cosine",
            "warmup_steps": min(100, args.steps // 10),
            "weight_decay": 0.0, "max_grad_norm": 1.0,
            "checkpoint_rule": "fixed_final_step",
            "save_strategy": "steps", "save_steps": args.eval_steps,
            "lora": {"rank": 16, "alpha": 32, "dropout": 0.05},
        },
        "software": {"python": platform.python_version(), "torch": torch.__version__,
                     "transformers": transformers.__version__, "peft": peft.__version__},
        "aggregate_counts": {"training_rows_encoded": len(encoded),
                             "dev_rows_encoded": len(dev_encoded),
                             "train_routes_weighted": train_counts,
                             "dev_routes": dev_counts},
    }
    if args.preflight_only:
        print(json.dumps({"preflight": "passed", **manifest}, sort_keys=True), flush=True)
        return
    manifest_path = args.out / "run-manifest.json"
    if args.resume_from_checkpoint is not None:
        if not manifest_path.is_file():
            raise SystemExit("resume requires the original run-manifest.json")
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous != manifest:
            raise SystemExit("resume inputs/settings differ from run-manifest.json")
    elif manifest_path.exists():
        raise SystemExit(f"refusing to overwrite run manifest: {manifest_path}")
    class Encoded(Dataset):
        def __init__(self, items): self.items=items
        def __len__(self): return len(self.items)
        def __getitem__(self, i): return self.items[i]
    ds=Encoded(encoded)
    dev_ds=Encoded(dev_encoded)
    model=AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32)
    if added: model.resize_token_embeddings(len(tok))
    initialize_v6_token_embeddings(model, tok)
    v6_token_ids = [tok.convert_tokens_to_ids(IN_TAG), tok.convert_tokens_to_ids(OUT_TAG)]
    model.config.use_cache=False
    model.enable_input_require_grads()
    model=get_peft_model(model,LoraConfig(r=16,lora_alpha=32,lora_dropout=.05,target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],trainable_token_indices=v6_token_ids,task_type="CAUSAL_LM"))
    def collate(fs):
        return {k:torch.nn.utils.rnn.pad_sequence([torch.tensor(x[k]) for x in fs],batch_first=True,padding_value=(tok.pad_token_id if k=="input_ids" else 0 if k=="attention_mask" else -100)) for k in ("input_ids","attention_mask","labels")}
    args.out.mkdir(parents=True,exist_ok=True)
    training_args=TrainingArguments(
        output_dir=str(args.out),max_steps=args.steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,learning_rate=1e-4,
        warmup_steps=min(100,args.steps//10),lr_scheduler_type="cosine",
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        gradient_checkpointing=True,logging_steps=25,
        eval_strategy="steps",eval_steps=args.eval_steps,
        save_strategy="steps",save_steps=args.eval_steps,
        save_total_limit=2,load_best_model_at_end=False,
        report_to="none",remove_unused_columns=False,
        seed=args.seed, data_seed=args.seed,
    )
    trainer=Trainer(model=model,args=training_args,train_dataset=ds,
                    eval_dataset=dev_ds,data_collator=collate)
    args.out.mkdir(parents=True,exist_ok=True)
    if args.resume_from_checkpoint is None:
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"training_rows":len(encoded),"dev_rows":len(dev_encoded),
                      "routes":train_counts,"dev_routes":dev_counts,
                      "steps":args.steps,"eval_steps":args.eval_steps,
                      "seed":args.seed,
                      "trainable_v6_token_ids":v6_token_ids,
                      "cuda":torch.cuda.is_available()}),flush=True)
    trainer.train(resume_from_checkpoint=(
        str(args.resume_from_checkpoint) if args.resume_from_checkpoint else None
    )); trainer.save_model(str(args.out)); tok.save_pretrained(str(args.out))
    eval_losses = [entry["eval_loss"] for entry in trainer.state.log_history
                   if isinstance(entry.get("eval_loss"), (int, float))]
    print(json.dumps({"saved":str(args.out),"training_rows":len(encoded),
                      "dev_rows":len(dev_encoded),"steps":args.steps,
                      "checkpoint_rule":"fixed_final_step",
                      "minimum_dev_loss_diagnostic":min(eval_losses) if eval_losses else None}),flush=True)
if __name__ == "__main__": main()
