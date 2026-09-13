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
import wave
from pathlib import Path

import numpy as np
import torch
from transformers import (AutoProcessor, MoonshineStreamingForConditionalGeneration,
                          Seq2SeqTrainer, Seq2SeqTrainingArguments)

SR = 16_000


def read_audio(path: str, augment: bool) -> np.ndarray:
    with wave.open(path, "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        raw = handle.readframes(handle.getnframes())
    if width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    elif width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype("float32") / 2147483648.0
    else:
        raise ValueError(f"unsupported PCM width {width} in {path}")
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != SR:
        new_len = max(1, round(len(audio) * SR / rate))
        audio = np.interp(np.linspace(0, len(audio) - 1, new_len),
                          np.arange(len(audio)), audio).astype("float32")
    if augment:
        if random.random() < 0.7:
            audio *= random.uniform(0.85, 1.15)
        if random.random() < 0.35:
            noise = np.random.default_rng().normal(0, 0.0025, len(audio)).astype("float32")
            audio = audio + noise
        if random.random() < 0.25 and len(audio) > SR:
            rate_factor = random.choice((0.94, 1.06))
            new_len = max(1, round(len(audio) / rate_factor))
            changed = np.interp(np.linspace(0, len(audio) - 1, new_len),
                                np.arange(len(audio)), audio)
            audio = np.interp(np.linspace(0, len(changed) - 1, len(audio)),
                              np.arange(len(changed)), changed)
    return np.clip(audio, -1.0, 1.0).astype("float32")


def prepare(rows, processor, augment, distill_weight=0.0):
    output = []
    for row in rows:
        variants = [(row["text"], 1.0)]
        teacher = str(row.get("baseline_hypothesis", "")).strip()
        if distill_weight > 0 and teacher and teacher != row["text"].strip():
            # Sequence-level distillation: the stronger v2 transcript is an
            # auxiliary target, never a replacement for the confirmed label.
            variants.append((teacher, distill_weight))
        audio = read_audio(row["audio_path"], augment)
        features = processor(audio, sampling_rate=SR)
        for target_text, target_weight in variants:
            labels = processor.tokenizer(target_text).input_ids
            # The model's forward() right-shifts labels and inserts BOS itself.
            # Tokenizer output already contains BOS, so remove that copy or the
            # decoder learns a duplicated BOS and often emits an empty transcript.
            if labels and labels[0] == processor.tokenizer.bos_token_id:
                labels = labels[1:]
            # Moonshine's tokenizer emits BOS but not EOS. Without an explicit
            # stop target, fine-tuned generation can continue into repeated or
            # unrelated text even when teacher-forced loss looks good.
            if labels[-1] != processor.tokenizer.eos_token_id:
                labels = labels + [processor.tokenizer.eos_token_id]
            reward = float(row.get("feedback_reward", 1.0))
            # Hard/low-reward samples get a larger gradient, capped for stability.
            weight = min(2.0, max(0.75, 1.0 + 0.75 * (1.0 - reward))) * target_weight
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
    def __init__(self, *args, teacher_model=None, kd_weight=0.0, kd_temperature=2.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.teacher_model = teacher_model
        self.kd_weight = kd_weight
        self.kd_temperature = kd_temperature

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
        if self.teacher_model is not None and self.kd_weight > 0:
            self.teacher_model.to(model.device)
            self.teacher_model.eval()
            with torch.no_grad():
                teacher_logits = self.teacher_model(**inputs).logits
            temperature = self.kd_temperature
            student_log_probs = torch.log_softmax(logits / temperature, dim=-1)
            teacher_probs = torch.softmax(teacher_logits / temperature, dim=-1)
            kd_tokens = torch.nn.functional.kl_div(
                student_log_probs, teacher_probs, reduction="none"
            ).sum(-1)
            kd_loss = (kd_tokens * mask).sum() / mask.sum().clamp_min(1)
            loss = loss + self.kd_weight * (temperature ** 2) * kd_loss
        return (loss, outputs) if return_outputs else loss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--model", type=Path, default=Path("/home/saptodeep/.local/share/vaani/models/v5-stt-moonshine-tiny"))
    ap.add_argument("--out", type=Path, default=Path("/home/saptodeep/.local/share/vaani/models/v5-stt-moonshine-feedback"))
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--learning-rate", type=float, default=2e-5)
    ap.add_argument("--distill-weight", type=float, default=0.0,
                    help="add baseline_hypothesis targets at this relative loss weight")
    ap.add_argument("--kd-weight", type=float, default=0.0,
                    help="logit-KL weight against a frozen copy of the base model")
    ap.add_argument("--kd-temperature", type=float, default=2.0)
    ap.add_argument(
        "--freeze-encoder",
        action="store_true",
        help="freeze the pretrained acoustic encoder and adapt only the decoder",
    )
    args = ap.parse_args()

    rows = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    random.Random(20260914).shuffle(rows)
    eval_rows = rows[-100:]
    train_rows = rows[:-100]
    processor = AutoProcessor.from_pretrained(args.model)
    print(f"train={len(train_rows)} eval={len(eval_rows)} model={args.model}", flush=True)
    train = prepare(train_rows, processor, augment=True, distill_weight=args.distill_weight)
    evaluation = prepare(eval_rows, processor, augment=False)
    # Keep master weights in FP32; Seq2SeqTrainer/GradScaler owns the FP16
    # autocast and gradient scaling. Loading FP16 weights here causes the
    # scaler to reject already-half-precision gradients.
    model = MoonshineStreamingForConditionalGeneration.from_pretrained(args.model)
    model.config.use_cache = False
    if args.freeze_encoder:
        # Keep the pretrained acoustic representation intact. This is useful
        # for small, narrow feedback sets where full-model SFT can erase the
        # base model's broader pronunciation coverage.
        for parameter in model.model.encoder.parameters():
            parameter.requires_grad = False
        print("freeze_encoder=true", flush=True)
    teacher_model = None
    if args.kd_weight > 0:
        teacher_model = MoonshineStreamingForConditionalGeneration.from_pretrained(args.model)
        teacher_model.config.use_cache = False
        for parameter in teacher_model.parameters():
            parameter.requires_grad = False
        teacher_model.eval()
        print(f"logit_kd=true weight={args.kd_weight} temperature={args.kd_temperature}", flush=True)
    training = Seq2SeqTrainingArguments(
        output_dir=str(args.out), max_steps=args.steps,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=max(1, args.batch_size // 2),
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.learning_rate, warmup_steps=25, lr_scheduler_type="cosine",
        fp16=True, gradient_checkpointing=True,
        eval_strategy="steps", eval_steps=100, save_steps=100,
        save_total_limit=2, logging_steps=10, report_to="none",
        predict_with_generate=False, remove_unused_columns=False,
    )
    trainer = WeightedTrainer(model=model, args=training,
                              train_dataset=train, eval_dataset=evaluation,
                              data_collator=Collator(processor), processing_class=processor,
                              teacher_model=teacher_model, kd_weight=args.kd_weight,
                              kd_temperature=args.kd_temperature)
    trainer.train()
    trainer.save_model(str(args.out))
    processor.save_pretrained(str(args.out))
    print(f"saved V5 STT: {args.out}")


if __name__ == "__main__":
    main()
