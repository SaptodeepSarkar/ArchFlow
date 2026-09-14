#!/usr/bin/env python3
"""Convert the external public TTS manifest to Piper's pipe-delimited CSV."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--audio-root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = []
    for line in args.manifest.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            audio = Path(row["audio_path"]).resolve()
            try:
                relative = audio.relative_to(args.audio_root.resolve())
            except ValueError:
                continue
            text = " ".join(str(row["text"]).split()).replace("\n", " ")
            if text and audio.exists():
                handle.write(f"{relative}|{text}\n")
                kept += 1
    print(json.dumps({"rows": kept, "csv": str(args.out),
                      "audio_root": str(args.audio_root.resolve())}))


if __name__ == "__main__":
    main()
