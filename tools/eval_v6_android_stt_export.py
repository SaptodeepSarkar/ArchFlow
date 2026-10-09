#!/usr/bin/env python3
"""Evaluate a whisper.cpp export against a licensed V6 JSONL slice.

The evaluator deliberately retains reference and hypothesis text only in
process memory. Its optional report has aggregate counts, WER, duration, and
runtime only; it never serializes utterance text, audio, or per-row errors.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import wave
from pathlib import Path


TOKEN = re.compile(r"[\w]+(?:['-][\w]+)?", flags=re.UNICODE)


def normalized_tokens(text: str) -> list[str]:
    return TOKEN.findall(text.casefold())


def edit_counts(reference: list[str], hypothesis: list[str]) -> tuple[int, int, int]:
    """Return substitutions, deletions, insertions without retaining alignment."""
    previous = [(index, 0, 0, index) for index in range(len(hypothesis) + 1)]
    for ref_index, reference_token in enumerate(reference, start=1):
        current = [(ref_index, 0, ref_index, 0)]
        for hyp_index, hypothesis_token in enumerate(hypothesis, start=1):
            substitute = previous[hyp_index - 1]
            delete = previous[hyp_index]
            insert = current[hyp_index - 1]
            mismatch = reference_token != hypothesis_token
            choices = [
                (substitute[0] + mismatch, substitute[1] + mismatch, substitute[2], substitute[3]),
                (delete[0] + 1, delete[1], delete[2] + 1, delete[3]),
                (insert[0] + 1, insert[1], insert[2], insert[3] + 1),
            ]
            current.append(min(choices, key=lambda value: value[0]))
        previous = current
    _, substitutions, deletions, insertions = previous[-1]
    return substitutions, deletions, insertions


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--whisper-cli", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--language", default="en")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    if args.limit <= 0:
        raise SystemExit("--limit must be positive")
    if not args.whisper_cli.is_file() or not args.model.is_file():
        raise SystemExit("whisper-cli or model is unavailable")

    rows = []
    with args.manifest.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
            if len(rows) == args.limit:
                break
    if len(rows) != args.limit:
        raise SystemExit("manifest has fewer rows than the requested frozen slice")

    substitutions = deletions = insertions = reference_words = 0
    duration_seconds = runtime_seconds = 0.0
    failures = 0
    audio_root = args.audio_root.resolve()
    for row in rows:
        reference_path = row.get("audio", {}).get("ref")
        if not isinstance(reference_path, str) or not reference_path:
            raise SystemExit("a frozen-slice audio reference is invalid")
        audio = (audio_root / reference_path).resolve()
        try:
            audio.relative_to(audio_root)
        except ValueError:
            raise SystemExit("a frozen-slice audio reference escapes the audio root")
        if not audio.is_file():
            raise SystemExit("a frozen-slice audio file is missing")
        started = time.monotonic()
        result = subprocess.run(
            [str(args.whisper_cli), "--no-prints", "--no-timestamps", "-m", str(args.model),
             "-f", str(audio), "-l", args.language],
            check=False,
            capture_output=True,
            text=True,
        )
        runtime_seconds += time.monotonic() - started
        duration_seconds += wav_seconds(audio)
        if result.returncode:
            failures += 1
            continue
        reference = normalized_tokens(row["utterance"]["reference_transcript"])
        hypothesis = normalized_tokens(result.stdout)
        sub, delete, insert = edit_counts(reference, hypothesis)
        substitutions += sub
        deletions += delete
        insertions += insert
        reference_words += len(reference)

    errors = substitutions + deletions + insertions
    report = {
        "schema_version": 1,
        "rows_requested": args.limit,
        "rows_decoded": args.limit - failures,
        "decode_failures": failures,
        "reference_words": reference_words,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "normalized_wer_percent": round(100 * errors / max(reference_words, 1), 4),
        "audio_seconds": round(duration_seconds, 3),
        "decode_seconds": round(runtime_seconds, 3),
        "real_time_factor": round(runtime_seconds / max(duration_seconds, 0.001), 5),
        "language": args.language,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
