#!/usr/bin/env python3
"""Evaluate the existing Whisper/CT2 recognizer on the V5 held-out clips.

This keeps decoding experiments separate from training.  It reports both the
literal score and a conservative word-recognition score so punctuation or
apostrophe formatting does not masquerade as an acoustic improvement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import time
from pathlib import Path

from stt_feedback_loop import score


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9']+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--beam-size", type=int, default=1)
    ap.add_argument("--initial-prompt", default="")
    ap.add_argument("--initial-prompt-file", type=Path)
    ap.add_argument("--hotwords-file", type=Path)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="int8_float16")
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()

    from faster_whisper import WhisperModel

    rows = [json.loads(line) for line in args.report.read_text().splitlines() if line.strip()]
    random.Random(20260914).shuffle(rows)
    rows = rows[-min(100, max(1, args.limit)):]
    model = WhisperModel(str(args.model), device=args.device,
                         compute_type=args.compute_type)
    prompt = args.initial_prompt
    if args.initial_prompt_file:
        prompt = args.initial_prompt_file.read_text()
    hotwords = None
    if args.hotwords_file:
        hotwords = ", ".join(x.strip() for x in args.hotwords_file.read_text().splitlines()
                               if x.strip() and not x.lstrip().startswith("#"))
    results = []
    audio_seconds = 0.0
    elapsed = 0.0
    for index, row in enumerate(rows):
        started = time.perf_counter()
        segments, _ = model.transcribe(
            row["audio_path"], language="en", beam_size=args.beam_size,
            condition_on_previous_text=False,
            initial_prompt=prompt or None,
            hotwords=hotwords,
            vad_filter=False,
        )
        hypothesis = " ".join(s.text.strip() for s in segments).strip()
        seconds = time.perf_counter() - started
        elapsed += seconds
        with __import__("wave").open(row["audio_path"], "rb") as wav:
            audio_seconds += wav.getnframes() / wav.getframerate()
        reference = row.get("reference", row.get("text", ""))
        literal = score(reference, hypothesis)
        normalized = score(normalize(reference), normalize(hypothesis))
        results.append({
            "row_id": hashlib.sha256(row["audio_path"].encode()).hexdigest()[:16],
            "reference_words": len(normalize(reference).split()),
            "literal_errors": len(literal["errors"]),
            "normalized_errors": len(normalized["errors"]),
            "normalized_wer": normalized["wer"],
            "seconds": seconds,
        })
        if (index + 1) % 10 == 0:
            print(f"{index + 1}/100", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in results))
    def mean(key: str) -> float:
        return sum(r[key]["wer"] for r in results) / len(results)
    print(json.dumps({
        "clips": len(results), "beam_size": args.beam_size,
        "literal_mean_row_wer": sum(r["literal_errors"] / max(r["reference_words"], 1) for r in results) / len(results),
        "normalized_mean_row_wer": sum(r["normalized_wer"] for r in results) / len(results),
        "corpus_normalized_wer": sum(r["normalized_errors"] for r in results) / max(sum(r["reference_words"] for r in results), 1),
        "audio_seconds": audio_seconds, "elapsed_seconds": elapsed,
        "real_time_factor": elapsed / max(audio_seconds, 1e-6),
        "out": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
