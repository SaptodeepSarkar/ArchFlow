#!/usr/bin/env python3
"""Turn verified formatter mistakes into source-grounded correction SFT rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()
    rows = []
    for line in args.results.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("exact"):
            continue
        # Expected output is reviewed data, never the model's own rewrite.
        target = json.loads(row["expected"])
        item = {
            "input": row["input"],
            "output": json.dumps(target, ensure_ascii=False, separators=(",", ":")),
            "source": "verified:model-error-correction",
        }
        rows.extend([item] * max(1, args.repeat))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(json.dumps({"corrections": len(rows), "out": str(args.out)}))


if __name__ == "__main__":
    main()
