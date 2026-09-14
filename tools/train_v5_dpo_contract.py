#!/usr/bin/env python3
"""DPO for the conservative V5 formatter contract.

This intentionally accepts only source-grounded V5 preference pairs. It is
not interchangeable with the older paraphrase-oriented DPO experiment.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import torch
from datasets import load_dataset
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DPOConfig, DPOTrainer


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    ap.add_argument("--adapter", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=100)
    a = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(a.base)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    base = AutoModelForCausalLM.from_pretrained(a.base, torch_dtype=dtype).to("cuda")
    model = PeftModel.from_pretrained(base, a.adapter)
    model.train()
    # Loading an adapter for inference can leave all LoRA tensors frozen;
    # explicitly make only the policy adapter trainable for DPO.
    try:
        model.set_adapter("default")
    except (ValueError, KeyError):
        pass
    for name, param in model.named_parameters():
        param.requires_grad = "lora_" in name or "adapter" in name
    ref = AutoModelForCausalLM.from_pretrained(a.base, torch_dtype=dtype).to("cuda")
    ref.eval()
    for p in ref.parameters():
        p.requires_grad = False
    ds = load_dataset("json", data_files=str(a.data), split="train")
    cfg = DPOConfig(
        output_dir=str(a.out), max_steps=a.steps,
        per_device_train_batch_size=1, gradient_accumulation_steps=8,
        learning_rate=5e-6, beta=0.1,
        bf16=torch.cuda.is_bf16_supported(), fp16=not torch.cuda.is_bf16_supported(),
        logging_steps=10, save_steps=50, save_total_limit=2,
        report_to="none", gradient_checkpointing=False,
    )
    trainer = DPOTrainer(model=model, ref_model=ref, args=cfg,
                         train_dataset=ds, processing_class=tok)
    trainer.train()
    trainer.save_model(str(a.out))
    tok.save_pretrained(str(a.out))
    print(f"saved V5 DPO adapter: {a.out}")


if __name__ == "__main__":
    main()
