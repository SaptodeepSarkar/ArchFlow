#!/usr/bin/env python3
"""Build a public-only mixed manifest without touching the held-out feedback rows.

The output is a temporary training artifact and must stay outside Git. The
feedback split is deterministic and matches the V5 evaluators.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


SEED = 20260914


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--feedback", type=Path, required=True)
    ap.add_argument("--public", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base-dir", type=Path, default=Path.cwd(),
                    help="base for relative audio paths in source manifests")
    args = ap.parse_args()

    feedback = load(args.feedback)
    random.Random(SEED).shuffle(feedback)
    feedback_train = feedback[:-100]
    public = load(args.public)
    seen: set[str] = set()
    merged: list[dict] = []
    # Prefer confirmed feedback metadata when the same public clip appears in
    # both sources; this preserves reward/protected-term fields for weighting.
    for row in feedback_train + public:
        audio = Path(row["audio_path"])
        path = str((args.base_dir / audio).resolve() if not audio.is_absolute() else audio.resolve())
        if path in seen:
            continue
        seen.add(path)
        merged.append({**row, "audio_path": path})
    random.Random(SEED).shuffle(merged)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in merged))
    print(f"rows={len(merged)} public={len(public)} feedback_train={len(feedback_train)} deduped={len(public)+len(feedback_train)-len(merged)}")


if __name__ == "__main__":
    main()
