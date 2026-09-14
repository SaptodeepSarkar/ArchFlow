#!/usr/bin/env python3
"""Decode the approved public Indian-English corpus into a local manifest.

Output stays outside the repository. It contains only public dataset audio
paths and public transcripts, and never touches existing corpora.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

REPOSITORY = "kaushalgawri/indian_accent_en_train"


def decode_audio(cell):
    import numpy as np
    if isinstance(cell, (str, bytes)):
        cell = json.loads(cell)
    elif hasattr(cell, "as_py"):
        cell = cell.as_py()
    else:
        cell = dict(cell)
    return np.asarray(cell["array"], dtype=np.float32), int(cell.get("sampling_rate", 16000))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--parquet", type=Path,
                    help="use an already-downloaded public parquet directly")
    ap.add_argument("--seed", type=int, default=20260914)
    args = ap.parse_args()
    manifest = args.out / "manifest.jsonl"
    if manifest.exists():
        print(f"already_ready rows={sum(1 for _ in manifest.open())}")
        return

    import pyarrow.parquet as pq
    import soundfile as sf

    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    if args.parquet:
        files = [args.parquet]
    else:
        from huggingface_hub import hf_hub_download, list_repo_files
        files = [Path(hf_hub_download(REPOSITORY, name, repo_type="dataset"))
                 for name in sorted(f for f in list_repo_files(REPOSITORY, repo_type="dataset")
                                    if f.endswith(".parquet"))]
    for local in files:
        for batch in pq.ParquetFile(local).iter_batches(batch_size=4):
            for item in batch.to_pylist():
                if item.get("down_votes") not in (0, None) or (item.get("up_votes") or 0) < 1:
                    continue
                text = str(item.get("text") or "").strip()
                if not text:
                    continue
                audio, sample_rate = decode_audio(item["audio"])
                if len(audio) < 0.4 * sample_rate or len(audio) > 30 * sample_rate:
                    continue
                wav = args.out / f"clip_{len(rows):05d}.wav"
                sf.write(wav, audio, sample_rate, subtype="PCM_16")
                rows.append({
                    "audio_path": str(wav), "text": text, "source": "cv_indian_full",
                    "up_votes": item.get("up_votes", 0), "down_votes": item.get("down_votes", 0),
                    "gender": item.get("gender"), "age": item.get("age"),
                    "speaker_name": item.get("speaker_name"),
                })
                if len(rows) % 250 == 0:
                    print(f"decoded={len(rows)}", flush=True)
    random.Random(args.seed).shuffle(rows)
    manifest.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(f"ready rows={len(rows)} path={manifest}")


if __name__ == "__main__":
    main()
