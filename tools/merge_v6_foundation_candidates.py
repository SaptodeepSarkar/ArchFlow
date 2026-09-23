#!/usr/bin/env python3
"""Merge V6 v2 manifests while rejecting duplicate IDs and source records."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows, example_ids, source_records = [], set(), set()
    for path in args.inputs:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            example_id = row["example_id"]
            source = row["source"]
            source_key = (source["name"], source["record_id"])
            if example_id in example_ids:
                raise SystemExit(f"duplicate example_id: {example_id}")
            if source_key in source_records:
                raise SystemExit(f"duplicate source record: {source_key}")
            example_ids.add(example_id)
            source_records.add(source_key)
            rows.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "unique_source_records": len(source_records), "out": str(args.out)}))


if __name__ == "__main__":
    main()
