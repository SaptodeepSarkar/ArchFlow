#!/usr/bin/env python3
"""Combine reviewed source-grounded formatter contracts for the GRPO smoke run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, nargs="+", required=True)
    args = ap.parse_args()
    rows = []
    for path in args.inputs:
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                # Validate the contract before it reaches an RL reward.
                target = json.loads(row["output"])
                if set(target) != {"operation", "result", "changed_spans", "needs_confirmation"}:
                    raise ValueError(f"not a formatter contract: {path}: {target.keys()}")
                rows.append({"input": row["input"], "output": row["output"]})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(json.dumps({"rows": len(rows), "out": str(args.out)}))


if __name__ == "__main__":
    main()
