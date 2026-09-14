#!/usr/bin/env python3
"""Evaluate a Whisper LoRA adapter on the fixed V5 held-out split."""
from __future__ import annotations

import argparse
import hashlib
import re
import json
import random
import re
import time
import wave
from pathlib import Path

import numpy as np
import torch
from peft import PeftModel
from stt_feedback_loop import score
from transformers import WhisperForConditionalGeneration, WhisperProcessor

SEED = 20260914
SR = 16000


def norm(text: str) -> str:
    text = text.lower().replace("’", "'")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9']+", " ", text)).strip()


def load_audio(path: str) -> np.ndarray:
    with wave.open(path, "rb") as h:
        raw = h.readframes(h.getnframes())
        if h.getsampwidth() != 2:
            raise ValueError("only 16-bit PCM is supported")
        audio = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
        if h.getnchannels() > 1:
            audio = audio.reshape(-1, h.getnchannels()).mean(1)
        if h.getframerate() != SR:
            n = max(1, round(len(audio) * SR / h.getframerate()))
            audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)
        return audio.astype("float32")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", type=Path, required=True)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--adapter", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--beams", type=int, default=5)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--initial-prompt", default="")
    ap.add_argument("--initial-prompt-file", type=Path)
    ap.add_argument("--limit", type=int, default=100)
    args = ap.parse_args()
    rows = [json.loads(x) for x in args.report.read_text().splitlines() if x.strip()]
    random.Random(SEED).shuffle(rows)
    rows = rows[-min(100, max(1, args.limit)):]
    processor = WhisperProcessor.from_pretrained(str(args.model), language="english", task="transcribe")
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = WhisperForConditionalGeneration.from_pretrained(str(args.model), torch_dtype=dtype).to("cuda")
    model = PeftModel.from_pretrained(model, str(args.adapter)).eval()
    model.config.forced_decoder_ids = None
    model.config.suppress_tokens = []
    prompt_ids = None
    prompt = args.initial_prompt
    if args.initial_prompt_file:
        prompt = args.initial_prompt_file.read_text()
    if prompt:
        prompt_ids = processor.get_prompt_ids(prompt, return_tensors="pt").to("cuda")
    outputs = []
    elapsed = 0.0
    for start in range(0, len(rows), args.batch_size):
        chunk = rows[start:start + args.batch_size]
        feats = [processor(load_audio(r["audio_path"]), sampling_rate=SR,
                           return_tensors="pt").input_features[0] for r in chunk]
        batch = torch.stack(feats).to("cuda", dtype=dtype)
        t0 = time.perf_counter()
        with torch.inference_mode():
            ids = model.generate(batch, language="english", task="transcribe",
                                 num_beams=args.beams, do_sample=False,
                                 max_new_tokens=224, use_cache=True,
                                 prompt_ids=prompt_ids)
        elapsed += time.perf_counter() - t0
        texts = processor.batch_decode(ids, skip_special_tokens=True)
        for row, hyp in zip(chunk, texts):
            reference = row.get("reference", row.get("text", ""))
            literal = score(reference, hyp)
            normalized = score(norm(reference), norm(hyp))
            protected = re.findall(
                r"(?:https?://\S+|/[^\s]+|\b[A-Z][A-Z0-9]{1,}\b|\b\d+(?:\.\d+)?\b|Celsius|narcotics|acrobat|glioblastoma|pharmacokinetics|otorhinolaryngology)",
                reference,
            )
            missing = sum(term.lower() not in hyp.lower() for term in protected)
            outputs.append({
                "row_id": hashlib.sha256(row["audio_path"].encode()).hexdigest()[:16],
                "reference_words": len(norm(reference).split()),
                "literal_errors": len(literal["errors"]),
                "normalized_errors": len(normalized["errors"]),
                "normalized_wer": normalized["wer"],
                "protected_terms": len(protected), "missing_protected_terms": missing,
            })
        print(f"{min(start + len(chunk), len(rows))}/{len(rows)}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in outputs))
    print(json.dumps({"clips": len(outputs), "beams": args.beams,
                      "literal_mean_row_wer": sum(x["literal_errors"] / max(x["reference_words"], 1) for x in outputs) / len(outputs),
                      "normalized_mean_row_wer": sum(x["normalized_wer"] for x in outputs) / len(outputs),
                      "corpus_normalized_wer": sum(x["normalized_errors"] for x in outputs) / max(sum(x["reference_words"] for x in outputs), 1),
                      "decode_seconds": elapsed, "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
