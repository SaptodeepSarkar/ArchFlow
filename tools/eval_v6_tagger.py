#!/usr/bin/env python3
"""Evaluate a saved V6 tagger on an independent schema-compatible JSONL set."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from train_v6_edit_tagger import BiGRUTagger, CausalConvTagger, Tagger, evaluate, load


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--min-available-mb", type=int, default=4096)
    ap.add_argument("--max-rss-mb", type=int, default=1024)
    args = ap.parse_args()
    config = json.loads((args.model_dir / "config.json").read_text())
    model_cls = {"hashed": Tagger, "bigru": BiGRUTagger, "conv": CausalConvTagger}[config.get("model", "hashed")]
    model = model_cls(hidden=int(config.get("hidden", 96)))
    model.load_state_dict(torch.load(args.model_dir / "model.pt", map_location="cpu", weights_only=True))
    model.eval(); torch.set_num_threads(max(1, min(args.threads, 2))); torch.set_num_interop_threads(1)
    rows = load([args.data])
    results, metrics = evaluate(model, rows, int(config["max_len"]), 16, args.min_available_mb, args.max_rss_mb, "challenge")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results))
    print(json.dumps({"model": config.get("model", "hashed"), "metrics": metrics, "out": str(args.out)}))


if __name__ == "__main__":
    main()
