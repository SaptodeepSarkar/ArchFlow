#!/usr/bin/env python3
"""WER for the V8 STT model: overall and per source, on one split."""

from __future__ import annotations

import argparse
import json
import os
import sys

import torch
from transformers import WhisperForConditionalGeneration, WhisperProcessor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="HF dir (e.g. $OUT/stt/averaged) or hub id")
    parser.add_argument("--data", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--eval-dir", default=None, help="defaults to <data>/../eval")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=200)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    import jiwer

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    eval_dir = args.eval_dir or os.path.join(os.path.dirname(os.path.abspath(args.data)), "eval")
    os.makedirs(eval_dir, exist_ok=True)

    rows = common.stt_split(args.data, args.split)
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        raise SystemExit(f"no rows in {args.data}/stt/{args.split}.jsonl")

    processor = WhisperProcessor.from_pretrained(args.model)
    model = WhisperForConditionalGeneration.from_pretrained(
        args.model, torch_dtype=torch.float32, attn_implementation="sdpa").to(device).eval()
    model.config.use_cache = True

    max_new_tokens = min(args.max_new_tokens, model.config.max_target_positions - 1)
    predictions = []
    with torch.inference_mode():
        for row in rows:
            audio = common.load_wav_16k(common.stt_audio_path(args.data, row))
            features = processor.feature_extractor(
                audio, sampling_rate=16000, return_tensors="pt", padding="max_length"
            ).input_features.to(device)
            tokens = model.generate(features, max_new_tokens=max_new_tokens)
            text = processor.tokenizer.batch_decode(tokens, skip_special_tokens=True)[0].strip()
            predictions.append({"id": row["id"], "source": row.get("source", "unknown"),
                                "reference": row["text"], "prediction": text})

    references = [p["reference"] for p in predictions]
    hypotheses = [p["prediction"] for p in predictions]
    report = {
        "model": args.model,
        "split": args.split,
        "n": len(predictions),
        "wer": float(jiwer.wer(references, hypotheses)),
        "per_source": {},
    }
    for source in sorted({p["source"] for p in predictions}):
        subset = [p for p in predictions if p["source"] == source]
        report["per_source"][source] = {
            "n": len(subset),
            "wer": float(jiwer.wer([p["reference"] for p in subset],
                                   [p["prediction"] for p in subset])),
        }

    common.write_json(os.path.join(eval_dir, "stt.json"), report)
    with open(os.path.join(eval_dir, "stt_predictions.jsonl"), "w") as f:
        for prediction in predictions:
            f.write(json.dumps(prediction) + "\n")
    print(f"wer={report['wer']:.4f} n={report['n']} -> {eval_dir}/stt.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
