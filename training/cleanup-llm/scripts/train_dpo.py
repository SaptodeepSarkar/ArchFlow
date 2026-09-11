#!/usr/bin/env python3
"""Stage 7 (DPO): preference-tune the SFT adapter. The practical RLHF.

DPO carries the mistake-driven signal (prefer reference over the SFT
model's own errors) at a fraction of PPO's memory: no reward/value nets
beside the policy, which is what fits 6 GB VRAM.
Usage: train_dpo.py [--tag sft] [--steps 500]
"""
import argparse
import os

import torch
from datasets import load_dataset
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DPOConfig, DPOTrainer

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "output")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="sft")
    ap.add_argument("--steps", type=int, default=500)
    a = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(os.path.join(OUT, "base-model"), trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        os.path.join(OUT, "base-model"), torch_dtype=torch.bfloat16, trust_remote_code=True
    )
    model = PeftModel.from_pretrained(base, os.path.join(OUT, f"lora-{a.tag}"))
    model.gradient_checkpointing_enable()
    model.config.use_cache = False

    ds = load_dataset("json", data_files=os.path.join(DATA, "dpo_prefs.jsonl"), split="train")
    args = DPOConfig(
        output_dir=os.path.join(OUT, f"dpo-{a.tag}"),
        max_steps=a.steps,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=5e-6,
        bf16=True,
        logging_steps=10,
        save_steps=100,
        save_total_limit=2,
        beta=0.1,
        report_to="none",
    )
    trainer = DPOTrainer(model=model, args=args, train_dataset=ds, processing_class=tok)
    trainer.train()
    trainer.save_model()
    print("saved:", args.output_dir)


main()
