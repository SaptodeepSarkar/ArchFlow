#!/usr/bin/env python3
"""Generate the hermetic smoke fixtures: 32 STT rows and 64 formatter rows.

Deterministic: rerunning overwrites the same bytes, so the committed JSONL and
the wavs cannot drift. The wavs are 2 s of digital silence (16 kHz mono PCM16)
because the smoke only checks shapes and resume, never accuracy.
"""

from __future__ import annotations

import argparse
import json
import os
import wave

SENTENCES = [
    "The quick brown fox jumps over the lazy dog.",
    "We should ship the update on Friday.",
    "Please send me the report by noon.",
    "The meeting moved to room 204.",
    "I will call you after lunch.",
    "Add the new user to the admin group.",
    "The build failed because the cache was stale.",
    "Let us review the numbers tomorrow morning.",
    "She said the deadline is the third of March.",
    "Turn the lights off before you leave.",
    "The server restarted twice during the demo.",
    "Keep the receipt in the blue folder.",
]

AUDIO_SECONDS = 2
SAMPLE_RATE = 16000


def write_silence(path, seconds=AUDIO_SECONDS, rate=SAMPLE_RATE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * int(seconds * rate))


def stt_rows(split, count, start):
    rows = []
    for i in range(count):
        index = start + i
        rows.append({
            "id": f"fx-stt-{index:04d}",
            "audio": f"audio/{split}/fx-stt-{index:04d}.wav",
            "text": SENTENCES[index % len(SENTENCES)],
            "speaker_id": f"spk-{split}-{i % 3}",
            "duration_s": float(AUDIO_SECONDS),
            "source": "fixture",
            "accent": "fixture",
        })
    return rows


def formatter_rows(split, count, start):
    rows = []
    for i in range(count):
        index = start + i
        clean = SENTENCES[index % len(SENTENCES)]
        kind = index % 5
        vocab = [["vaani", "Vaani"]] if index % 5 == 4 else []
        spoken = clean.replace("admin", "vaani") if vocab else clean
        target = clean.replace("admin", "Vaani") if vocab else clean
        low = spoken[0].lower() + spoken[1:]
        if kind == 0:  # filler removal
            source, ops = "umm so " + low.replace(" the ", " hmm the ", 1), ["delete"]
        elif kind == 1:  # repair
            source, ops = "we should, no sorry, " + low, ["delete", "restore"]
        elif kind == 2:  # casing + punctuation restore only
            source, ops = low.rstrip("."), ["restore"]
        elif kind == 3:  # identity pair
            source, ops = spoken, []
        else:  # replace
            source, ops = low.replace("vaani", "vanee"), ["replace"]
        numbers = [word for word in target.replace(".", "").split() if word.isdigit()]
        rows.append({
            "id": f"fx-fmt-{index:04d}",
            "seed_id": f"fx-seed-{index // 3:04d}",
            "input": source,
            "output": target,
            "ops": ops,
            "domain": ["note", "email", "chat", "command", "dictation"][index % 5],
            "protected_tokens": numbers + ([word for word in ("Friday", "March", "Vaani") if word in target]),
            "vocab": vocab,
            "variant": index % 3 + 1,
        })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures"))
    args = parser.parse_args()

    stt = {"train": stt_rows("train", 24, 1), "dev": stt_rows("dev", 8, 101)}
    os.makedirs(os.path.join(args.out, "stt"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "formatter"), exist_ok=True)
    for split, rows in stt.items():
        with open(os.path.join(args.out, "stt", f"{split}.jsonl"), "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
                write_silence(os.path.join(args.out, "stt", row["audio"]))

    fmt = {"train": formatter_rows("train", 48, 1), "dev": formatter_rows("dev", 16, 1001)}
    for split, rows in fmt.items():
        with open(os.path.join(args.out, "formatter", f"{split}.jsonl"), "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")

    print(f"fixtures: 32 STT rows (24/8), 64 formatter rows (48/16) under {args.out}", flush=True)


if __name__ == "__main__":
    main()
