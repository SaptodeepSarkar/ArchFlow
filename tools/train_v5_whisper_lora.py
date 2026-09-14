#!/usr/bin/env python3
"""Continue the tested Indian-English Whisper checkpoint on V5 feedback.

This is deliberately a conservative LoRA continuation, not a replacement
model trained from scratch.  It uses the same deterministic 900/100 split as
the Moonshine experiments, reward-weighted examples, and mild waveform
augmentation.  The held-out references never enter training.
"""
from __future__ import annotations

import argparse
import json
import random
import wave
from pathlib import Path

import numpy as np
import torch
from peft import LoraConfig, get_peft_model
from transformers import (Seq2SeqTrainer, Seq2SeqTrainingArguments,
                          WhisperForConditionalGeneration, WhisperProcessor)

SR = 16_000
SEED = 20260914


def read_audio(path: str, augment: bool) -> np.ndarray:
    with wave.open(path, "rb") as handle:
        rate, channels, width = handle.getframerate(), handle.getnchannels(), handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())
    if width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    elif width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype("float32") / 2147483648.0
    else:
        raise ValueError(f"unsupported PCM width {width}: {path}")
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SR:
        new_len = max(1, round(len(audio) * SR / rate))
        audio = np.interp(np.linspace(0, len(audio) - 1, new_len), np.arange(len(audio)), audio)
    if augment:
        rng = np.random.default_rng()
        if random.random() < 0.6:
            audio = audio * random.uniform(0.92, 1.08)
        if random.random() < 0.25:
            audio = audio + rng.normal(0.0, 0.0015, len(audio))
    return np.clip(audio, -1.0, 1.0).astype("float32")


def make_rows(rows, processor, augment: bool):
    result = []
    for row in rows:
        audio = read_audio(row["audio_path"], augment)
        features = processor(audio, sampling_rate=SR).input_features[0]
        labels = processor.tokenizer(row["text"], truncation=True, max_length=224).input_ids
        if labels and labels[0] == processor.tokenizer.bos_token_id:
            labels = labels[1:]
        reward = float(row.get("feedback_reward", 1.0))
        protected = len(row.get("missing_protected_terms", []))
        weight = min(2.0, max(0.85, 1.0 + 0.6 * (1.0 - reward) + 0.2 * protected))
        result.append({"input_features": np.asarray(features, dtype=np.float32),
                       "labels": labels, "weight": weight})
    return result


class Collator:
    def __init__(self, processor):
        self.processor = processor

    def __call__(self, items):
        batch = self.processor.feature_extractor.pad(
            [{"input_features": x["input_features"]} for x in items], return_tensors="pt")
        labels = self.processor.tokenizer.pad(
            [{"input_ids": x["labels"]} for x in items], return_tensors="pt")["input_ids"]
        labels[labels == self.processor.tokenizer.pad_token_id] = -100
        batch["labels"] = labels
        batch["sample_weight"] = torch.tensor([x["weight"] for x in items], dtype=torch.float32)
        return batch


class WeightedTrainer(Seq2SeqTrainer):
    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        weights = inputs.pop("sample_weight").to(model.device)
        labels = inputs["labels"]
        outputs = model(**inputs)
        loss = torch.nn.functional.cross_entropy(
            outputs.logits.transpose(1, 2), labels, ignore_index=-100, reduction="none")
        mask = labels.ne(-100)
        per_row = (loss * mask).sum(1) / mask.sum(1).clamp_min(1)
        value = (per_row * weights).sum() / weights.sum().clamp_min(1e-6)
        return (value, outputs) if return_outputs else value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--steps", type=int, default=250)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--learning-rate", type=float, default=1e-5)
    args = ap.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this training run")
    random.seed(SEED)
    rows = [json.loads(x) for x in args.manifest.read_text().splitlines() if x.strip()]
    random.Random(SEED).shuffle(rows)
    train_rows, eval_rows = rows[:-100], rows[-100:]
    processor = WhisperProcessor.from_pretrained(str(args.model), language="english", task="transcribe")
    train = make_rows(train_rows, processor, True)
    evaluation = make_rows(eval_rows, processor, False)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = WhisperForConditionalGeneration.from_pretrained(
        str(args.model), torch_dtype=dtype, low_cpu_mem_usage=True)
    model.config.forced_decoder_ids = None
    model.config.suppress_tokens = []
    model.config.use_cache = False
    lora = LoraConfig(r=16, lora_alpha=32, target_modules=["q_proj", "v_proj"],
                      lora_dropout=0.05, bias="none")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    training = Seq2SeqTrainingArguments(
        output_dir=str(args.out), max_steps=args.steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1, gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate, warmup_steps=25,
        lr_scheduler_type="cosine", bf16=dtype == torch.bfloat16,
        fp16=dtype == torch.float16, tf32=True, gradient_checkpointing=True,
        eval_strategy="no", save_strategy="steps", save_steps=100,
        save_total_limit=2, logging_steps=10, report_to="none",
        remove_unused_columns=False, label_names=["labels"], seed=SEED,
    )
    trainer = WeightedTrainer(model=model, args=training, train_dataset=train,
                              eval_dataset=evaluation, data_collator=Collator(processor),
                              processing_class=processor)
    trainer.train()
    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(args.out / "adapter"))
    processor.save_pretrained(str(args.out / "adapter"))
    print(f"saved V5 Whisper adapter: {args.out / 'adapter'}")


if __name__ == "__main__":
    main()
