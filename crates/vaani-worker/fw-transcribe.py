#!/usr/bin/env python3
"""faster-whisper transcription sidecar for vaani-worker.

Usage: fw-transcribe.py <model_dir> <wav> <lang> [--prompt TEXT] [--beam N]
                            [--device cuda|cpu]

Prints the transcript to stdout (single write, no trailing newline needed).
Audio and transcript text are never logged. Text travels via stdout only;
the initial prompt (user-configured vocabulary) arrives via argv like
whisper.cpp's --prompt.
"""

import sys
import os

# Fully local like Cozy's env.sh: never touch the network.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 3:
        sys.stderr.write(
            "usage: fw-transcribe.py <model_dir> <wav> <lang> "
            "[--prompt TEXT] [--beam N] [--device cuda|cpu]\n"
        )
        raise SystemExit(2)
    model_dir, wav_path, lang = args[0], args[1], args[2]
    # Default initial prompt: Cozy's validated Hindi-word hint. An explicit
    # --prompt (user vocabulary) overrides it. Never empty for the cozy
    # fine-tune: the prompt is part of its measured accuracy recipe.
    prompt = ("Indian English. HTML CSS MCP CTC CUDA LLM STT WER QLoRA VLM "
              "Celsius narcotics acrobat glioblastoma pharmacokinetics.")
    # Beam 5 is the measured V5 decoding improvement for the existing cozy
    # checkpoint.  Callers can still pass --beam 1 for the lowest latency.
    beam = 5
    device = "cuda"
    i = 3
    while i < len(args):
        if args[i] == "--prompt":
            i += 1
            if i < len(args) and args[i]:
                prompt = args[i]
        elif args[i] == "--beam":
            i += 1
            try:
                beam = int(args[i]) if i < len(args) else 1
            except ValueError:
                beam = 1
        elif args[i] == "--device":
            i += 1
            device = args[i] if i < len(args) else "cuda"
        i += 1

    from faster_whisper import WhisperModel

    try:
        model = WhisperModel(
            model_dir, device=device, device_index=0,
            compute_type="int8_float16",
        )
    except Exception:
        model = WhisperModel(model_dir, device="cpu", compute_type="int8")

    kwargs = {
        "language": lang or None,
        "beam_size": max(1, beam),
        "condition_on_previous_text": False,
    }
    if prompt:
        kwargs["initial_prompt"] = prompt

    segments, _info = model.transcribe(wav_path, **kwargs)
    kept = [
        s.text.strip()
        for s in segments
        if s.text.strip() and float(getattr(s, "no_speech_prob", 0.0)) <= 0.7
    ]
    sys.stdout.write(" ".join(kept))


main()
