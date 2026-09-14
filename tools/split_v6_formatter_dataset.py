#!/usr/bin/env python3
"""Deterministically split V6 rows into train/dev/frozen-test JSONL files."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def bucket(row: dict, seed: str) -> int:
    group = row.get("metadata", {}).get("base_id", row["id"])
    return int(hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()[:8], 16) % 100

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--input", type=Path, required=True); ap.add_argument("--out", type=Path, required=True); ap.add_argument("--seed", default="v6-split-2026-09-14"); args = ap.parse_args()
    rows = [json.loads(x) for x in args.input.read_text().splitlines() if x.strip()]; groups = {"train": [], "dev": [], "test": []}
    for row in rows:
        b = bucket(row, args.seed); groups["test" if b < 10 else "dev" if b < 20 else "train"].append(row)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, data in groups.items(): (args.out / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data))
    print(json.dumps({k: len(v) for k, v in groups.items()}))

if __name__ == "__main__": main()
