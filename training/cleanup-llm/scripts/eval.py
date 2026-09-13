#!/usr/bin/env python3
"""Stage 5 (eval): holdout checks for a LoRA tag. Usage: eval.py --tag sft.

Reports: exact-match rate on grammar holdout (sample), exact-match on the
speech holdout, structure-format checks, and source-grounding checks.
Exits nonzero when nothing loads.
"""
import argparse
import json
import os
import re

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from v4_contract import parse_and_validate

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
    ap.add_argument("--adapter", default="", help="Explicit adapter directory; overrides the tag convention")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--structure-n", type=int, default=100)
    ap.add_argument("--show-intent", action="store_true")
    a = ap.parse_args()

    if a.adapter:
        adapter = a.adapter if os.path.isdir(a.adapter) else os.path.join(OUT, a.adapter)
    elif a.tag == "dpo":
        adapter = os.path.join(OUT, "dpo-sft")
    elif a.tag == "llm-v1":
        adapter = os.path.join(OUT, "llm-v1")
    else:
        adapter = os.path.join(OUT, f"lora-{a.tag}")
    if not os.path.isdir(adapter):
        raise SystemExit(f"adapter not found: {adapter}")
    tok = AutoTokenizer.from_pretrained(os.path.join(OUT, "base-model"), trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        os.path.join(OUT, "base-model"), torch_dtype=torch.bfloat16, trust_remote_code=True
    ).to("cuda")
    model = PeftModel.from_pretrained(base, adapter).eval()

    grammar = load_pairs(os.path.join(DATA, "eval_grammar.jsonl"), a.n)
    speech = load_pairs(os.path.join(DATA, "eval_speech.jsonl"), 50)
    structure = []
    structure_path = os.path.join(DATA, "eval_structure.jsonl")
    if os.path.exists(structure_path):
        structure = load_pairs(structure_path, a.structure_n)
    intent = []
    intent_path = os.path.join(DATA, "eval_intent.jsonl")
    if os.path.exists(intent_path):
        intent = load_pairs(intent_path, 100)
    contract = []
    contract_path = os.path.join(DATA, "eval_contract_v4.jsonl")
    if os.path.exists(contract_path):
        contract = load_pairs(contract_path, 100)
    g_hit = sum(
        generate(model, tok, r["instruction"], r["input"]) == r["output"] for r in grammar
    )
    s_hit, s_list = 0, 0
    for r in speech:
        got = generate(model, tok, r["instruction"], r["input"])
        s_hit += got == r["output"]
        if "- " in r["output"]:
            s_list += ("- " in got)
    v_hit, v_list, v_grounded = 0, 0, 0
    v_cases, v_list_cases, v_grounded_cases = 0, 0, 0
    list_marker = re.compile(r"(?:^|\n)(?:- |• |\d+\. )")
    no_source_items = {
        "make a grocery list",
        "make a list like a grocery list",
        "turn this into pointers",
        "add milk to the list",
        "i need things for the trip",
        "agenda for tomorrow",
        "buy stuff",
        "there are a few reasons",
        "tell me a grocery list",
        "hello this is me and i am testing the system and it should fix grammar when items are actually spoken",
        "please make a grocery list",
        "turn these into pointers",
        "format this as a list",
        "i want bullet points",
        "can you make it a numbered list",
        "organize this into a grocery list",
    }
    for r in structure:
        got = generate(model, tok, r["instruction"], r["input"])
        v_cases += 1
        v_hit += got == r["output"]
        if "- " in r["output"] or "• " in r["output"] or re.search(r"\n\d+\. ", r["output"]):
            v_list_cases += 1
            v_list += bool(list_marker.search(got))
        if r["input"] in no_source_items:
            v_grounded_cases += 1
            v_grounded += not bool(list_marker.search(got))
    i_hit = 0
    i_list = 0
    for r in intent:
        got = generate(model, tok, r["instruction"], r["input"])
        i_hit += got == r["output"]
        if a.show_intent:
            print(f"INTENT input={r['input']!r} expected={r['output']!r} got={got!r}")
        if list_marker.search(r["output"]):
            i_list += bool(list_marker.search(got))
    c_valid = 0
    c_exact = 0
    for r in contract:
        got = generate(model, tok, r["instruction"], r["input"], max_new=384)
        check = parse_and_validate(got, r["input"])
        c_valid += check.valid
        c_exact += got == r["output"]
    print(f"[{a.tag}] grammar exact: {g_hit}/{len(grammar)}")
    print(f"[{a.tag}] speech exact: {s_hit}/{len(speech)}")
    print(f"[{a.tag}] list-format kept: {s_list} list cases checked")
    print(f"[{a.tag}] structure exact: {v_hit}/{v_cases}")
    print(f"[{a.tag}] structure lists kept: {v_list}/{v_list_cases}")
    print(f"[{a.tag}] no invented lists: {v_grounded}/{v_grounded_cases}")
    print(f"[{a.tag}] intent exact: {i_hit}/{len(intent)}")
    print(f"[{a.tag}] intent list-format kept: {i_list}/{sum(bool(list_marker.search(r['output'])) for r in intent)}")
    print(f"[{a.tag}] contract valid: {c_valid}/{len(contract)} exact: {c_exact}/{len(contract)}")
    print(json.dumps({"tag": a.tag, "grammar": [g_hit, len(grammar)], "speech": [s_hit, len(speech)], "structure": [v_hit, v_cases], "structure_lists": [v_list, v_list_cases], "grounded": [v_grounded, v_grounded_cases], "intent": [i_hit, len(intent)], "intent_lists": i_list, "contract_valid": [c_valid, len(contract)], "contract_exact": [c_exact, len(contract)]}))


main()
