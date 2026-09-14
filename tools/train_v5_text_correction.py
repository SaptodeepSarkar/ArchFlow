#!/usr/bin/env python3
"""Train a small, source-grounded transcript correction LoRA adapter."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


def render(row: dict) -> str:
    return (f"<|im_start|>system\n{row['instruction']}<|im_end|>\n"
            f"<|im_start|>user\n{row['input']}<|im_end|>\n"
            f"<|im_start|>assistant\n{row['output']}<|im_end|>")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    args = ap.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for correction training")
    rows = [json.loads(x) for x in args.data.read_text().splitlines() if x.strip()]
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        str(args.model), torch_dtype=torch.bfloat16, trust_remote_code=True)
    model.config.use_cache = False
    peft = LoraConfig(
        r=32, lora_alpha=64, lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft)
    model.print_trainable_parameters()
    ds = Dataset.from_list([{"text": render(row)} for row in rows])
    config = SFTConfig(
        output_dir=str(args.out), max_steps=args.steps,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr, lr_scheduler_type="cosine", warmup_steps=30,
        bf16=True, gradient_checkpointing=True, logging_steps=10,
        save_steps=100, save_total_limit=2, max_length=512, packing=False,
        dataset_text_field="text", report_to="none",
    )
    trainer = SFTTrainer(model=model, args=config, train_dataset=ds,
                         processing_class=tokenizer)
    trainer.train()
    trainer.save_model(str(args.out))
    print(f"saved correction adapter: {args.out}")


if __name__ == "__main__":
    main()
