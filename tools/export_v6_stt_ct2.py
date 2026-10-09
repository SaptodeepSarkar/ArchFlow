#!/usr/bin/env python3
"""Merge a V6 Whisper LoRA candidate and export an isolated CT2 artifact.

Never overwrites an existing destination and never prints a transcript. The
optional smoke decode reports only success, segment count, and elapsed time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True,
                        help="fused Hugging Face Whisper checkpoint")
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--smoke-audio", type=Path)
    parser.add_argument("--smoke-device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if not (args.adapter / "adapter_config.json").is_file():
        raise SystemExit("adapter_config.json is missing")
    if not (args.adapter / "adapter_model.safetensors").is_file():
        raise SystemExit("adapter weights are missing")
    if not args.model.is_dir():
        raise SystemExit("base checkpoint is missing")
    if args.smoke_audio and not args.smoke_audio.is_file():
        raise SystemExit("smoke audio is missing")

    config = json.loads((args.adapter / "adapter_config.json").read_text(encoding="utf-8"))
    declared_base = config.get("base_model_name_or_path")
    if declared_base and Path(declared_base).resolve() != args.model.resolve():
        raise SystemExit("adapter and requested base model do not match")
    out_root = args.out_root.expanduser().resolve()
    if out_root.exists():
        raise SystemExit("refusing to overwrite an existing export directory")
    out_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out_root.name}.export-",
                                     dir=out_root.parent) as temporary:
        staged_root = Path(temporary) / "export"
        staged_root.mkdir()
        hf_out = staged_root / "hf-merged"
        ct2_out = staged_root / "ct2-int8-float16"

        import torch
        from peft import PeftModel
        from transformers import WhisperForConditionalGeneration, WhisperProcessor

        base = WhisperForConditionalGeneration.from_pretrained(
            str(args.model), torch_dtype=torch.float32, low_cpu_mem_usage=True)
        adapted = PeftModel.from_pretrained(base, str(args.adapter))
        merged = adapted.merge_and_unload()
        merged.config.forced_decoder_ids = None
        merged.config.suppress_tokens = []
        hf_out.mkdir()
        merged.save_pretrained(hf_out, safe_serialization=True)
        WhisperProcessor.from_pretrained(str(args.model)).save_pretrained(hf_out)

        from ctranslate2.converters import TransformersConverter
        TransformersConverter(str(hf_out), load_as_float16=True).convert(
            str(ct2_out), quantization="int8_float16")

        result = {
            "model": out_root.name,
            "base": str(args.model),
            "adapter": str(args.adapter),
            "ct2_model_sha256": hashlib.sha256((ct2_out / "model.bin").read_bytes()).hexdigest(),
            "ct2_bytes": (ct2_out / "model.bin").stat().st_size,
        }
        if args.smoke_audio:
            from faster_whisper import WhisperModel
            start = time.monotonic()
            compute_type = "int8_float16" if args.smoke_device == "cuda" else "int8"
            model = WhisperModel(str(ct2_out), device=args.smoke_device, compute_type=compute_type)
            segments, _ = model.transcribe(str(args.smoke_audio), language="en", beam_size=5,
                                           condition_on_previous_text=False)
            segment_count = sum(1 for _ in segments)
            result.update({"cuda_smoke_ok": segment_count > 0,
                           "smoke_segments": segment_count,
                           "smoke_seconds": round(time.monotonic() - start, 3)})
            if segment_count == 0:
                raise SystemExit("CT2 smoke decode returned no segments")
        (staged_root / "export.json").write_text(json.dumps(result, indent=2) + "\n",
                                                 encoding="utf-8")
        if out_root.exists():
            raise SystemExit("export destination appeared during conversion; refusing to overwrite")
        os.rename(staged_root, out_root)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
