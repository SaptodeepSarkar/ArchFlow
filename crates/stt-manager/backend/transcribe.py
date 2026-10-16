#!/usr/bin/env python3
"""Vaani STT backend: Vosk word stream over 16kHz mono audio.

Protocol on stdout (vosk LOG lines stay on stderr):
  W <t_sec> <word>          one final word, streamed as decoded
  DONE audio=<s> infer=<s> words=<n> model=<dir>

Input: --wav PATH (16kHz mono wav) or --stdin (raw s16le 16k mono on stdin).
Exit nonzero on any failure; details go to stderr.
"""

import json
import os
import sys
import time
import wave

CHUNK_FRAMES = 4000
SAMPLE_RATE = 16000


def feed(rec, frames, out):
    """Push PCM bytes; emit one W line per decoded word. Returns infer seconds."""
    words = 0
    infer = 0.0
    t0 = 0  # chunk start time in seconds
    for pcm in frames:
        t = t0
        t0 += len(pcm) / (2 * SAMPLE_RATE)
        s = time.time()
        final = rec.AcceptWaveform(pcm)
        infer += time.time() - s
        if final:
            for w in json.loads(rec.Result()).get("result", []):
                out.write(f"W {float(w.get('start', t)):.2f} {w['word']}\n")
                words += 1
            out.flush()
    return words, infer


def main():
    args = sys.argv[1:]
    if "--wav" in args:
        wav_path = args[args.index("--wav") + 1]
        use_stdin = False
    elif "--stdin" in args:
        wav_path, use_stdin = None, True
    else:
        print("usage: transcribe.py --wav PATH | --stdin", file=sys.stderr)
        return 2

    model_dir = os.environ.get(
        "VAANI_STT_MODEL",
        "/home/saptodeep/Projects/Kyuma/models/vosk-model-small-en-us-0.15",
    )
    if not os.path.isdir(model_dir):
        print(f"model dir not found: {model_dir}", file=sys.stderr)
        return 1

    from vosk import KaldiRecognizer, Model

    model = Model(model_dir)
    rec = KaldiRecognizer(model, SAMPLE_RATE)
    rec.SetWords(True)

    if use_stdin:
        data = sys.stdin.buffer.read()
        n = len(data) & ~1
        frames = [data[i : i + 8000] for i in range(0, n, 8000) if data[i : i + 8000]]
        audio_secs = n / (2 * SAMPLE_RATE)
    else:
        try:
            wf = wave.open(wav_path, "rb")
        except (OSError, wave.Error) as e:
            print(f"bad wav {wav_path}: {e}", file=sys.stderr)
            return 2
        with wf:
            if wf.getframerate() != SAMPLE_RATE or wf.getnchannels() != 1:
                print(
                    f"{wav_path}: need 16kHz mono, "
                    f"got {wf.getframerate()}Hz x{wf.getnchannels()}",
                    file=sys.stderr,
                )
                return 2
            audio_secs = wf.getnframes() / wf.getframerate()
            frames = []
            while True:
                d = wf.readframes(CHUNK_FRAMES)
                if not d:
                    break
                frames.append(d)

    words, infer = feed(rec, frames, sys.stdout)
    s = time.time()
    for w in json.loads(rec.FinalResult()).get("result", []):
        sys.stdout.write(f"W {float(w.get('start', audio_secs)):.2f} {w['word']}\n")
        words += 1
    infer += time.time() - s
    sys.stdout.write(
        f"DONE audio={audio_secs:.2f} infer={infer:.2f} words={words} model={model_dir}\n"
    )
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
