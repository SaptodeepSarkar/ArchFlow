#!/usr/bin/env python3
"""Convert V5 JSONL audio manifests into Lhotse recording/cut manifests.

This prepares the Indian-English corpus for Icefall without copying audio or
putting private data in the repository. The fixed holdout is excluded by
audio-path hash when supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def holdout_ids(path: Path) -> set[str]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {
        hashlib.sha256(row["audio_path"].encode()).hexdigest()[:16]
        for row in rows
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--holdout", type=Path)
    args = ap.parse_args()

    from lhotse import CutSet, MonoCut, Recording, SupervisionSegment

    excluded = holdout_ids(args.holdout) if args.holdout else set()
    recordings = []
    cuts = []
    skipped = 0
    for line in args.manifest.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        audio = Path(row["audio_path"])
        rid = hashlib.sha256(str(audio).encode()).hexdigest()[:16]
        if rid in excluded:
            skipped += 1
            continue
        recording = Recording.from_file(str(audio), recording_id=f"v5-{rid}")
        supervision = SupervisionSegment(
            id=f"sup-{rid}", recording_id=recording.id, start=0.0,
            duration=recording.duration, text=row["text"],
        )
        recordings.append(recording)
        cuts.append(MonoCut(
            id=f"cut-{rid}", start=0.0, duration=recording.duration,
            channel=0, supervisions=[supervision], recording=recording,
        ))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    CutSet.from_cuts(cuts).to_file(args.out_dir / "cuts.jsonl.gz")
    CutSet.from_cuts(cuts).to_file(args.out_dir / "cuts.jsonl")
    print(json.dumps({"cuts": len(cuts), "holdout_skipped": skipped,
                      "out": str(args.out_dir / "cuts.jsonl.gz")}))


if __name__ == "__main__":
    main()
