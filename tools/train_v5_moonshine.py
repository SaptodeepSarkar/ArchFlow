#!/usr/bin/env python3
"""Fine-tune Moonshine Streaming on confirmed feedback.

This checkpoint is encoder-decoder seq2seq, not CTC/RNNT, so its native
cross-entropy objective is used. Rewards up-weight difficult examples and
training audio receives conservative gain/noise/speed augmentation.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly
from transformers import (AutoProcessor, MoonshineStreamingForConditionalGeneration,
                          Seq2SeqTrainer, Seq2SeqTrainingArguments)

SR = 16_000


def read_audio(path: str, augment: bool) -> np.ndarray:
    audio, rate = sf.read(path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != SR:
        audio = resample_poly(audio, SR, rate).astype("float32")
    if augment:
        if random.random() < 0.7:
            audio *= random.uniform(0.85, 1.15)
        if random.random() < 0.35:
            noise = np.random.default_rng().normal(0, 0.0025, len(audio)).astype("float32")
            audio = audio + noise
        if random.random() < 0.25 and len(audio) > SR:
            rate_factor = random.choice((0.94, 1.06))
            changed = resample_poly(audio, int(100 * rate_factor), 100)
            audio = resample_poly(changed, 100, int(100 * rate_factor))
    return np.clip(audio, -1.0, 1.0).astype("float32")


def prepare(rows, processor, augment):
    output = []
    for row in rows:
        audio = read_audio(row["audio_path"], augment)
        features = processor(audio, sampling_rate=SR)
        labels = processor.tokenizer(row["text"]).input_ids
        reward = float(row.get("feedback_reward", 1.0))
        # Hard/low-reward samples get a larger gradient, capped for stability.
        weight = min(2.0, max(0.75, 1.0 + 0.75 * (1.0 - reward)))
        output.append({"input_values": features["input_values"][0],
                       "attention_mask": features["attention_mask"][0],
                       "labels": labels, "sample_weight": weight})
    return output


class Collator:
    def __init__(self, processor):
        self.processor = processor

    def __call__(self, items):
        audio = self.processor.feature_extractor.pad(
            [{"input_values": item["input_values"],
              "attention_mask": item["attention_mask"]} for item in items],
            return_tensors="pt",
        )
        labels = self.processor.tokenizer.pad(
            [{"input_ids": item["labels"]} for item in items], return_tensors="pt"
        )["input_ids"]
        labels[labels == self.processor.tokenizer.pad_token_id] = -100
        audio["labels"] = labels
        audio["sample_weight"] = torch.tensor(
            [item["sample_weight"] for item in items], dtype=torch.float32
        )
        return audio


class WeightedTrainer(Seq2SeqTrainer):
    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        weights = inputs.pop("sample_weight").to(model.device)
        labels = inputs["labels"]
        outputs = model(**inputs)
        logits = outputs.logits
        # Seq2seq models prepare decoder_input_ids internally, so logits are
        # already aligned with the label positions. Shifting here would train
        # the model one token late and catastrophically damage decoding.
        token_loss = torch.nn.functional.cross_entropy(
            logits.transpose(1, 2), labels,
            ignore_index=-100, reduction="none"
        )
        mask = labels.ne(-100)
        per_example = (token_loss * mask).sum(1) / mask.sum(1).clamp_min(1)
        loss = (per_example * weights).sum() / weights.sum().clamp_min(1e-6)
        return (loss, outputs) if return_outputs else loss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--model", type=Path, default=Path("/home/saptodeep/.local/share/vaani/models/v5-stt-moonshine-tiny"))
    ap.add_argument("--out", type=Path, default=Path("/home/saptodeep/.local/share/vaani/models/v5-stt-moonshine-feedback"))
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    args = ap.parse_args()

    rows = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    random.Random(20260914).shuffle(rows)
    eval_rows = rows[-100:]
    train_rows = rows[:-100]
    processor = AutoProcessor.from_pretrained(args.model)
    print(f"train={len(train_rows)} eval={len(eval_rows)} model={args.model}", flush=True)
    train = prepare(train_rows, processor, augment=True)
    evaluation = prepare(eval_rows, processor, augment=False)
    # Keep master weights in FP32; Seq2SeqTrainer/GradScaler owns the FP16
    # autocast and gradient scaling. Loading FP16 weights here causes the
    # scaler to reject already-half-precision gradients.
    model = MoonshineStreamingForConditionalGeneration.from_pretrained(args.model)
    model.config.use_cache = False
    training = Seq2SeqTrainingArguments(
        output_dir=str(args.out), max_steps=args.steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=max(1, args.batch_size // 2),
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=2e-5, warmup_steps=25, lr_scheduler_type="cosine",
        fp16=True, gradient_checkpointing=True,
        eval_strategy="steps", eval_steps=100, save_steps=100,
        save_total_limit=2, logging_steps=10, report_to="none",
        predict_with_generate=False, remove_unused_columns=False,
    )
    trainer = WeightedTrainer(model=model, args=training,
                              train_dataset=train, eval_dataset=evaluation,
                              data_collator=Collator(processor), processing_class=processor)
    trainer.train()
    trainer.save_model(str(args.out))
    processor.save_pretrained(str(args.out))
    print(f"saved V5 STT: {args.out}")


if __name__ == "__main__":
    main()
