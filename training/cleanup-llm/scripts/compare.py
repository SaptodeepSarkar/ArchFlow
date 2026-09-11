#!/usr/bin/env python3
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import os, sys

OUT = os.path.join(os.path.dirname(__file__), "..", "output")
tok = AutoTokenizer.from_pretrained(os.path.join(OUT, "base-model"), trust_remote_code=True)
SYSTEM = ("You are a conservative transcription editor. Fix ONLY grammar, "
    "punctuation, capitalization, and obvious filler words. Preserve meaning, "
    "negation, numbers, names, units, code, paths, and the original language. "
    "Do not add facts, do not rephrase claims, do not translate. If unsure, "
    "return the input unchanged.")

text = sys.argv[1] if len(sys.argv) > 1 else "uh i was talking to vishal last night and i think that he is kind of a mischievous person but it is okay every person has its own trait"

for tag, path in [("SFT", os.path.join(OUT, "lora-sft")), ("DPO", os.path.join(OUT, "dpo-sft"))]:
    base = AutoModelForCausalLM.from_pretrained(os.path.join(OUT, "base-model"), torch_dtype=torch.bfloat16, trust_remote_code=True).to("cuda")
    model = PeftModel.from_pretrained(base, path).eval().to("cuda")
    prompt = f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{text}<|im_end|>\n<|im_start|>assistant\n"
    with torch.no_grad():
        ids = tok(prompt, return_tensors="pt").to("cuda")
        out = model.generate(**ids, max_new_tokens=256, do_sample=False)
        gen = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    print(f"--- {tag} ---")
    print(gen)
