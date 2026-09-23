#!/usr/bin/env python3
"""Write leakage-safe V6 v2 splits from approved rows only."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def split_for(group_id: str, seed: str) -> str:
    bucket = int(hashlib.sha256(f"{seed}:{group_id}".encode()).hexdigest()[:8], 16) % 100
    return "test" if bucket < 10 else "dev" if bucket < 20 else "train"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", default="v6-foundation-2026-09-23")
    args = parser.parse_args()
    groups: dict[str, list[dict]] = defaultdict(list)
    for line in args.input.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["annotation"]["review_status"] == "approved":
            groups[row["group_id"]].append(row)
    output = {"train": [], "dev": [], "test": []}
    for group_id, rows in groups.items():
        name = split_for(group_id, args.seed)
        for row in rows:
            row = dict(row)
            row["split"] = name
            output[name].append(row)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in output.items():
        (args.out / f"{name}.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({name: len(rows) for name, rows in output.items()}))


if __name__ == "__main__":
    main()
