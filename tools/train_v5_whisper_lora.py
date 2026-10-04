#!/usr/bin/env python3
"""Loss-weighted LoRA adaptation for a local Whisper checkpoint.

The default mode is the historical V5 900/100 feedback experiment. V6 may pass
an upstream speaker/meeting-isolated train split using ``--pre-split``; those
rows can carry a per-example ``sample_weight`` derived from actual STT errors.
The script never includes a pre-split dev/test manifest in training.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sqlite3
import wave
from pathlib import Path

import numpy as np
import torch
from peft import LoraConfig, PeftModel, get_peft_model
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
        if random.random() < 0.20 and len(audio) > SR:
            # Time-scale perturbation. Keep the resulting duration changed so
            # the encoder sees natural fast/slow speaking variation.
            factor = random.choice((0.92, 1.08))
            output_len = max(1, round(len(audio) / factor))
            audio = np.interp(np.linspace(0, len(audio) - 1, output_len),
                              np.arange(len(audio)), audio).astype("float32")
        if random.random() < 0.15:
            # Small synthetic room impulse: direct path plus one decaying echo.
            delay = random.randint(int(0.008 * SR), int(0.045 * SR))
            impulse = np.zeros(delay + 1, dtype="float32")
            impulse[0] = 1.0
            impulse[-1] = random.uniform(0.05, 0.18)
            audio = np.convolve(audio, impulse, mode="full")[:len(audio)]
        if random.random() < 0.15:
            # Cheap microphone/voice-message codec proxy without a system codec.
            levels = random.choice((128.0, 256.0, 512.0))
            audio = np.round(audio * levels) / levels
    return np.clip(audio, -1.0, 1.0).astype("float32")


def make_dataset(rows, processor, augment: bool):
    """Build a disk-backed dataset instead of retaining every mel in RAM."""
    import datasets as hfds
    hfds.disable_progress_bars()

    def generator():
        for row in rows:
            audio = read_audio(row["audio_path"], augment)
            features = processor(audio, sampling_rate=SR).input_features[0]
            labels = processor.tokenizer(row["text"], truncation=True, max_length=224).input_ids
            if labels and labels[0] == processor.tokenizer.bos_token_id:
                labels = labels[1:]
            if "sample_weight" in row:
                weight = float(row["sample_weight"])
            else:
                reward = float(row.get("feedback_reward", 1.0))
                protected = len(row.get("missing_protected_terms", []))
                weight = min(2.0, max(0.85, 1.0 + 0.6 * (1.0 - reward) + 0.2 * protected))
            yield {"input_features": np.asarray(features, dtype=np.float32),
                   "labels": labels, "weight": weight}

    return hfds.Dataset.from_generator(
        generator,
        features=hfds.Features({
            "input_features": hfds.Sequence(hfds.Sequence(hfds.Value("float32"))),
            "labels": hfds.Sequence(hfds.Value("int32")),
            "weight": hfds.Value("float32"),
        }),
    )


class Collator:
    def __init__(self, processor):
        self.processor = processor

    def __call__(self, items):
        if any(not math.isfinite(float(x["weight"])) or float(x["weight"]) <= 0
               for x in items):
            raise ValueError("sample weights must be finite and positive")
        batch = self.processor.feature_extractor.pad(
            [{"input_features": x["input_features"]} for x in items], return_tensors="pt")
        # Whisper uses the end-of-transcript token as its pad token. Masking
        # by token ID therefore also erased each target's genuine EOS label.
        # Pad from sequence lengths so only newly-added positions are ignored.
        label_rows = [torch.tensor(x["labels"], dtype=torch.long) for x in items]
        labels = torch.nn.utils.rnn.pad_sequence(
            label_rows, batch_first=True, padding_value=-100)
        batch["labels"] = labels
        batch["sample_weight"] = torch.tensor([x["weight"] for x in items], dtype=torch.float32)
        return batch


class StreamingRows(torch.utils.data.IterableDataset):
    """Infinite feature stream with optional source-controlled sampling."""
    def __init__(self, rows, processor, augment: bool, auxiliary_rows=None,
                 auxiliary_fraction: float = 0.0, auxiliary_source_rows=None,
                 source_fractions=None):
        self.rows = rows
        self.processor = processor
        self.augment = augment
        self.auxiliary_rows = auxiliary_rows or []
        self.auxiliary_fraction = auxiliary_fraction
        self.auxiliary_source_rows = auxiliary_source_rows or []
        self.source_fractions = source_fractions or []

    def encode_row(self, row):
        audio = read_audio(row["audio_path"], self.augment)
        features = self.processor(audio, sampling_rate=SR).input_features[0]
        labels = self.processor.tokenizer(row["text"], truncation=True, max_length=224).input_ids
        if labels and labels[0] == self.processor.tokenizer.bos_token_id:
            labels = labels[1:]
        if "sample_weight" in row:
            weight = float(row["sample_weight"])
        else:
            reward = float(row.get("feedback_reward", 1.0))
            protected = len(row.get("missing_protected_terms", []))
            weight = min(2.0, max(0.85, 1.0 + 0.6 * (1.0 - reward) + 0.2 * protected))
        return {"input_features": np.asarray(features, dtype=np.float32),
                "labels": labels, "weight": weight}

    def __iter__(self):
        if self.auxiliary_source_rows and self.source_fractions:
            while True:
                draw = random.random()
                cumulative = 0.0
                selected = None
                for rows, fraction in zip(self.auxiliary_source_rows, self.source_fractions):
                    cumulative += fraction
                    if draw < cumulative:
                        selected = rows
                        break
                if selected is None:
                    selected = self.rows
                yield self.encode_row(random.choice(selected))
        elif self.auxiliary_rows and self.auxiliary_fraction > 0:
            while True:
                source = (self.auxiliary_rows
                          if random.random() < self.auxiliary_fraction else self.rows)
                yield self.encode_row(random.choice(source))
        else:
            order = list(range(len(self.rows)))
            while True:
                random.shuffle(order)
                for index in order:
                    yield self.encode_row(self.rows[index])


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
    ap.add_argument("--manifest", type=Path, action="append", required=True,
                    help="training manifest; repeat to combine independently audited sources")
    ap.add_argument("--sqlite-manifest", type=Path, action="append",
                    help="optional local SQLite audio/target manifest; repeat to mix private sources")
    ap.add_argument("--sqlite-sample-weight", type=float, default=1.0,
                    help="weight assigned to rows read from --sqlite-manifest")
    ap.add_argument("--sqlite-sample-fraction", type=float, default=0.0,
                    help="optional target fraction for SQLite rows in streaming training")
    ap.add_argument("--sqlite-source-fraction", type=float, action="append",
                    help="target share for each repeated --sqlite-manifest, in the same order")
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--resume-from-checkpoint", type=Path,
                    help="resume Trainer state from an existing checkpoint directory")
    ap.add_argument("--init-adapter", type=Path,
                    help="continue an existing compatible LoRA adapter instead of starting fresh")
    ap.add_argument("--steps", type=int, default=250)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--learning-rate", type=float, default=1e-5)
    ap.add_argument("--streaming", action="store_true",
                    help="generate features per batch; requires a finite --steps")
    ap.add_argument("--no-augment", action="store_true",
                    help="disable waveform perturbations for a controlled acoustic experiment")
    ap.add_argument("--pre-split", action="store_true",
                    help="all manifest rows are training data; splits are managed upstream")
    args = ap.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this training run")
    random.seed(SEED)
    if args.sqlite_sample_fraction > 0 and not args.sqlite_manifest:
        raise ValueError("--sqlite-sample-fraction requires --sqlite-manifest")
    if not math.isfinite(args.sqlite_sample_fraction) or not 0 <= args.sqlite_sample_fraction < 1:
        raise ValueError("--sqlite-sample-fraction must be in [0, 1)")
    source_fractions = args.sqlite_source_fraction
    if source_fractions is not None:
        if args.sqlite_sample_fraction > 0:
            raise ValueError("choose either --sqlite-sample-fraction or per-source fractions")
        if len(source_fractions) != len(args.sqlite_manifest or []):
            raise ValueError("pass one --sqlite-source-fraction per --sqlite-manifest")
        if (any(not math.isfinite(value) or not 0 < value < 1 for value in source_fractions)
                or sum(source_fractions) >= 1):
            raise ValueError("per-source fractions must be positive and sum to less than 1")
    rows = []
    sqlite_rows = []
    sqlite_source_rows = []
    for manifest in args.manifest:
        if not manifest.is_file():
            raise FileNotFoundError(f"training manifest does not exist: {manifest}")
        rows.extend(json.loads(x) for x in manifest.read_text().splitlines() if x.strip())
    if not rows:
        raise ValueError("training manifests contain no examples")
    if args.sqlite_manifest:
        if not math.isfinite(args.sqlite_sample_weight) or args.sqlite_sample_weight <= 0:
            raise ValueError("--sqlite-sample-weight must be positive")
        for manifest in args.sqlite_manifest:
            if not manifest.is_file():
                raise FileNotFoundError("SQLite training manifest does not exist")
            connection = sqlite3.connect(f"file:{manifest.resolve()}?mode=ro", uri=True)
            try:
                columns = {item[1] for item in connection.execute("PRAGMA table_info(examples)")}
                if not {"id", "audio_path", "target_text"} <= columns:
                    raise ValueError("SQLite examples table has an incompatible schema")
                weighted = "sample_weight" in columns
                query = ("SELECT audio_path, target_text, sample_weight FROM examples ORDER BY id"
                         if weighted else
                         "SELECT audio_path, target_text FROM examples ORDER BY id")
                extra = connection.execute(query).fetchall()
            finally:
                connection.close()
            if not extra:
                raise ValueError("SQLite training manifest contains no examples")
            source_rows = []
            for item in extra:
                audio_path, target_text = item[:2]
                weight = item[2] if weighted else args.sqlite_sample_weight
                if (not Path(audio_path).is_file() or not isinstance(target_text, str)
                        or not target_text.strip() or not isinstance(weight, (int, float))
                        or not math.isfinite(weight) or weight <= 0):
                    raise ValueError("SQLite training manifest contains invalid audio, target, or weight")
                row = {"audio_path": audio_path, "text": target_text,
                       "sample_weight": float(weight)}
                sqlite_rows.append(row)
                source_rows.append(row)
            sqlite_source_rows.append(source_rows)
        if args.sqlite_sample_fraction > 0:
            if not args.streaming:
                raise ValueError("--sqlite-sample-fraction requires --streaming")
            if not rows or not sqlite_rows:
                raise ValueError("source-controlled sampling needs real and SQLite rows")
        elif source_fractions is not None:
            if not args.streaming:
                raise ValueError("per-source SQLite sampling requires --streaming")
            if not rows or len(sqlite_source_rows) != len(source_fractions):
                raise ValueError("per-source sampling needs real rows and all SQLite sources")
        else:
            rows.extend(sqlite_rows)
    if args.pre_split:
        train_rows, eval_rows = rows, None
    else:
        random.Random(SEED).shuffle(rows)
        train_rows, eval_rows = rows[:-100], rows[-100:]
    processor = WhisperProcessor.from_pretrained(str(args.model), language="english", task="transcribe")
    if args.streaming:
        if args.steps <= 0:
            raise ValueError("--streaming requires a positive --steps")
        auxiliary_rows = sqlite_rows if args.sqlite_sample_fraction > 0 else None
        sampled_sources = sqlite_source_rows if source_fractions is not None else None
        train = StreamingRows(train_rows, processor, not args.no_augment,
                              auxiliary_rows=auxiliary_rows,
                              auxiliary_fraction=args.sqlite_sample_fraction,
                              auxiliary_source_rows=sampled_sources,
                              source_fractions=source_fractions)
        evaluation = None
    else:
        train = make_dataset(train_rows, processor, not args.no_augment)
        evaluation = make_dataset(eval_rows, processor, False) if eval_rows is not None else None
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = WhisperForConditionalGeneration.from_pretrained(
        str(args.model), torch_dtype=dtype, low_cpu_mem_usage=True)
    model.config.forced_decoder_ids = None
    model.config.suppress_tokens = []
    model.config.use_cache = False
    if args.init_adapter:
        model = PeftModel.from_pretrained(model, str(args.init_adapter), is_trainable=True)
    else:
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
        # Keep long unattended runs observable without emitting a high-rate
        # progress-bar stream that can interfere with supervising terminals.
        disable_tqdm=True,
        remove_unused_columns=False, label_names=["labels"], seed=SEED,
    )
    trainer = WeightedTrainer(model=model, args=training, train_dataset=train,
                              eval_dataset=evaluation, data_collator=Collator(processor),
                              processing_class=processor)
    if args.resume_from_checkpoint:
        checkpoint = args.resume_from_checkpoint
        if not checkpoint.is_dir() or not (checkpoint / "trainer_state.json").is_file():
            raise ValueError("--resume-from-checkpoint must name a complete Trainer checkpoint")
        trainer.train(resume_from_checkpoint=str(checkpoint))
    else:
        trainer.train()
    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(args.out / "adapter"))
    processor.save_pretrained(str(args.out / "adapter"))
    print(f"saved Whisper adapter: {args.out / 'adapter'}")


if __name__ == "__main__":
    main()
