#!/usr/bin/env python3
"""Create paired base/V4 STT hypotheses and bounded word-level rewards.

The input manifest must contain ``audio_path`` and either ``text`` or
``reference``. References are treated as labels only; they are never replaced
by a model hypothesis. Model weights and generated reports belong outside Git.
"""
from __future__ import annotations

import argparse
import json
import re
from difflib import SequenceMatcher
from pathlib import Path


def words(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)?", value.lower())


def alignment(reference: str, hypothesis: str) -> dict:
    ref, hyp = words(reference), words(hypothesis)
    matcher = SequenceMatcher(a=ref, b=hyp, autojunk=False)
    errors = []
    substitutions = deletions = insertions = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            substitutions += max(i2 - i1, j2 - j1)
            kind = "substitute"
        elif tag == "delete":
            deletions += i2 - i1
            kind = "delete"
        else:
            insertions += j2 - j1
            kind = "insert"
        errors.append({"type": kind, "reference_words": ref[i1:i2],
                       "hypothesis_words": hyp[j1:j2],
                       "reference_position": i1})
    total = max(1, len(ref))
    wer = (substitutions + deletions + insertions) / total
    # Reward is deliberately bounded and monotonic with word correctness.
    reward = max(-1.0, min(1.0, 1.0 - wer))
    return {"reference_words": len(ref), "wer": wer,
            "substitutions": substitutions, "deletions": deletions,
            "insertions": insertions, "errors": errors, "reward": reward}


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            row["reference"] = row.get("text") or row.get("reference") or ""
            rows.append(row)
    return rows


def read_wav(path: str):
    import wave
    import numpy as np
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
        raise ValueError(f"unsupported PCM width {width}: {path}")
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != 16000:
        target = max(1, round(len(audio) * 16000 / rate))
        audio = np.interp(np.linspace(0, len(audio) - 1, target),
                          np.arange(len(audio)), audio)
    return audio.astype("float32")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--base-model", type=Path, required=True)
    ap.add_argument("--v4-model", type=Path, required=True,
                    help="V4 PEFT adapter directory")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    rows = load_rows(args.manifest)
    if args.limit:
        rows = rows[:args.limit]
    processor = WhisperProcessor.from_pretrained(str(args.base_model),
                                                  language="english", task="transcribe")
    dtype = torch.float16 if args.device.startswith("cuda") else torch.float32
    base = WhisperForConditionalGeneration.from_pretrained(
        str(args.base_model), torch_dtype=dtype).to(args.device).eval()
    v4 = PeftModel.from_pretrained(base, str(args.v4_model)).eval()

    def decode(model, batch):
        features = [processor(read_wav(row["audio_path"]), sampling_rate=16000).input_features[0]
                    for row in batch]
        with torch.inference_mode():
            ids = model.generate(torch.tensor(features, dtype=dtype, device=args.device),
                                 language="english", task="transcribe",
                                 max_new_tokens=224, do_sample=False)
        return processor.batch_decode(ids, skip_special_tokens=True)

    output = []
    for start in range(0, len(rows), args.batch_size):
        batch = rows[start:start + args.batch_size]
        base_hyp = decode(base, batch)
        v4_hyp = decode(v4, batch)
        for row, base_text, v4_text in zip(batch, base_hyp, v4_hyp):
            base_score = alignment(row["reference"], base_text)
            v4_score = alignment(row["reference"], v4_text)
            output.append({"audio_path": row["audio_path"],
                           "reference": row["reference"],
                           "base_hypothesis": base_text,
                           "v4_hypothesis": v4_text,
                           "base": base_score, "v4": v4_score,
                           "reward_delta_v4_minus_base":
                               v4_score["reward"] - base_score["reward"]})
        if len(output) % 100 == 0:
            print(f"processed={len(output)}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n"
                                         for row in output))
    print(f"wrote={len(output)} path={args.out}")


if __name__ == "__main__":
    main()
