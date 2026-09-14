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

from v5_formatter_prompt import prompt as native_prompt
from v5_contract_guard import repair

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "training/cleanup-llm/data"
sys.path.insert(0, str(ROOT / "training/cleanup-llm/scripts"))
from v4_contract import parse_and_validate  # noqa: E402


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def prompt(row: dict, template: str, tokenizer) -> str:
    if template == "contract-v2":
        return native_prompt(tokenizer, row["input"])
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
    ap.add_argument("--template", choices=["legacy", "contract-v2"], default="legacy")
    ap.add_argument("--guard", action="store_true", help="apply the conservative contract guard")
    ap.add_argument("--aggregate-only", action="store_true",
                    help="write only aggregate counts; never persist transcript text")
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
        inputs = tokenizer(prompt(row, args.template, tokenizer), return_tensors="pt").to(model.device)
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False,
                                       pad_token_id=tokenizer.eos_token_id)
        text = tokenizer.decode(generated[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        if args.guard:
            text = repair(text, row["input"])
        validation = parse_and_validate(text, row["input"])
        expected = row.get("output", "")
        try:
            exact = json.loads(text) == json.loads(expected)
        except json.JSONDecodeError:
            exact = text == expected
        results.append({"input": row["input"], "expected": expected, "generated": text,
                        "valid": validation.valid, "reason": validation.reason,
                        "exact": exact})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    valid = sum(item["valid"] for item in results)
    exact = sum(item["exact"] for item in results)
    metrics = {"count": len(results), "valid": valid / len(results) if results else 0,
               "exact": exact / len(results) if results else 0}
    if args.aggregate_only:
        args.out.write_text(json.dumps(metrics) + "\n")
    else:
        args.out.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in results) + "\n")
    print(json.dumps({**metrics, "output": str(args.out)}))


if __name__ == "__main__":
    main()
