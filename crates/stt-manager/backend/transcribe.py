#!/usr/bin/env python3
"""Vaani STT backend: Vosk word stream over 16kHz mono audio.

Protocol on stdout (vosk LOG lines stay on stderr):
  W <t_sec> <word>          one final word, streamed as decoded
  P <t_sec> <phrase>        current partial phrase (live UI), empty = cleared
  DONE audio=<s> infer=<s> words=<n> model=<dir>

Input: --wav PATH (16kHz mono wav), --stdin (whole raw s16le 16k mono), or
--stream (raw s16le 16k mono fed incrementally; emits P partials while the
caller is still recording, so the UI can show words live).
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


def stream(rec, out):
    """Incremental stdin feed: P partials while audio arrives, W for finals.

    Reads with read1 so a partial is emitted as soon as bytes are available
    (the caller is still recording); read() would block for a full chunk.
    Returns (words, infer_secs, audio_secs).
    """
    stdin = sys.stdin.buffer
    audio_secs = 0.0
    infer = 0.0
    words = 0
    while True:
        data = stdin.read1(3200)
        if not data:
            break
        n = len(data) & ~1
        if n == 0:
            continue
        audio_secs += n / (2 * SAMPLE_RATE)
        s = time.time()
        final = rec.AcceptWaveform(data[:n])
        infer += time.time() - s
        if final:
            for w in json.loads(rec.Result()).get("result", []):
                out.write(f"W {float(w.get('start', audio_secs)):.2f} {w['word']}\n")
                words += 1
            out.write("P 0 \n")
        else:
            out.write(
                f"P {audio_secs:.2f} "
                f"{json.loads(rec.PartialResult()).get('partial', '')}\n"
            )
        out.flush()
    for w in json.loads(rec.FinalResult()).get("result", []):
        out.write(f"W {float(w.get('start', audio_secs)):.2f} {w['word']}\n")
        words += 1
    out.write("P 0 \n")
    out.flush()
    return words, infer, audio_secs


def main():
    args = sys.argv[1:]
    mode = "wav"
    if "--wav" in args:
        wav_path = args[args.index("--wav") + 1]
    elif "--stream" in args:
        wav_path, mode = None, "stream"
    elif "--stdin" in args:
        wav_path, mode = None, "stdin"
    else:
        print("usage: transcribe.py --wav PATH | --stdin | --stream", file=sys.stderr)
        return 2
    use_stdin = mode == "stdin"

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

    if mode == "stream":
        words, infer, audio_secs = stream(rec, sys.stdout)
        sys.stdout.write(
            f"DONE audio={audio_secs:.2f} infer={infer:.2f} words={words} model={model_dir}\n"
        )
        sys.stdout.flush()
        return 0

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
