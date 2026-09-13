#!/usr/bin/env python3
"""Evaluate a Whisper/PEFT adapter against an explicit JSONL manifest."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--adapter", type=Path, required=True)
    ap.add_argument("--cozy-root", type=Path, required=True)
    args = ap.parse_args()
    sys.path.insert(0, str(args.cozy_root / "scripts"))
    from common import BASE_MODEL, english_normalizer, wer  # type: ignore

    import librosa
    import torch
    from peft import PeftModel
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    rows = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
    processor = WhisperProcessor.from_pretrained(BASE_MODEL, language="english", task="transcribe")
    model = WhisperForConditionalGeneration.from_pretrained(BASE_MODEL, torch_dtype=torch.float16).to("cuda")
    model = PeftModel.from_pretrained(model, str(args.adapter))
    model.eval()
    norm = english_normalizer()
    refs, hyps = [], []
    with torch.inference_mode():
        for start in range(0, len(rows), 4):
            chunk = rows[start:start + 4]
            feats = [processor(librosa.load(r["audio_path"], sr=16000, mono=True)[0],
                               sampling_rate=16000, return_tensors="pt").input_features[0]
                     for r in chunk]
            ids = model.generate(torch.stack(feats).half().to("cuda"), language="english",
                                 task="transcribe", max_new_tokens=200, do_sample=False)
            refs.extend(norm(r["text"]) for r in chunk)
            hyps.extend(norm(h) for h in processor.batch_decode(ids, skip_special_tokens=True))
    print(f"{args.manifest.name}: {wer(hyps, refs):.2f}% WER ({len(rows)} clips)")


if __name__ == "__main__":
    main()
