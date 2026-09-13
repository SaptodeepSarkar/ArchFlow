#!/usr/bin/env python3
"""Evaluate the V5 formatter adapter without allowing it to execute commands."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "training/cleanup-llm/data"
sys.path.insert(0, str(ROOT / "training/cleanup-llm/scripts"))
from v4_contract import parse_and_validate  # noqa: E402


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def prompt(row: dict) -> str:
    return ("[SYSTEM]\n" + row["instruction"] + "\n[/SYSTEM]\n"
            "[USER]\n" + row["input"] + "\n[/USER]\n"
            "[ASSISTANT]\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=Path("/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m"))
    ap.add_argument("--adapter", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=DATA / "eval_contract_v4.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-new-tokens", type=int, default=180)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    base = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype="auto", device_map="auto")
    model = PeftModel.from_pretrained(base, args.adapter)
    model.eval()
    data = rows(args.data)
    if args.limit:
        data = data[:args.limit]
    results = []
    for row in data:
        inputs = tokenizer(prompt(row), return_tensors="pt").to(model.device)
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False,
                                       pad_token_id=tokenizer.eos_token_id)
        text = tokenizer.decode(generated[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        validation = parse_and_validate(text, row["input"])
        expected = row.get("output", "")
        results.append({"input": row["input"], "expected": expected, "generated": text,
                        "valid": validation.valid, "reason": validation.reason,
                        "exact": text == expected})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in results) + "\n")
    valid = sum(item["valid"] for item in results)
    exact = sum(item["exact"] for item in results)
    print(json.dumps({"count": len(results), "valid": valid / len(results) if results else 0,
                      "exact": exact / len(results) if results else 0, "output": str(args.out)}))


if __name__ == "__main__":
    main()
