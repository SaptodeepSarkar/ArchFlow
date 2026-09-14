#!/usr/bin/env python3
"""Merge grounded V6 JSONL sources without duplicate source utterances."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--inputs", type=Path, nargs="+", required=True); ap.add_argument("--out", type=Path, required=True); args = ap.parse_args()
    rows = []; seen = set()
    for path in args.inputs:
        for line in path.read_text().splitlines():
            if not line.strip(): continue
            row = json.loads(line); key = row["source"].casefold()
            if key in seen: continue
            seen.add(key); rows.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(json.dumps({"rows": len(rows), "out": str(args.out)}))


if __name__ == "__main__": main()
