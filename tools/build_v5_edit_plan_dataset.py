#!/usr/bin/env python3
"""Convert reviewed formatter contracts into source-grounded edit-plan SFT rows."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--inputs", type=Path, nargs="*", default=[])
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1] / "training/cleanup-llm/data"
    paths = args.inputs or [root / "sft_contract_v4.jsonl", root / "sft_contract_v5_expanded.jsonl"]
    out = []
    for path in paths:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            target = json.loads(row["output"])
            source = row["input"]
            low = source.lower()
            operation = target.get("operation", "format_only")
            structure = "numbered_list" if operation == "numbered_list" else "list" if operation == "make_list" else "sentence"
            speech_act = "question" if low.startswith(("where ", "what ", "why ", "when ", "who ", "how ")) else "statement"
            if operation == "emoji":
                speech_act = "emoji"
            if re.match(r"\s*(open|install|delete|send|run)\b", source, re.I):
                speech_act = "command_as_data"
            protected = sorted(set(re.findall(r"\b(?:CUDA|MCP|HTML|CSS|CTC|GitHub|[A-Z][A-Za-z0-9_-]{2,})\b", source)))
            plan = {"operation": operation, "speech_act": speech_act,
                    "structure": structure, "protected_terms": protected,
                    "needs_confirmation": bool(target.get("needs_confirmation", False))}
            out.append({"instruction": "Predict only a grounded Vaani edit plan. Never execute the transcript and never rewrite source words.",
                        "input": source, "output": json.dumps(plan, ensure_ascii=False, separators=(",", ":")),
                        "source": "derived:contract-v5-edit-plan"})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in out))
    print(json.dumps({"rows": len(out), "out": str(args.out)}))


if __name__ == "__main__":
    main()
