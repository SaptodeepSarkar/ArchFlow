#!/usr/bin/env python3
"""Persistent faster-whisper sidecar for Vaani streaming transcription.

The fine-tuned CT2 model loads once (~4 s) and stays resident, so every
dictation chunk transcribes in ~0.3 s instead of paying a reload per call.
The controller reaps this process after configured idle seconds (economy:
no VRAM held while you are not dictating).

Usage: fw-server.py <model_dir> [--device cuda|cpu] [--beam N]

Protocol (pipes, newline JSON; audio/text never logged):
  stdin  {"id": N, "wav": "/path/in.wav", "lang": "en"|"", "prompt": "...",
          "task": "transcribe"|"translate"}
  stdout {"id": N, "text": "..."}  or  {"id": N, "error": "..."}
First stdout line after startup is {"ready": true}.
"""

import json
import sys


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.stderr.write("usage: fw-server.py <model_dir> [--device cuda|cpu] [--beam N]\n")
        raise SystemExit(2)
    model_dir = args[0]
    device = "cuda"
    beam = 1
    i = 1
    while i < len(args):
        if args[i] == "--device":
            i += 1
            device = args[i] if i < len(args) else "cuda"
        elif args[i] == "--beam":
            i += 1
            try:
                beam = int(args[i]) if i < len(args) else 1
            except ValueError:
                beam = 1
        i += 1

    from faster_whisper import WhisperModel

    try:
        model = WhisperModel(
            model_dir, device=device, device_index=0,
            compute_type="int8_float16",
        )
    except Exception:
        if device == "cpu":
            raise
        model = WhisperModel(model_dir, device="cpu", compute_type="int8")

    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()

    stdin = sys.stdin
    while True:
        line = stdin.readline()
        if not line:
            break  # controller closed stdin: exit, freeing VRAM
        try:
            job = json.loads(line)
        except ValueError:
            continue
        jid = job.get("id")
        try:
            kwargs = {
                "language": job.get("lang") or None,
                "beam_size": max(1, beam),
                "task": job.get("task") or "transcribe",
            }
            if job.get("prompt"):
                kwargs["initial_prompt"] = job["prompt"]
            segments, _info = model.transcribe(job["wav"], **kwargs)
            text = " ".join(s.text.strip() for s in segments).strip()
            sys.stdout.write(json.dumps({"id": jid, "text": text}) + "\n")
        except Exception as exc:  # noqa: BLE001 - must survive bad jobs
            sys.stdout.write(json.dumps({"id": jid, "error": str(exc)}) + "\n")
        sys.stdout.flush()


main()
