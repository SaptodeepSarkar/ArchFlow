#!/usr/bin/env python3
"""Turn confirmed STT feedback reports into a Whisper training manifest.

Only human-confirmed private references and dataset references are admitted.
The model hypothesis is retained as audit metadata, never used as a label.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--min-reward", type=float, default=-1.0)
    args = parser.parse_args()

    rows = []
    seen = set()
    malformed = 0
    for report in args.reports:
        with report.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                path = item.get("audio_path")
                text = str(item.get("reference", "")).strip()
                if not item.get("reference_confirmed") or not path or not text:
                    continue
                if float(item.get("reward", -1.0)) < args.min_reward:
                    continue
                key = (str(Path(path).resolve()), text)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "audio_path": str(Path(path).resolve()),
                    "text": text,
                    "source": item.get("dataset", "private_feedback"),
                    "feedback_reward": item.get("reward"),
                    "baseline_hypothesis": item.get("hypothesis", ""),
                })

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    suffix = f"; skipped malformed lines={malformed}" if malformed else ""
    print(f"wrote {len(rows)} confirmed rows -> {args.out}{suffix}")


if __name__ == "__main__":
    main()
