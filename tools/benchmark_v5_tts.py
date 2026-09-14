#!/usr/bin/env python3
"""Numeric-only CPU benchmark for a local Kokoro ONNX TTS artifact."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro

CASES = (
    "Hello, this is a local voice test.",
    "Open the browser and explain the next step.",
    "HTML, CSS, MCP, CTC, Celsius, and pharmacokinetics.",
    "Please make a short numbered list for tomorrow.",
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--voices", type=Path, required=True)
    ap.add_argument("--voice", default="af_sarah")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    tts = Kokoro(str(args.model), str(args.voices))
    # kokoro-onnx versions that target the older export choose int32 for
    # speed whenever the input is named input_ids; the current quantized
    # export declares float32. Normalize that one feed at the benchmark seam.
    session = tts.sess
    class SessionCompat:
        def get_inputs(self):
            return session.get_inputs()

        def run(self, names, inputs):
            if "speed" in inputs:
                inputs = dict(inputs)
                inputs["speed"] = np.asarray(inputs["speed"], dtype=np.float32)
            return session.run(names, inputs)
    tts.sess = SessionCompat()
    timings = []
    durations = []
    for text in CASES:
        start = time.perf_counter()
        audio, sample_rate = tts.create(text, voice=args.voice, speed=1.0)
        elapsed = time.perf_counter() - start
        timings.append(elapsed)
        durations.append(np.asarray(audio).size / sample_rate)
    metrics = {
        "cases": len(CASES), "sample_rate": sample_rate,
        "model_bytes": args.model.stat().st_size,
        "voice": args.voice, "total_audio_seconds": sum(durations),
        "total_synthesis_seconds": sum(timings),
        "real_time_factor": sum(timings) / max(sum(durations), 1e-9),
        "p50_seconds": float(np.percentile(timings, 50)),
        "p95_seconds": float(np.percentile(timings, 95)),
    }
    args.out.write_text(json.dumps(metrics) + "\n")
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
