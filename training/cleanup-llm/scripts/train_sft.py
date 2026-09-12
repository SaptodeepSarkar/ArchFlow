#!/usr/bin/env python3
"""Stage 4 (SFT): LoRA-tune Qwen3-0.6B on grammar + speech mixes.

Full fine-tuning does not fit 6 GB VRAM; LoRA r=32 on q/v/o + mlp matches
it for style adaptation (same call Cozy made for STT). The base model stays
frozen; only adapter weights move. Usage: train_sft.py [--steps N]
[--tag NAME] [--from-adapter NAME] [--structure-repeat N] [--lr RATE]
[--out-name DIR] [--smoke]
"""
import argparse
import json
import os

import torch
from datasets import load_dataset
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training  # noqa: F401
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer

BASE = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "output")


def load_pairs(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def fmt(ex):
    return (
        f"<|im_start|>system\n{ex['instruction']}<|im_end|>\n"
        f"<|im_start|>user\n{ex['input']}<|im_end|>\n"
        f"<|im_start|>assistant\n{ex['output']}<|im_end|>"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--tag", default="sft")
    ap.add_argument("--from-adapter", default="", help="Continue an existing adapter without touching base weights")
    ap.add_argument("--structure-repeat", type=int, default=0, help="Repeat LLM v1 structure rows per epoch")
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--out-name", default="", help="Adapter directory name; defaults to lora-TAG")
    ap.add_argument("--smoke", action="store_true", help="50 steps on 200 rows to prove the loop")
    a = ap.parse_args()

    def resolve_adapter(name):
        if os.path.isdir(name):
            return name
        candidate = os.path.join(OUT, name)
        if os.path.isdir(candidate):
            return candidate
        raise SystemExit(f"adapter not found: {name}")

    grammar = load_pairs(os.path.join(DATA, "sft_grammar.jsonl"))
    speech = load_pairs(os.path.join(DATA, "sft_speech.jsonl"))
    structure = []
    structure_path = os.path.join(DATA, "sft_structure.jsonl")
    if a.structure_repeat > 0:
        if not os.path.exists(structure_path):
            raise SystemExit("sft_structure.jsonl missing: run build_structure_data.py first")
        structure = load_pairs(structure_path)
    # Speech pairs are few but precious: upsample so every epoch sees them.
    train_rows = grammar + speech * max(1, len(grammar) // max(1, len(speech)) // 20)
    train_rows += structure * max(0, a.structure_repeat)
    if a.smoke:
        train_rows = (grammar[:150] + speech * 5 + structure[:20])[:200]
    print(f"sft rows: {len(train_rows)} (grammar={len(grammar)} speech={len(speech)} structure={len(structure)})")

    tok = AutoTokenizer.from_pretrained(os.path.join(OUT, "base-model"), trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        os.path.join(OUT, "base-model"),
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    model.config.use_cache = False
    if a.from_adapter:
        model = PeftModel.from_pretrained(model, resolve_adapter(a.from_adapter), is_trainable=True)
        model.train()
        for p in model.base_model.model.parameters():
            p.requires_grad = False
        for name, p in model.named_parameters():
            if "lora" in name or "adapter" in name:
                p.requires_grad = True
    else:
        peft = LoraConfig(
            r=32,
            lora_alpha=64,
            lora_dropout=0.05,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, peft)
    model.print_trainable_parameters()

    from datasets import Dataset

    ds = Dataset.from_list([{"text": fmt(r)} for r in train_rows])
    args = SFTConfig(
        output_dir=os.path.join(OUT, a.out_name or f"lora-{a.tag}"),
        max_steps=a.steps if not a.smoke else 50,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=a.lr,
        lr_scheduler_type="cosine",
        warmup_steps=20,
        bf16=True,
        gradient_checkpointing=False,
        logging_steps=10,
        save_steps=100 if not a.smoke else 50,
        save_total_limit=2,
        max_length=1024,
        packing=False,
        dataset_text_field="text",
        report_to="none",
    )
    trainer = SFTTrainer(model=model, args=args, train_dataset=ds, processing_class=tok)
    trainer.train()
    trainer.save_model()
    print("saved:", args.output_dir)


main()
