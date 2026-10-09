#!/usr/bin/env python3
"""Validate local V6 synthetic vocabulary audio without exposing targets."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import wave
from collections import Counter
from pathlib import Path


def count_untracked_audio(audio_dir: Path, expected_paths: set[Path]) -> int:
    expected = {path.resolve() for path in expected_paths}
    present = {path.resolve() for path in audio_dir.glob("*.wav") if path.is_file()}
    return len(present - expected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--minimum-duration-ms", type=int, default=500)
    parser.add_argument("--maximum-duration-ms", type=int, default=20_000)
    args = parser.parse_args()
    db = sqlite3.connect(args.manifest)
    rows = db.execute("SELECT id, audio_path, sample_rate, audio_sha256, term_pack FROM examples").fetchall()
    errors, packs, rates, durations = [], Counter(), Counter(), []
    expected_audio = set()
    ids = set()
    for identity, location, expected_rate, expected_hash, pack in rows:
        if identity in ids:
            errors.append("duplicate_id"); continue
        ids.add(identity); path = Path(location)
        expected_audio.add(path)
        if not path.is_file():
            errors.append("missing_audio"); continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            errors.append("audio_hash_mismatch"); continue
        try:
            with wave.open(str(path), "rb") as handle:
                frames, rate = handle.getnframes(), handle.getframerate()
                if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                    errors.append("audio_format")
                if rate != expected_rate:
                    errors.append("sample_rate_mismatch")
                duration = round(1000 * frames / max(rate, 1))
        except (wave.Error, EOFError):
            errors.append("invalid_wav"); continue
        if not args.minimum_duration_ms <= duration <= args.maximum_duration_ms:
            errors.append("duration_out_of_range")
        packs[pack] += 1; rates[rate] += 1; durations.append(duration)
    audio_dir = args.manifest.parent / "audio"
    untracked_audio = count_untracked_audio(audio_dir, expected_audio)
    errors.extend(["untracked_audio"] * untracked_audio)
    db.close()
    report = {"rows": len(rows), "errors": len(errors), "error_counts": Counter(errors),
              "audio_files_on_disk": len(list(audio_dir.glob("*.wav"))),
              "untracked_audio_files": untracked_audio,
              "packs": packs, "sample_rates": rates,
              "duration_ms_min": min(durations, default=None),
              "duration_ms_max": max(durations, default=None),
              "duration_ms_mean": sum(durations) / len(durations) if durations else None}
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
