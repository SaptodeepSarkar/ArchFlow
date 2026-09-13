#!/usr/bin/env python3
"""Compare Moonshine V5 with the recorded v2 hypotheses on one held-out set."""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import soundfile as sf
import torch
from scipy.signal import resample_poly
from transformers import AutoProcessor, MoonshineStreamingForConditionalGeneration

from stt_feedback_loop import score

SR = 16_000


def audio(path):
    samples, rate = sf.read(path, dtype="float32")
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    if rate != SR:
        samples = resample_poly(samples, SR, rate).astype("float32")
    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = ap.parse_args()

    rows = [json.loads(line) for line in args.report.read_text().splitlines() if line.strip()]
    random.Random(20260914).shuffle(rows)
    rows = rows[-100:]
    processor = AutoProcessor.from_pretrained(args.model)
    dtype = torch.float16 if args.device == "cuda" else torch.float32
    model = MoonshineStreamingForConditionalGeneration.from_pretrained(args.model, torch_dtype=dtype).to(args.device)
    model.eval()
    results = []
    total_audio = 0.0
    total_elapsed = 0.0
    with torch.inference_mode():
        for index, row in enumerate(rows):
            samples = audio(row["audio_path"])
            total_audio += len(samples) / SR
            inputs = processor(samples, sampling_rate=SR, return_tensors="pt")
            inputs = {key: value.to(args.device) for key, value in inputs.items()}
            if dtype == torch.float16:
                inputs["input_values"] = inputs["input_values"].to(dtype)
            max_length = max(16, int((inputs["attention_mask"].sum().item() * 6.5 / SR)))
            started = time.perf_counter()
            generated = model.generate(**inputs, max_length=max_length)
            elapsed = time.perf_counter() - started
            total_elapsed += elapsed
            hypothesis = processor.decode(generated[0], skip_special_tokens=True).strip()
            metrics = score(row["reference"], hypothesis)
            results.append({"index": index, "audio_path": row["audio_path"],
                            "reference": row["reference"],
                            "v2_hypothesis": row.get("baseline_hypothesis", row.get("hypothesis", "")),
                            "v5_hypothesis": hypothesis, "v5_seconds": elapsed,
                            **metrics})
            if (index + 1) % 10 == 0:
                print(f"{index + 1}/100", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in results))
    v2 = [score(item["reference"], item["v2_hypothesis"])["wer"] for item in results]
    v5 = [item["wer"] for item in results]
    print(json.dumps({"clips": len(results), "v2_wer": sum(v2) / len(v2),
                      "v5_wer": sum(v5) / len(v5), "audio_seconds": total_audio,
                      "v5_seconds": total_elapsed,
                      "v5_real_time_factor": total_elapsed / max(total_audio, 1e-6),
                      "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
