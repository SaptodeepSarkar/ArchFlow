#!/usr/bin/env python3
"""Resident cleanup-LLM sidecar for Vaani stream mode.

Loads Qwen3-0.6B + the LoRA adapter once (~8 s cold) and stays resident, so
every finish/inject answers in ~1-2 s instead of paying a reload per call.
The controller reaps this process after configured idle seconds (economy:
no VRAM held while you are not dictating).

Usage: llm-server.py <model_dir> <adapter_dir> [--threshold N]

Protocol (pipes, newline JSON; transcripts never logged):
  stdin  {"id": N, "text": "..."}
  stdout {"id": N, "text": "..."}  or  {"id": N, "error": "..."}
First stdout line after startup is {"ready": true}.

Keep SYSTEM in sync with scripts/vaani_inject.py (same v1 contract).
"""

import json
import os
import sys

# Fully local: never touch the network (hub checks add seconds per load).
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

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


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        sys.stderr.write("usage: llm-server.py <model_dir> <adapter_dir> [--threshold N]\n")
        raise SystemExit(2)
    model_dir, adapter_dir = args[0], args[1]
    # Keep this aligned with config.example.toml: zero means every non-empty
    # transcript is offered to the formatter.
    threshold = 0
    i = 2
    while i < len(args):
        if args[i] == "--threshold":
            i += 1
            try:
                threshold = int(args[i]) if i < len(args) else 0
            except ValueError:
                threshold = 0
        i += 1

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    tok = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
    if not tok.pad_token:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        model_dir, dtype=torch.bfloat16, trust_remote_code=True
    ).to("cuda")
    if os.path.isdir(adapter_dir):
        model = PeftModel.from_pretrained(base, adapter_dir)
    else:
        model = base
    model.config.use_cache = True
    model.eval()

    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except json.JSONDecodeError:
            continue
        jid = job.get("id")
        text = str(job.get("text", ""))
        try:
            if not text.strip() or len(text.split()) < threshold:
                sys.stdout.write(json.dumps({"id": jid, "text": text}) + "\n")
            else:
                prompt = (
                    f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
                    f"<|im_start|>user\n{text}<|im_end|>\n"
                    f"<|im_start|>assistant\n"
                )
                ids = tok(prompt, return_tensors="pt").to("cuda")
                with torch.no_grad():
                    out = model.generate(
                        **ids,
                        max_new_tokens=min(512, max(64, len(text) * 2)),
                        do_sample=False,
                    )
                gen = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
                sys.stdout.write(json.dumps({"id": jid, "text": gen if gen else text}) + "\n")
        except Exception as e:  # never wedge the controller: report, keep serving
            sys.stdout.write(json.dumps({"id": jid, "error": str(e)[:200], "text": text}) + "\n")
        sys.stdout.flush()


main()
