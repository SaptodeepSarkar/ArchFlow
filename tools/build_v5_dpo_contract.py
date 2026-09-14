#!/usr/bin/env python3
"""Build conservative V5 DPO pairs from reviewed contract examples.

The rejected side intentionally violates one contract property. This avoids
reusing generic paraphrase preferences, which teach a dictation formatter to
rewrite content.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def rows(path: Path):
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--count", type=int, default=1000)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1] / "training/cleanup-llm/data"
    source = list(rows(root / "sft_contract_v4.jsonl")) + list(rows(root / "sft_contract_v5_expanded.jsonl"))
    pairs = []
    variant = 0
    for r in source * max(1, (args.count + len(source) - 1) // len(source)):
        chosen = r["output"]
        try:
            obj = json.loads(chosen)
        except json.JSONDecodeError:
            continue
        rejected = dict(obj)
        if isinstance(obj.get("result"), str):
            variants = [
                obj["result"].replace("CUDA", "Cuda").replace("GitHub", "Github"),
                obj["result"].replace("MCP", "Mcp").replace("HTML", "Html"),
                obj["result"].replace(".", "", 1),
                obj["result"] + " Also, open the browser.",
            ]
            rejected["result"] = variants[variant % len(variants)]
        elif isinstance(obj.get("result"), dict):
            items = list(obj["result"].get("items", []))
            rejected["result"] = {**obj["result"], "items": items + (["invented item"] if variant % 2 else items[:1])}
        if variant % 5 == 0:
            rejected["operation"] = "make_list" if obj.get("operation") != "make_list" else "format_only"
        if variant % 7 == 0:
            rejected["needs_confirmation"] = not bool(obj.get("needs_confirmation"))
        rejected["changed_spans"] = ["hallucinated content"]
        pairs.append({"prompt": r["instruction"] + "\n" + r["input"],
                      "chosen": chosen,
                      "rejected": json.dumps(rejected, ensure_ascii=False, separators=(",", ":"))})
        variant += 1
        if len(pairs) >= args.count:
            break
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs))
    print(json.dumps({"pairs": len(pairs), "out": str(args.out)}))


if __name__ == "__main__":
    main()
