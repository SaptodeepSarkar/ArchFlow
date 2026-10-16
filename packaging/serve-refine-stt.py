#!/usr/bin/env python3
"""Resident re-decode server for Vaani's fine-tuned Whisper.

Why a resident server: the daemon spawns its STT backend per utterance, and
loading an 809M-parameter model per utterance would add seconds to every run.
This holds the model once and answers over HTTP, the same shape as the
formatter's llama-server.

It serves the *fine-tuned* weights (base + LoRA adapter), and only ever runs
after the streaming pass has finished, so the RTF ~0.09 streaming budget is
untouched: the fast Vosk model emits words while the user speaks, and this model
re-decodes the finished utterance.

Endpoints:
  GET  /health      -> {"status":"ok","model":...,"adapter":...}
  POST /transcribe  -> body = raw s16le 16kHz mono PCM
                       {"text":..., "words":[{"w":...,"t":...}], "audio":s, "infer":s}

Run:
  serve-refine-stt.py --adapter <lora dir> --port 8083 [--device cuda] [--base <id>]
Without --adapter it serves the plain base model (useful as a control).

shortcut: words carry t=0 because word-level timestamps need cross-attention
for every layer, which asks for ~4.5 GB -- more than this laptop's 6 GB card has
once the formatter is resident. The live loop only consumes the text, so nothing
needs the times today; compute them if a UI ever wants per-word highlighting.
"""
from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_CHUNK_SECONDS = 60  # MAX_RECORD_SECS in the daemon; reject anything longer
SAMPLE_RATE = 16000
WINDOW_SECONDS = 30  # Whisper's receptive field; longer audio is windowed

_state: dict = {}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):  # keep stdout clean; the daemon reads only JSON
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (http.server's naming)
        if self.path == "/health":
            self._send(200, {"status": "ok", "model": _state.get("model"),
                             "adapter": _state.get("adapter")})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/transcribe":
            self._send(404, {"error": "not found"})
            return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        n -= n % 2
        if n < 2 * SAMPLE_RATE // 4:
            self._send(400, {"error": f"too little audio: {n} bytes"})
            return
        audio_secs = n / (2 * SAMPLE_RATE)
        if audio_secs > MAX_CHUNK_SECONDS:
            self._send(413, {"error": f"{audio_secs:.1f}s exceeds {MAX_CHUNK_SECONDS}s"})
            return
        try:
            text, infer = transcribe(raw[:n])
        except Exception as exc:  # noqa: BLE001 - report, never kill the server
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})
            return
        self._send(200, {"text": text, "words": [{"w": w, "t": 0.0}
                                                 for w in text.split()],
                         "audio": round(audio_secs, 2), "infer": round(infer, 2)})


def transcribe(pcm: bytes) -> tuple[str, float]:
    """Run the model over PCM (s16le, 16k, mono) -> (text, infer secs).

    Featurising with `padding="max_length"` is the same path the training and
    evaluation scripts use, and the shape the STT regression test pins: Whisper
    needs a fixed 3000-frame mel for every clip.

    `numpy` is imported here so `--help` stays dependency-free, which is what the
    packaging gate checks.
    """
    import numpy as np
    import torch

    audio = np.frombuffer(pcm, dtype="<i2").astype("float32") / 32768.0
    step = WINDOW_SECONDS * SAMPLE_RATE
    windows = [audio[i:i + step] for i in range(0, len(audio), step)] or [audio]
    proc, core = _state["proc"], _state["core"]
    device, dtype = _state["device"], torch.float16

    texts, infer = [], 0.0
    with _state["lock"]:
        for win in windows:
            feats = proc(win, sampling_rate=SAMPLE_RATE, return_tensors="pt",
                         padding="max_length").input_features
            t0 = time.time()
            ids = core.generate(input_features=feats.to(device, dtype=dtype),
                                max_new_tokens=225, language="en", task="transcribe")
            infer += time.time() - t0
            texts.append(proc.tokenizer.batch_decode(ids, skip_special_tokens=True)[0].strip())
    return " ".join(t for t in texts if t).strip(), infer


def main() -> int:
    ap = argparse.ArgumentParser(
        # Show the defaults: the port and device here have to line up with the
        # daemon's VAANI_STT_REFINE_ENDPOINT / VAANI_STT_REFINE_PYTHON.
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    ap.add_argument("--base", default="openai/whisper-large-v3-turbo",
                    help="base Whisper model id or local path")
    ap.add_argument("--adapter", default="",
                    help="LoRA adapter dir; empty serves the plain base model")
    ap.add_argument("--host", default="127.0.0.1", help="bind address")
    ap.add_argument("--port", type=int, default=8083,
                    help="bind port; must match the daemon's "
                         "VAANI_STT_REFINE_ENDPOINT")
    ap.add_argument("--device", default="cuda", help="cuda or cpu")
    args = ap.parse_args()

    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    proc = WhisperProcessor.from_pretrained(args.base)
    model = WhisperForConditionalGeneration.from_pretrained(
        args.base, torch_dtype=torch.float16, low_cpu_mem_usage=True)
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)
        # PeftModel -> LoraModel -> WhisperForConditionalGeneration: generate()
        # lives on the inner model, and unwrapping keeps VRAM at ~2.5 GB instead
        # of the ~4.5 GB the attention-returning timestamp path needs.
        model = model.base_model.model
    model.to(args.device)
    model.eval()

    _state.update(proc=proc, core=model, device=args.device, lock=threading.Lock(),
                  model=args.base, adapter=args.adapter or None)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"step": "ready", "host": args.host, "port": args.port,
                      "model": args.base, "adapter": args.adapter or None,
                      "device": args.device}), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
