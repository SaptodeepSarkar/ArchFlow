#!/usr/bin/env python3
"""Stage 2 (base grammar): CoEdit instruction pairs -> data/sft_grammar.jsonl.

Each line: {"instruction": ..., "input": ..., "output": ...}.
Keeps grammar/coherence/paraphrase tasks that match transcript cleanup;
drops tasks needing outside facts. Deterministic 95/5 train/holdout split.
"""
import json
import os
import random

from datasets import load_dataset

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

KEEP = {
    "gec",  # grammar error correction
    "coherence",
    "paraphrase",
    "formalize",
    "simplify",
}

SYSTEM = (
    "You are a conservative transcription editor. Fix ONLY grammar, "
    "punctuation, capitalization, and obvious filler words. Preserve meaning, "
    "negation, numbers, names, units, code, paths, and the original language. "
    "Do not add facts, do not rephrase claims, do not translate. If unsure, "
    "return the input unchanged."
)


def main() -> None:
    ds = load_dataset("grammarly/coedit", split="train")
    rows = []
    for ex in ds:
        task = str(ex.get("task", "")).lower()
        src = str(ex.get("src", "")).strip()
        tgt = str(ex.get("tgt", "")).strip()
        if task not in KEEP or not src or not tgt or src == tgt:
            continue
        if len(src) > 1200 or len(tgt) > 1200:
            continue
        rows.append(
            {"instruction": SYSTEM, "input": src, "output": tgt, "source": f"coedit:{task}"}
        )
    random.Random(7).shuffle(rows)
    cut = int(len(rows) * 0.95)
    with open(os.path.join(DATA, "sft_grammar.jsonl"), "w") as f:
        for r in rows[:cut]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(DATA, "eval_grammar.jsonl"), "w") as f:
        for r in rows[cut:]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"grammar pairs: train={cut} holdout={len(rows) - cut}")


main()
