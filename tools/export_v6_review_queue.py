#!/usr/bin/env python3
"""Export review-only V6 candidate fields; this never approves a row."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    queue = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["annotation"]["review_status"] != "needs_human_review":
            continue
        queue.append({
            "example_id": row["example_id"], "source": row["source"],
            "raw_stt": row["utterance"]["raw_stt"],
            "reference_transcript": row["utterance"]["reference_transcript"],
            "proposed_target": row["utterance"]["clean_target"],
            "labels": row["labels"], "decision": "PENDING", "clean_target": None,
            "reviewer": None, "notes": None,
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in queue), encoding="utf-8")
    print(json.dumps({"pending_review": len(queue), "out": str(args.out)}))


if __name__ == "__main__":
    main()
