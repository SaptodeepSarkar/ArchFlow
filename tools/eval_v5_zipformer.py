#!/usr/bin/env python3
"""Benchmark an official sherpa-onnx streaming Zipformer on the V5 holdout."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
import wave
import hashlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from stt_feedback_loop import score


def normalize(text: str) -> str:
    import re
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def read_audio(path: str) -> tuple[int, np.ndarray]:
    with wave.open(path, "rb") as wav:
        rate = wav.getframerate()
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
            raise ValueError(f"expected mono 16-bit WAV: {path}")
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    samples = samples.astype(np.float32) / 32768.0
    if rate != 16000:
        target_len = round(len(samples) * 16000 / rate)
        source_x = np.linspace(0.0, 1.0, len(samples), endpoint=False)
        target_x = np.linspace(0.0, 1.0, target_len, endpoint=False)
        samples = np.interp(target_x, source_x, samples).astype(np.float32)
        rate = 16000
    return rate, samples


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--int8", action="store_true")
    args = ap.parse_args()

    import sherpa_onnx

    suffix = ".int8.onnx" if args.int8 else ".onnx"
    prefix = "epoch-99-avg-1"
    if (args.model_dir / f"encoder-{prefix}-chunk-16-left-128{suffix}").exists():
        prefix += "-chunk-16-left-128"
    recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
        tokens=str(args.model_dir / "tokens.txt"),
        encoder=str(args.model_dir / f"encoder-{prefix}{suffix}"),
        decoder=str(args.model_dir / f"decoder-{prefix}{suffix}"),
        joiner=str(args.model_dir / f"joiner-{prefix}{suffix}"),
        num_threads=args.threads,
        sample_rate=16000,
        feature_dim=80,
        decoding_method="greedy_search",
        provider="cpu",
    )
    rows = [json.loads(line) for line in args.report.read_text().splitlines() if line.strip()]
    random.Random(20260914).shuffle(rows)
    rows = rows[-min(100, max(1, args.limit)):]
    results = []
    audio_seconds = elapsed = 0.0
    for index, row in enumerate(rows):
        rate, samples = read_audio(row["audio_path"])
        if rate != 16000:
            raise ValueError(f"holdout audio must be 16 kHz: {rate}")
        started = time.perf_counter()
        stream = recognizer.create_stream()
        for start in range(0, len(samples), 3200):
            stream.accept_waveform(rate, samples[start:start + 3200])
            while recognizer.is_ready(stream):
                recognizer.decode_stream(stream)
        stream.input_finished()
        while recognizer.is_ready(stream):
            recognizer.decode_stream(stream)
        hypothesis = recognizer.get_result(stream).strip()
        seconds = time.perf_counter() - started
        elapsed += seconds
        audio_seconds += len(samples) / rate
        reference = row.get("reference", row.get("text", ""))
        literal = score(reference, hypothesis)
        normalized = score(normalize(reference), normalize(hypothesis))
        # Keep persisted reports free of paths and transcript/audio content.
        results.append({
            "row_id": hashlib.sha256(row["audio_path"].encode()).hexdigest()[:16],
            "reference_words": len(normalize(reference).split()),
            "literal_errors": len(literal["errors"]), "normalized_errors": len(normalized["errors"]),
            "normalized_wer": normalized["wer"], "seconds": seconds,
        })
        if (index + 1) % 10 == 0:
            print(f"{index + 1}/{len(rows)}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results))
    ref_words = sum(row["reference_words"] for row in results)
    errors = sum(row["normalized_errors"] for row in results)
    print(json.dumps({
        "clips": len(results), "errors": errors, "reference_words": ref_words,
        "corpus_normalized_wer": errors / max(ref_words, 1),
        "mean_row_normalized_wer": sum(r["normalized_wer"] for r in results) / len(results),
        "audio_seconds": audio_seconds, "elapsed_seconds": elapsed,
        "real_time_factor": elapsed / max(audio_seconds, 1e-6), "int8": args.int8,
        "out": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
