#!/usr/bin/env python3
"""Stage 5 (eval): holdout checks for a LoRA tag. Usage: eval.py --tag sft.

Reports: exact-match rate on grammar holdout (sample), exact-match on the
speech holdout, and list-format presence. Exits nonzero when nothing loads.
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
def generate(model, tok, instruction, text, max_new=256):
    prompt = (
        f"<|im_start|>system\n{instruction}<|im_end|>\n"
        f"<|im_start|>user\n{text}<|im_end|>\n"
        f"<|im_start|>assistant\n"
    )
    ids = tok(prompt, return_tensors="pt").to(model.device)
    out = model.generate(**ids, max_new_tokens=max_new, do_sample=False)
    gen = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    return gen.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sft")
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()

    adapter = os.path.join(OUT, f"lora-{a.tag}")
    tok = AutoTokenizer.from_pretrained(os.path.join(OUT, "base-model"), trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        os.path.join(OUT, "base-model"), torch_dtype=torch.bfloat16, trust_remote_code=True
    )
    model = PeftModel.from_pretrained(base, adapter).eval()

    grammar = load_pairs(os.path.join(DATA, "eval_grammar.jsonl"), a.n)
    speech = load_pairs(os.path.join(DATA, "eval_speech.jsonl"), 50)
    g_hit = sum(
        generate(model, tok, r["instruction"], r["input"]) == r["output"] for r in grammar
    )
    s_hit, s_list = 0, 0
    for r in speech:
        got = generate(model, tok, r["instruction"], r["input"])
        s_hit += got == r["output"]
        if "- " in r["output"]:
            s_list += ("- " in got)
    print(f"[{a.tag}] grammar exact: {g_hit}/{len(grammar)}")
    print(f"[{a.tag}] speech exact: {s_hit}/{len(speech)}")
    print(f"[{a.tag}] list-format kept: {s_list} list cases checked")
    print(json.dumps({"tag": a.tag, "grammar": [g_hit, len(grammar)], "speech": [s_hit, len(speech)]}))


main()
