#!/usr/bin/env python3
"""Stage only audio and references from the pinned Monsoon public test split.

This is an evaluation-only source. Dataset metadata is read in memory but
never copied to the output; raw Hub caches are isolated in a temporary folder
and removed when this command exits. The output manifest is local-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable


REPO_ID = "VoiceArena/MonsoonASR-Open-ASR-leaderboard-en-IN"
REVISION = "bc1da7b42ef6e2853123c97bf6d22067e4802d11"
DATASET_URL = f"https://huggingface.co/datasets/{REPO_ID}/tree/{REVISION}"
LICENSE = "CC BY 4.0"


def audio_extension(source_path: str | None, payload: bytes) -> str:
    candidate = Path(source_path or "").suffix.lower()
    if candidate in {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".webm"}:
        return candidate
    if payload.startswith(b"RIFF"):
        return ".wav"
    if payload.startswith(b"fLaC"):
        return ".flac"
    if payload.startswith(b"OggS"):
        return ".ogg"
    if payload.startswith(b"ID3") or payload[:1] == b"\xff":
        return ".mp3"
    raise ValueError("audio encoding is not recognized")


def stage_rows(rows: Iterable[dict], output_dir: Path) -> dict:
    """Write minimal audio/reference rows; discard every other source field."""
    output_dir.mkdir(parents=True, exist_ok=False)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir()
    manifest_path = output_dir / "manifest.jsonl"
    count = 0
    duration_seconds = 0.0
    with manifest_path.open("x", encoding="utf-8") as manifest:
        for index, source in enumerate(rows):
            reference = source.get("text")
            audio = source.get("audio")
            if not isinstance(reference, str) or not reference.strip() or not isinstance(audio, dict):
                raise ValueError("source row lacks audio or reference")
            payload = audio.get("bytes")
            if not isinstance(payload, bytes) or not payload:
                raise ValueError("source audio bytes are unavailable")
            example_id = hashlib.sha256(
                f"{REPO_ID}@{REVISION}:test:{index}".encode("utf-8")
            ).hexdigest()[:24]
            extension = audio_extension(audio.get("path"), payload)
            audio_rel = f"audio/{example_id}{extension}"
            audio_path = output_dir / audio_rel
            audio_path.write_bytes(payload)
            audio_hash = hashlib.sha256(payload).hexdigest()
            duration = source.get("audio_length_s")
            if isinstance(duration, (int, float)) and duration > 0:
                duration_seconds += float(duration)
            row = {
                "example_id": example_id,
                "audio": {"ref": audio_rel, "sha256": audio_hash},
                "utterance": {"reference_transcript": reference.strip()},
                "challenge_tags": ["indian_english", "spontaneous", "conversation"],
                "challenge_terms": [],
            }
            manifest.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    if count != 2_102:
        raise ValueError(f"pinned public test split has unexpected row count: {count}")
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    provenance = {
        "dataset": REPO_ID,
        "revision": REVISION,
        "split": "test (public; evaluation only)",
        "license": LICENSE,
        "source_url": DATASET_URL,
        "rows": count,
        "audio_seconds_from_source_metadata": round(duration_seconds, 3),
        "minimal_manifest_sha256": manifest_hash,
        "audio_fields_retained": ["audio bytes", "content sha256"],
        "text_fields_retained": ["human-reviewed reference transcript"],
        "source_metadata_discarded": [
            "source id", "speaker id", "gender", "date of birth", "occupation",
            "education", "marital status", "district", "state", "city",
            "years in district", "income", "device manufacturer", "device model",
        ],
        "restriction": "one-shot aggregate-only evaluation; never training or tuning",
        "attribution": "VoiceArena Monsoon ASR Open Leaderboard (CC BY 4.0)",
    }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return {"rows": count, "duration_seconds": round(duration_seconds, 3),
            "manifest_sha256": manifest_hash}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="new non-Git directory; existing output is never overwritten")
    args = parser.parse_args()
    if args.out_dir.exists():
        raise SystemExit("output directory already exists; choose a new path")

    args.out_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{args.out_dir.name}.stage-", dir=args.out_dir.parent
    ) as temporary:
        temp_root = Path(temporary)
        # Do not leave raw Parquet/audio/demographic cache in the user's default
        # Hugging Face cache. The isolated cache is removed on exit.
        os.environ["HF_HOME"] = str(temp_root / "hf-home")
        os.environ["HF_HUB_CACHE"] = str(temp_root / "hf-hub")
        os.environ["HF_DATASETS_CACHE"] = str(temp_root / "hf-datasets")
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"

        from datasets import Audio, load_dataset
        from datasets.utils.logging import disable_progress_bar, set_verbosity_error

        disable_progress_bar()
        set_verbosity_error()
        dataset = load_dataset(REPO_ID, revision=REVISION, split="test", streaming=True)
        dataset = dataset.cast_column("audio", Audio(decode=False))
        staged_dir = temp_root / "dataset"
        summary = stage_rows(dataset, staged_dir)
        if args.out_dir.exists():
            raise SystemExit("output directory appeared during staging; refusing to overwrite")
        os.replace(staged_dir, args.out_dir)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
