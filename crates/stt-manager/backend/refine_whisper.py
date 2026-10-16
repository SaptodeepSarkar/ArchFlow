#!/usr/bin/env python3
"""Vaani STT backend: the fine-tuned Whisper re-decode pass.

Second pass over a finished utterance. The streaming backend already emitted
live words for the overlay; this asks the resident fine-tuned model for a more
accurate reading of the same PCM, and the daemon prefers those words when it
answers. It never runs while the user is speaking, so it cannot delay the live
words (see the architecture note in FINAL-indic-stt-llm-training.md).

Line protocol is identical to transcribe.py, so the daemon parses one shape:
  W <t_sec> <word>        one final word (t is 0 here: see the server's note)
  DONE audio=<s> infer=<s> words=<n> model=<endpoint>

Input: --stdin (raw s16le 16kHz mono). Exits nonzero if the model server is
unreachable or rejects the audio, so the caller keeps the streaming words
rather than losing the utterance.

Config (env): VAANI_STT_REFINE_ENDPOINT (default http://127.0.0.1:8083),
              VAANI_STT_REFINE_TIMEOUT (seconds, default 120).
Stdlib only on purpose: this runs under the STT python that has vosk, which has
no ML stack installed.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

SAMPLE_RATE = 16000


def main():
    if "--stdin" not in sys.argv[1:]:
        print("usage: refine_whisper.py --stdin", file=sys.stderr)
        return 2
    endpoint = os.environ.get("VAANI_STT_REFINE_ENDPOINT", "http://127.0.0.1:8083")
    timeout = float(os.environ.get("VAANI_STT_REFINE_TIMEOUT", "120"))

    pcm = sys.stdin.buffer.read()
    n = len(pcm) & ~1
    if n == 0:
        print("no audio on stdin", file=sys.stderr)
        return 2
    audio_secs = n / (2 * SAMPLE_RATE)

    url = endpoint.rstrip("/") + "/transcribe"
    req = urllib.request.Request(
        url, data=pcm[:n], headers={"Content-Type": "application/octet-stream"}
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"refine server {endpoint} failed: {e}", file=sys.stderr)
        return 1

    words = payload.get("words") or []
    out = sys.stdout
    for w in words:
        text = str(w.get("w", "")).strip()
        if text:
            out.write(f"W {float(w.get('t') or 0.0):.2f} {text}\n")
    infer = float(payload.get("infer") or (time.time() - t0))
    out.write(
        f"DONE audio={audio_secs:.2f} infer={infer:.2f} words={len(words)} model={endpoint}\n"
    )
    out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
