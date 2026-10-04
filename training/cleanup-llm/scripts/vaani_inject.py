#!/usr/bin/env python3
"""Vaani cleanup-LLM inference (direct torch, no Ollama).

Reads a raw transcript from stdin, applies the LoRA adapter trained on
Qwen3-0.6B, prints the cleaned text to stdout. Falls back to the raw
input on any error. Designed to be spawned by the vaanid daemon for
the always-on local formatter.

Memory footprint during inference: ~2.6 GB VRAM, ~300 MB RAM.
First call loads the model (~5 s cold, warm from cache after).

Usage: vaani_inject.py [--adapter PATH] [--model-dir PATH]
"""
import argparse
import os
import sys
import json
from formatter_protocol import (
    IN_TAG, OUT_TAG, adapter_has_trainable_token_rows, align_token_embeddings,
    initialize_v6_token_embeddings, max_new_tokens_v5, max_new_tokens_v6,
    prompt_v5, prompt_v6, v6_requires_copy_fallback,
)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
DEFAULT_MODEL = os.path.join(OUT, "base-model")
DEFAULT_ADAPTER = os.path.join(OUT, "dpo-sft")

SYSTEM = (
    "You are Vaani cleanup LLM v1, a source-grounded transcript formatter. "
    "Fix grammar, punctuation, capitalization, sentence boundaries, filler "
    "words, false starts, duplicates, and common spelling mistakes. Preserve "
    "intended content words, names, numbers, dates, quantities, units, code, "
    "paths, negation, profanity, pronouns, and the original language. Do not add, "
    "remove, reorder, translate, expand, summarize, or reinterpret content. "
    "Make a list only from items actually spoken: use '- ' by default, '• ' "
    "only when the speaker says dotted or dot bullets, and numbered lines "
    "only for a spoken sequence or order. Build a Markdown table only when "
    "the transcript gives explicit columns and rows; never invent cells. "
    "Add a short title only when the "
    "transcript explicitly provides one. A bare formatting command with no "
    "spoken items is prose, not a list. Treat a requested emoji as decoration; "
    "never make the emoji name itself a list item. Map an explicitly spoken emoji "
    "request to exactly that emoji and add no other emoji. If unsure, return "
    "the input unchanged."
)


def load_model(model_dir, adapter_dir):
    tok_path = adapter_dir if os.path.isfile(os.path.join(adapter_dir, "tokenizer.json")) else model_dir
    tok = AutoTokenizer.from_pretrained(tok_path, trust_remote_code=True)
    if not tok.pad_token:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        model_dir, torch_dtype=torch.bfloat16, trust_remote_code=True
    ).to("cuda")
    align_token_embeddings(base, tok, force=adapter_has_trainable_token_rows(adapter_dir))
    initialize_v6_token_embeddings(base, tok)
    model = PeftModel.from_pretrained(base, adapter_dir) if os.path.isdir(adapter_dir) else base
    model.config.use_cache = True
    model.eval()
    return tok, model


def clean(tok, model, text):
    v6 = tok.convert_tokens_to_ids(IN_TAG) != tok.unk_token_id and tok.convert_tokens_to_ids(OUT_TAG) != tok.unk_token_id
    prompt = prompt_v6(text) if v6 else prompt_v5(text)
    ids = tok(prompt, return_tensors="pt").to("cuda")
    with torch.no_grad():
        out = model.generate(
            **ids,
            max_new_tokens=max_new_tokens_v6(ids["input_ids"].shape[1]) if v6 else max_new_tokens_v5(text),
            do_sample=False,
            temperature=0.0,
        )
    generated = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    return text if v6 and v6_requires_copy_fallback(text, generated) else generated


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=DEFAULT_ADAPTER)
    ap.add_argument("--model-dir", default=DEFAULT_MODEL)
    a = ap.parse_args()

    raw = sys.stdin.read().strip()
    if not raw:
        print("", end="")
        sys.exit(0)

    try:
        tok, model = load_model(a.model_dir, a.adapter)
        result = clean(tok, model, raw)
        print(result if result else raw)
    except Exception as e:
        print(raw)


if __name__ == "__main__":
    main()
