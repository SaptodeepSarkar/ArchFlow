#!/usr/bin/env python3
"""Prepare a speaker-disjoint public Indian-English TTS manifest outside Git."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def bucket(speaker: str) -> str:
    # Stable speaker split: no speaker appears in more than one partition.
    value = int(hashlib.sha256(speaker.encode()).hexdigest()[:8], 16) % 10
    return "test" if value == 0 else "valid" if value == 1 else "train"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = []
    for line in args.input.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        speaker = str(row.get("speaker_name") or row.get("client_id") or "unknown")
        text = str(row.get("text", "")).strip()
        audio = Path(row["audio_path"])
        if text and audio.exists() and len(text.split()) >= 2:
            rows.append({"audio_path": str(audio), "text": text, "speaker": speaker})
    speaker_values = {row["speaker"] for row in rows}
    speaker_disjoint = len(speaker_values) > 1
    for row in rows:
        key = row["speaker"] if speaker_disjoint else row["audio_path"]
        row["split"] = bucket(key)
    args.out.mkdir(parents=True, exist_ok=True)
    counts = {}
    speakers = {}
    for row in rows:
        split = row["split"]
        counts[split] = counts.get(split, 0) + 1
        speakers.setdefault(split, set()).add(row["speaker"])
        with (args.out / f"{split}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {"clips": counts, "speakers": {k: len(v) for k, v in speakers.items()},
               "speaker_disjoint": speaker_disjoint, "source": str(args.input)}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
