#!/usr/bin/env python3
"""LoRA-train the downloaded SmolLM2 V5 formatter on Vaani contracts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "training/cleanup-llm/data"


def load(name):
    path = DATA / name
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def render(row):
    return ("[SYSTEM]\n" + row["instruction"] + "\n[/SYSTEM]\n"
            "[USER]\n" + row["input"] + "\n[/USER]\n"
            "[ASSISTANT]\n" + row["output"] + "\n[/ASSISTANT]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=Path("/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m"))
    ap.add_argument("--out", type=Path, default=Path("/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-adapter"))
    ap.add_argument("--steps", type=int, default=500)
    args = ap.parse_args()

    grammar = load("sft_grammar.jsonl")
    speech = load("sft_speech.jsonl")
    structure = load("sft_structure.jsonl")
    intent = load("sft_intent.jsonl")
    contract = load("sft_contract_v4.jsonl")
    rows = grammar + speech * 20 + structure * 3 + intent * 10 + contract * 30
    print(f"rows={len(rows)} grammar={len(grammar)} contract={len(contract)}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=torch.bfloat16)
    model.config.use_cache = False
    ds = Dataset.from_list([{"text": render(row)} for row in rows])
    bf16 = torch.cuda.is_bf16_supported()
    config = SFTConfig(
        output_dir=str(args.out), max_steps=args.steps,
        per_device_train_batch_size=1, gradient_accumulation_steps=16,
        learning_rate=5e-5, lr_scheduler_type="cosine", warmup_steps=20,
        bf16=bf16, fp16=not bf16, gradient_checkpointing=True,
        logging_steps=10, save_steps=100, save_total_limit=2,
        max_length=768, packing=False, dataset_text_field="text", report_to="none",
    )
    trainer = SFTTrainer(
        model=model, args=config, train_dataset=ds,
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=16, lora_alpha=32, lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
            task_type="CAUSAL_LM",
        ),
    )
    trainer.train()
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))
    print(f"saved V5 formatter adapter: {args.out}")


if __name__ == "__main__":
    main()
