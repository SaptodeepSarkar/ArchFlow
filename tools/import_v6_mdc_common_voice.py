#!/usr/bin/env python3
"""Import the official MDC South Asian English CV 26 release privately.

This is deliberately an offline importer: it never logs in, downloads data, or
accepts terms. The account owner must obtain the pinned archive through MDC and
pass --terms-accepted only after accepting the applicable terms. The raw
client_id is used in memory to verify the release's speaker-disjoint splits,
then discarded; no demographic fields are copied to the output manifests.
"""
from __future__ import annotations

import argparse
import csv
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import statistics
import tarfile
import tempfile
import wave
from collections import Counter
from pathlib import Path, PurePosixPath

DATASET = "Mozilla Common Voice Scripted Speech 26.0 - South Asian English"
DATASET_ID = "cmrt70sar001umm07jwxzhw89"
RELEASE = "cv-corpus-26.0-2026-06-12"
ARCHIVE_NAME = "common-voice-scripted-speech-26-0-south-9d6029b6.tar.gz"
MDC_URL = f"https://mozilladatacollective.com/datasets/{DATASET_ID}"
ACCENT = "India and South Asia (India, Pakistan, Sri Lanka)"
EXPECTED = {
    "train": (101_702, 2_270),
    "dev": (6_533, 102),
    "test": (3_864, 81),
}
MAX_ARCHIVE_MEMBERS = 150_000
MAX_UNPACKED_BYTES = 8 * 1024**3
MIN_IMPORT_FREE_BYTES = 24 * 1024**3


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_extract(archive: Path, target: Path) -> None:
    """Extract regular files only; reject path traversal and links."""
    root = target.resolve()
    with tarfile.open(archive, "r:gz") as bundle:
        total_bytes = 0
        for member_count, member in enumerate(bundle, 1):
            if member_count > MAX_ARCHIVE_MEMBERS:
                raise ValueError("archive contains too many members")
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or member.issym() or member.islnk():
                raise ValueError("archive contains an unsafe path or link")
            destination = (target / Path(*name.parts)).resolve()
            try:
                destination.relative_to(root)
            except ValueError as exc:
                raise ValueError("archive path escapes extraction root") from exc
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError("archive contains a non-regular entry")
            total_bytes += member.size
            if member.size < 0 or total_bytes > MAX_UNPACKED_BYTES:
                raise ValueError("archive exceeds the unpacked-size limit")
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise ValueError("archive member could not be read")
            with source, destination.open("xb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)


def find_split_tables(root: Path) -> tuple[Path, dict[str, Path]]:
    tables: dict[str, list[Path]] = {name: [] for name in EXPECTED}
    for path in root.rglob("*.tsv"):
        if path.name in {f"{name}.tsv" for name in EXPECTED}:
            tables[path.stem].append(path)
    if any(len(items) != 1 for items in tables.values()):
        raise ValueError("archive must contain exactly one train/dev/test TSV")
    paths = {name: items[0] for name, items in tables.items()}
    if len({path.parent for path in paths.values()}) != 1:
        raise ValueError("split TSVs must share a directory")
    return paths["train"].parent, paths


def count_speakers(table: Path) -> Counter[str]:
    """Count pseudonymous speakers in memory without persisting source IDs."""
    counts: Counter[str] = Counter()
    with table.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        required = {"client_id", "accents"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("split TSV lacks speaker/accent fields")
        for row in reader:
            if row.get("accents", "").strip() != ACCENT:
                raise ValueError("accent tags differ from the pinned closed-form release")
            client = (row.get("client_id") or "").strip()
            if not client:
                raise ValueError("source row has no speaker key")
            counts[hashlib.sha256(client.encode("utf-8")).hexdigest()] += 1
    return counts


def convert_mp3(source: Path, destination: Path) -> None:
    """Decode/resample without exposing transcript or audio in logs."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(source),
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav",
             str(destination)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode:
            raise ValueError("audio decode failed")
        with wave.open(str(destination), "rb") as wav:
            if (wav.getnchannels() != 1 or wav.getframerate() != 16_000
                    or wav.getsampwidth() != 2 or wav.getnframes() < 3_200):
                raise ValueError("decoded audio failed format checks")
    except Exception as exc:
        destination.unlink(missing_ok=True)
        if isinstance(exc, ValueError):
            raise
        raise ValueError("audio decode failed or output is not valid PCM16 WAV") from exc


def import_archive(archive: Path, out: Path, repo_root: Path) -> dict:
    if archive.name != ARCHIVE_NAME or not archive.is_file():
        raise ValueError(f"provide the exact official archive: {ARCHIVE_NAME}")
    destination = out.resolve()
    try:
        destination.relative_to(repo_root.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("audio/manifests must stay outside the Git worktree")
    if destination.exists():
        raise ValueError("refusing to overwrite an existing import")

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Archive extraction plus 16-kHz PCM conversion needs substantial scratch
    # space: 166 speech-hours alone occupy about 19 GiB as mono PCM16.
    required_free = max(MIN_IMPORT_FREE_BYTES, archive.stat().st_size * 7)
    if shutil.disk_usage(parent).free < required_free:
        raise ValueError("insufficient free space for safe extraction and PCM conversion")
    archive_sha = sha256_file(archive)
    counts: Counter[str] = Counter()
    speakers: dict[str, set[str]] = {name: set() for name in EXPECTED}
    audio_hashes: dict[str, str] = {}
    manifest_hashes: dict[str, str] = {}
    invalid = Counter()

    with tempfile.TemporaryDirectory(prefix=f".{destination.name}.import-", dir=parent) as scratch_name:
        scratch = Path(scratch_name)
        source_root = scratch / "source"
        source_root.mkdir()
        safe_extract(archive, source_root)
        table_root, tables = find_split_tables(source_root)
        speaker_counts = {split: count_speakers(table) for split, table in tables.items()}
        for split, sizes in speaker_counts.items():
            if len(sizes) != EXPECTED[split][1]:
                raise ValueError("source speaker count differs from pinned MDC release")
        # Output manifests contain only model inputs and provenance identifiers;
        # client IDs and contributor demographics are never written.
        for split, table in tables.items():
            manifest_path = scratch / f"{split}.jsonl"
            with contextlib.ExitStack() as stack:
                source = stack.enter_context(table.open("r", encoding="utf-8-sig", newline=""))
                output = stack.enter_context(manifest_path.open("x", encoding="utf-8"))
                capped_output = None
                if split == "train":
                    capped_output = stack.enter_context(
                        (scratch / "train-speaker-capped.jsonl").open("x", encoding="utf-8"))
                reader = csv.DictReader(source, delimiter="\t")
                required = {"path", "sentence", "client_id", "accents"}
                if not reader.fieldnames or not required.issubset(reader.fieldnames):
                    raise ValueError("split TSV lacks required Common Voice fields")
                for row in reader:
                    wav_path = None
                    try:
                        client = row.get("client_id", "").strip()
                        text = row.get("sentence", "").strip()
                        rel = PurePosixPath(row.get("path", ""))
                        if (not client or not text or row.get("accents", "").strip() != ACCENT
                                or rel.is_absolute() or ".." in rel.parts):
                            raise ValueError("row failed metadata checks")
                        audio = (table_root / Path(*rel.parts)).resolve()
                        audio.relative_to(table_root.resolve())
                        if not audio.is_file() or audio.suffix.lower() != ".mp3":
                            raise ValueError("source audio is missing or not MP3")
                        source_hash = sha256_file(audio)
                        if source_hash in audio_hashes:
                            raise ValueError("duplicate audio across source rows")
                        audio_hashes[source_hash] = split
                        speaker_key = hashlib.sha256(client.encode("utf-8")).hexdigest()
                        speakers[split].add(speaker_key)
                        example_id = hashlib.sha256(
                            f"{DATASET_ID}:{RELEASE}:{split}:{source_hash}".encode()
                        ).hexdigest()
                        wav_path = scratch / "audio" / split / f"{example_id}.wav"
                        convert_mp3(audio, wav_path)
                        record = {
                            "example_id": example_id,
                            "audio_path": str(destination / "audio" / split / f"{example_id}.wav"),
                            "text": text,
                            "reference": text,
                            "source": "mozilla-common-voice-26-south-asian-english",
                            "source_record_id": example_id,
                            "license": "CC0-1.0",
                            "sample_weight": 1.0,
                        }
                        serialized = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                        output.write(serialized)
                        if capped_output is not None:
                            # A separate candidate caps dominant speakers with a
                            # square-root weight. Compare it on dev; uniform is
                            # retained as the control and test remains untouched.
                            capped = dict(record)
                            capped["sample_weight"] = min(
                                1.0, (500.0 / speaker_counts[split][speaker_key]) ** 0.5)
                            capped_output.write(
                                json.dumps(capped, ensure_ascii=False, sort_keys=True) + "\n")
                        counts[split] += 1
                    except Exception:
                        if wav_path is not None:
                            wav_path.unlink(missing_ok=True)
                        invalid[split] += 1
                output.flush()
                os.fsync(output.fileno())
            expected_rows, expected_speakers = EXPECTED[split]
            if counts[split] != expected_rows or len(speakers[split]) != expected_speakers:
                raise ValueError("imported split count or speaker count differs from pinned MDC release")
            manifest_hashes[split] = sha256_file(manifest_path)
            if split == "train":
                manifest_hashes["train-speaker-capped"] = sha256_file(
                    scratch / "train-speaker-capped.jsonl")

        names = list(speakers)
        if any(speakers[a] & speakers[b] for i, a in enumerate(names) for b in names[i + 1:]):
            raise ValueError("source speaker IDs overlap across official splits")
        if sum(invalid.values()) != 0:
            raise ValueError("one or more pinned-release rows failed automatic checks")
        manifest_audio_paths = set()
        for split in EXPECTED:
            with (scratch / f"{split}.jsonl").open(encoding="utf-8") as manifest:
                for line in manifest:
                    record = json.loads(line)
                    manifest_audio_paths.add(
                        (scratch / "audio" / split / f"{Path(record['audio_path']).stem}.wav").resolve()
                    )
        staged_audio_paths = {path.resolve() for path in (scratch / "audio").rglob("*.wav")}
        if staged_audio_paths != manifest_audio_paths:
            raise ValueError("staged audio files do not match accepted manifest rows")

        shutil.rmtree(source_root)
        train_speaker_sizes = sorted(speaker_counts["train"].values())
        provenance = {
            "schema": "vaani.v6.stt-import/1",
            "dataset": DATASET,
            "dataset_id": DATASET_ID,
            "release": RELEASE,
            "archive": ARCHIVE_NAME,
            "archive_sha256": archive_sha,
            "license": "CC0-1.0",
            "access_route": "Mozilla Data Collective",
            "source_url": MDC_URL,
            "accent_filter": ACCENT,
            "audio_format": "16-kHz mono PCM16 WAV",
            "split_policy": "preserve official speaker-disjoint train/dev/test",
            "speaker_ids_written": False,
            "counts": {
                split: {"rows": counts[split], "speakers": len(speakers[split])}
                for split in EXPECTED
            },
            "train_speaker_distribution": {
                "minimum_clips": train_speaker_sizes[0],
                "median_clips": statistics.median(train_speaker_sizes),
                "p95_clips": train_speaker_sizes[int(0.95 * (len(train_speaker_sizes) - 1))],
                "maximum_clips": train_speaker_sizes[-1],
                "speaker_capped_weight_rule": "min(1, sqrt(500 / speaker_clip_count))",
            },
            "invalid_rows": dict(invalid),
            "manifest_sha256": manifest_hashes,
            "qualification_only": ["dev", "test"],
            "redistribution": "do not rehost source audio/dataset",
        }
        (scratch / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # Move only the completed payload; the temporary source files disappear.
        payload = scratch / "payload"
        payload.mkdir()
        for split in EXPECTED:
            (scratch / f"{split}.jsonl").rename(payload / f"{split}.jsonl")
        (scratch / "train-speaker-capped.jsonl").rename(
            payload / "train-speaker-capped.jsonl")
        (scratch / "audio").rename(payload / "audio")
        (scratch / "provenance.json").rename(payload / "provenance.json")
        os.replace(payload, destination)
    return provenance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True,
                        help="official MDC CV 26 South Asian English archive")
    parser.add_argument("--out", type=Path, required=True,
                        help="new private output directory outside the repository")
    parser.add_argument("--terms-accepted", action="store_true",
                        help="confirm the account owner already accepted MDC/Common Voice terms")
    args = parser.parse_args()
    if not args.terms_accepted:
        raise SystemExit("MDC/Common Voice terms must be accepted by the account owner first")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required to convert MP3 into the V6 Whisper training format")
    try:
        report = import_archive(args.archive.resolve(), args.out,
                                Path(__file__).resolve().parents[1])
    except Exception as exc:
        # Do not print a transcript, client ID, or source file path on failure.
        raise SystemExit(f"MDC import failed ({type(exc).__name__}); no row content was logged") from None
    print(json.dumps({"dataset_id": DATASET_ID, "archive_sha256": report["archive_sha256"],
                      "counts": report["counts"], "manifest_sha256": report["manifest_sha256"]},
                     sort_keys=True))


if __name__ == "__main__":
    main()
