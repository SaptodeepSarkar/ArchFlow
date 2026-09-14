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
import os
import sys

# Fully local like Cozy's env.sh: never touch the network (hub checks add
# seconds per load and fail offline). Set before importing faster-whisper.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.stderr.write("usage: fw-server.py <model_dir> [--device cuda|cpu] [--beam N]\n")
        raise SystemExit(2)
    model_dir = args[0]
    device = "cuda"
    # Beam 5 lowers held-out normalized WER for the production cozy prompt;
    # the explicit --beam flag remains available for a lower-latency profile.
    beam = 5
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
                # Each chunk stands alone: never continue a previous chunk's
                # output (runaway repetition), and drop non-speech segments
                # (silence padding hallucinations) by probability.
                "condition_on_previous_text": False,
            }
            if job.get("prompt"):
                kwargs["initial_prompt"] = job["prompt"]
            segments, _info = model.transcribe(job["wav"], **kwargs)
            kept = [
                s.text.strip()
                for s in segments
                if s.text.strip()
                and float(getattr(s, "no_speech_prob", 0.0)) <= 0.7
            ]
            text = " ".join(kept)
            sys.stdout.write(json.dumps({"id": jid, "text": text}) + "\n")
        except Exception as exc:  # noqa: BLE001 - must survive bad jobs
            sys.stdout.write(json.dumps({"id": jid, "error": str(exc)}) + "\n")
        sys.stdout.flush()


main()
