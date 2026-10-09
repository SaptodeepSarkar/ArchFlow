#!/usr/bin/env python3
"""Import the gated Vaani English transcribed subset into private V6 manifests.

This never accepts dataset terms. The caller must first accept ARTPARK's
Hugging Face conditions, then explicitly pass --terms-accepted. Audio and
transcripts are written only under a new destination outside the Git worktree.
Only audio, transcript, source/license identifiers, and hashes are retained;
demographic and location fields are deliberately discarded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
import wave
from collections import Counter
from pathlib import Path
from typing import Any

DATASET_ID = "ARTPARK-IISc/Vaani-transcription-part"
AUDITED_REVISION = "d2acadff1ccce766d127c11b1a157251460dd68a"
SPLITS = ("train", "validation", "test")


def checked_revision(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("revision must be a full 40-character lowercase commit hash")
    return value


def mono_pcm16(audio: Any, sample_rate: int):
    """Convert a Hugging Face decoded Audio array to 16-kHz mono PCM16."""
    import numpy as np

    if not isinstance(sample_rate, int) or not 8_000 <= sample_rate <= 192_000:
        raise ValueError("invalid audio sample rate")
    samples = np.asarray(audio)
    if samples.ndim == 2:
        # HF/audio decoders use samples x channels; tolerate channels x samples.
        if samples.shape[0] <= 8 < samples.shape[1]:
            samples = samples.mean(axis=0)
        else:
            samples = samples.mean(axis=1)
    if samples.ndim != 1 or samples.size < max(1, sample_rate // 5):
        raise ValueError("audio must contain at least 200 ms of mono/mixable speech")
    if np.issubdtype(samples.dtype, np.integer):
        bounds = np.iinfo(samples.dtype)
        scale = max(abs(bounds.min), bounds.max)
        samples = samples.astype(np.float32) / float(scale)
    else:
        samples = samples.astype(np.float32, copy=False)
    if not np.isfinite(samples).all() or float(np.max(np.abs(samples))) > 1.05:
        raise ValueError("audio contains non-finite or out-of-range samples")
    if sample_rate != 16_000:
        new_size = max(1, round(samples.size * 16_000 / sample_rate))
        samples = np.interp(np.linspace(0, samples.size - 1, new_size),
                            np.arange(samples.size), samples).astype(np.float32)
    return np.round(np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")


def write_audio(path: Path, audio: Any, sample_rate: int) -> str:
    try:
        pcm = mono_pcm16(audio, sample_rate)
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(16_000)
            target.writeframes(pcm.tobytes())
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except Exception:
        path.unlink(missing_ok=True)
        raise


def record_for(split: str, index: int, row: dict[str, Any],
               audio_path: Path, audio_sha256: str, revision: str) -> dict[str, Any]:
    transcript = row.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("empty transcript")
    source_id = hashlib.sha256(
        f"{DATASET_ID}:{revision}:{split}:{index}:{audio_sha256}".encode("utf-8")
    ).hexdigest()
    clean_text = transcript.strip()
    return {
        "example_id": source_id,
        "audio_path": str(audio_path),
        "text": clean_text,
        "reference": clean_text,
        "source": "project-vaani-transcription-part-english",
        "source_record_id": source_id,
        "source_revision": revision,
        "license": "CC BY 4.0",
        "sample_weight": 1.0,
        "audio_sha256": audio_sha256,
    }


def ensure_outside_repo(path: Path, repo_root: Path) -> Path:
    destination = path.resolve()
    try:
        destination.relative_to(repo_root.resolve())
    except ValueError:
        return destination
    raise ValueError("Vaani audio/manifests must be stored outside the Git worktree")


def import_dataset(out: Path, revision: str) -> dict[str, Any]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("install the project's Hugging Face datasets dependency first") from exc

    counts: Counter[str] = Counter()
    split_hashes: dict[str, set[str]] = {split: set() for split in SPLITS}
    manifest_digests: dict[str, str] = {}
    accepted_audio_paths: set[Path] = set()
    parent = out.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Build privately and atomically publish only after all splits validate.
    with tempfile.TemporaryDirectory(prefix=f".{out.name}.import-", dir=parent) as scratch_name:
        scratch = Path(scratch_name)
        for split in SPLITS:
            dataset = load_dataset(DATASET_ID, "English", split=split,
                                   revision=revision, token=True, streaming=True)
            manifest_path = scratch / f"{split}.jsonl"
            with manifest_path.open("x", encoding="utf-8") as manifest:
                for index, row in enumerate(dataset):
                    audio_path = scratch / "audio" / split / f"{index:06d}.wav"
                    try:
                        audio = row.get("audio")
                        if not isinstance(audio, dict) or audio.get("array") is None:
                            raise ValueError("missing decoded audio")
                        audio_sha = write_audio(
                            audio_path, audio["array"], audio.get("sampling_rate"),
                        )
                        previous = next((name for name, digests in split_hashes.items()
                                         if audio_sha in digests), None)
                        if previous is not None:
                            if previous != split:
                                raise RuntimeError("identical audio occurs across official splits")
                            counts[f"duplicate_{split}"] += 1
                            audio_path.unlink(missing_ok=True)
                            continue
                        record = record_for(split, index, row,
                                            out / "audio" / split / f"{index:06d}.wav",
                                            audio_sha, revision)
                        manifest.write(json.dumps(record, ensure_ascii=False,
                                                  sort_keys=True) + "\n")
                        accepted_audio_paths.add(audio_path.resolve())
                        split_hashes[split].add(audio_sha)
                        counts[split] += 1
                    except RuntimeError:
                        audio_path.unlink(missing_ok=True)
                        raise
                    except Exception:
                        # Bad/missing media or labels are excluded automatically;
                        # only aggregate counts are retained or printed.
                        audio_path.unlink(missing_ok=True)
                        counts[f"invalid_{split}"] += 1
                manifest.flush()
                os.fsync(manifest.fileno())
            if counts[split] == 0:
                raise RuntimeError(f"source split {split} imported no valid examples")
            manifest_digests[split] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

        totals = sum(counts[split] + counts[f"invalid_{split}"] + counts[f"duplicate_{split}"]
                     for split in SPLITS)
        invalid = sum(counts[f"invalid_{split}"] for split in SPLITS)
        if totals == 0 or invalid / totals > 0.01:
            raise RuntimeError("more than 1% of source rows failed automated validation")
        staged_audio_paths = {path.resolve() for path in (scratch / "audio").rglob("*.wav")}
        if staged_audio_paths != accepted_audio_paths:
            raise RuntimeError("staged audio files do not match accepted manifest rows")
        provenance = {
            "schema": "vaani.v6.stt-import/1",
            "dataset": DATASET_ID,
            "config": "English",
            "revision": revision,
            "license": "CC BY 4.0",
            "attribution": "Project Vaani, IISc Bangalore and ARTPARK",
            "citation": "https://arxiv.org/abs/2603.28714",
            "audio_format": "16-kHz mono PCM16 WAV",
            "split_policy": "preserve official train/validation/test splits",
            "speaker_disjointness": "not asserted; source rows have no speaker ID",
            "counts": dict(sorted(counts.items())),
            "manifest_sha256": manifest_digests,
        }
        (scratch / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(scratch, out)
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--revision", default=AUDITED_REVISION)
    parser.add_argument("--terms-accepted", action="store_true",
                        help="confirm the account owner already accepted upstream access terms")
    args = parser.parse_args()
    if not args.terms_accepted:
        raise SystemExit("accept the dataset's access terms in Hugging Face first; no terms are accepted by this tool")
    try:
        revision = checked_revision(args.revision)
        destination = ensure_outside_repo(args.out, Path(__file__).resolve().parents[1])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if destination.exists():
        raise SystemExit("refusing to overwrite existing Vaani import")
    try:
        provenance = import_dataset(destination, revision)
    except Exception as exc:
        # HF exceptions can embed request details; print only a generic reason.
        raise SystemExit(f"Vaani import failed ({type(exc).__name__}); no transcript was logged") from None
    print(json.dumps({"dataset": DATASET_ID, "revision": revision,
                      "counts": provenance["counts"],
                      "manifest_sha256": provenance["manifest_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
