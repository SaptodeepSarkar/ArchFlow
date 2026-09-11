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
    prompt = ("Cozy assistant. Romanized Hindi words: aaj kaisa karo yaar "
              "accha theek thoda nahi bas arre.")
    beam = 1
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
        if device == "cpu":
            raise
        model = WhisperModel(model_dir, device="cpu", compute_type="int8")

    kwargs = {"language": lang or None, "beam_size": max(1, beam)}
    if prompt:
        kwargs["initial_prompt"] = prompt
    segments, _info = model.transcribe(wav_path, **kwargs)
    sys.stdout.write(" ".join(s.text.strip() for s in segments).strip())


main()
