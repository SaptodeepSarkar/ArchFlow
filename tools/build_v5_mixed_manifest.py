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
    ap.add_argument("--hard-threshold", type=float, default=0.8)
    ap.add_argument("--hard-repeat", type=int, default=0,
                    help="extra copies for confirmed rows at or below threshold")
    args = ap.parse_args()

    feedback = load(args.feedback)
    random.Random(SEED).shuffle(feedback)
    feedback_train = feedback[:-100]
    public = load(args.public)
    seen: set[str] = set()
    merged: list[dict] = []
    extra_hard = 0
    # Prefer confirmed feedback metadata when the same public clip appears in
    # both sources; this preserves reward/protected-term fields for weighting.
    for row in feedback_train + public:
        audio = Path(row["audio_path"])
        path = str((args.base_dir / audio).resolve() if not audio.is_absolute() else audio.resolve())
        if path in seen:
            continue
        seen.add(path)
        normalized = {**row, "audio_path": path}
        merged.append(normalized)
        if args.hard_repeat and "feedback_reward" in row and row["feedback_reward"] <= args.hard_threshold:
            merged.extend(normalized.copy() for _ in range(args.hard_repeat))
            extra_hard += args.hard_repeat
    random.Random(SEED).shuffle(merged)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in merged))
    base_rows = len(merged) - extra_hard
    print(f"rows={len(merged)} base_rows={base_rows} public={len(public)} "
          f"feedback_train={len(feedback_train)} deduped={len(public)+len(feedback_train)-base_rows} "
          f"extra_hard={extra_hard}")


if __name__ == "__main__":
    main()
