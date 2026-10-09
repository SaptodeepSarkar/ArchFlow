#!/usr/bin/env python3
"""Verify a local V6 CT2 artifact without printing recognized text."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    model_path = args.model / "model.bin"
    if not model_path.is_file() or not args.audio.is_file():
        raise SystemExit("CT2 model or smoke audio is missing")

    from faster_whisper import WhisperModel

    compute_type = "int8_float16" if args.device == "cuda" else "int8"
    started = time.monotonic()
    model = WhisperModel(str(args.model), device=args.device, compute_type=compute_type)
    segments, _ = model.transcribe(str(args.audio), language="en", beam_size=5,
                                   condition_on_previous_text=False)
    count = sum(1 for _ in segments)
    result = {
        "ok": count > 0,
        "device": args.device,
        "compute_type": compute_type,
        "segments": count,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "model_bytes": model_path.stat().st_size,
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
    }
    print(json.dumps(result, sort_keys=True))
    if count == 0:
        raise SystemExit("CT2 smoke decode returned no segments")


if __name__ == "__main__":
    main()
