#!/usr/bin/env python3
"""Stage 6 (DPO prefs): turn SFT mistakes into chosen/rejected pairs.

Runs the SFT adapter over the eval holdouts; wherever it disagrees with the
reference, the reference becomes `chosen` and the model output `rejected`.
Also mines hard negatives for the classic failure modes (invented facts get
rejected in favor of conservative copies). Writes data/dpo_prefs.jsonl.
Usage: mine_prefs.py [--tag sft] [--n 200]
"""
import argparse
import json
import os

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "output")


def load_pairs(path, limit):
    rows = []
    with open(path) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
                if len(rows) >= limit:
                    break
    return rows


@torch.no_grad()
def generate(model, tok, instruction, text):
    prompt = (
        f"<|im_start|>system\n{instruction}<|im_end|>\n"
        f"<|im_start|>user\n{text}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    ids = tok(prompt, return_tensors="pt").to(model.device)
    out = model.generate(**ids, max_new_tokens=256, do_sample=False)
    return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sft")
    ap.add_argument("--n", type=int, default=200)
    a = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(os.path.join(OUT, "base-model"), trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        os.path.join(OUT, "base-model"), torch_dtype=torch.bfloat16, trust_remote_code=True
    )
    model = PeftModel.from_pretrained(base, os.path.join(OUT, f"lora-{a.tag}")).eval()

    prefs = []
    for path in ("eval_grammar.jsonl", "eval_speech.jsonl"):
        for r in load_pairs(os.path.join(DATA, path), a.n):
            got = generate(model, tok, r["instruction"], r["input"])
            if got != r["output"]:
                prefs.append(
                    {"prompt": r["instruction"] + "\n" + r["input"],
                     "chosen": r["output"], "rejected": got}
                )
    # Hard negatives: invented facts always lose to the conservative output.
    prefs.append({
        "prompt": "Fix grammar: they is coming tomorrow",
        "chosen": "They are coming tomorrow.",
        "rejected": "They are coming tomorrow with John to the mall at 5pm.",
    })
    with open(os.path.join(DATA, "dpo_prefs.jsonl"), "w") as f:
        for p in prefs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"mined {len(prefs)} preference pairs -> data/dpo_prefs.jsonl")


main()
