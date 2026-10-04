#!/usr/bin/env python3
"""Resident cleanup-LLM sidecar for Vaani’s always-on formatter.

Loads the configured local base + LoRA adapter once and stays resident, so
every finish/inject answers in ~1-2 s instead of paying a reload per call.
The controller reaps this process after configured idle seconds (economy:
no VRAM held while you are not dictating).

Usage: llm-server.py <model_dir> <adapter_dir>

Protocol (pipes, newline JSON; transcripts never logged):
  stdin  {"id": N, "text": "..."}
  stdout {"id": N, "text": "..."}  or  {"id": N, "error": "..."}
First stdout line after startup is {"ready": true}.

Shared prompt and generation limits live in formatter_protocol.py.
"""

import json
import os
import sys
from formatter_protocol import (
    IN_TAG, OUT_TAG, adapter_has_trainable_token_rows, align_token_embeddings,
    initialize_v6_token_embeddings, max_new_tokens_v5, v6_requires_copy_fallback,
    max_new_tokens_v6, prompt_v5, prompt_v6,
)

# Fully local: never touch the network (hub checks add seconds per load).
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

def main() -> None:
    args = sys.argv[1:]
    if len(args) < 2:
        sys.stderr.write("usage: llm-server.py <model_dir> <adapter_dir>\n")
        raise SystemExit(2)
    model_dir, adapter_dir = args[0], args[1]
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    tok_path = adapter_dir if os.path.isfile(os.path.join(adapter_dir, "tokenizer.json")) else model_dir
    tok = AutoTokenizer.from_pretrained(tok_path, trust_remote_code=True)
    if not tok.pad_token:
        tok.pad_token = tok.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        model_dir, dtype=torch.bfloat16, trust_remote_code=True
    ).to("cuda")
    v6 = tok.convert_tokens_to_ids(IN_TAG) != tok.unk_token_id and tok.convert_tokens_to_ids(OUT_TAG) != tok.unk_token_id
    align_token_embeddings(base, tok, force=adapter_has_trainable_token_rows(adapter_dir))
    initialize_v6_token_embeddings(base, tok)
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
            if not text.strip():
                sys.stdout.write(json.dumps({"id": jid, "text": text}) + "\n")
            else:
                prompt = prompt_v6(text) if v6 else prompt_v5(text)
                ids = tok(prompt, return_tensors="pt").to("cuda")
                with torch.no_grad():
                    out = model.generate(
                        **ids,
                        max_new_tokens=max_new_tokens_v6(ids["input_ids"].shape[1]) if v6 else max_new_tokens_v5(text),
                        do_sample=False,
                    )
                gen = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
                if v6 and v6_requires_copy_fallback(text, gen):
                    gen = text
                sys.stdout.write(json.dumps({"id": jid, "text": gen if gen else text, "protocol": "v6" if v6 else "v5"}) + "\n")
        except Exception as e:  # never wedge the controller: report, keep serving
            sys.stdout.write(json.dumps({"id": jid, "error": str(e)[:200], "text": text}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
