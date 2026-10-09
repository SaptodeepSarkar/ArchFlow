#!/usr/bin/env python3
"""Build group-isolated Whisper manifests from approved V6 AMI references.

STT labels are the corpus reference transcript, never the model hypothesis or
the formatter's clean target. Audio, manifests, and resulting weights stay in
the non-Git training workspace. Meeting-level hashing prevents the same
meeting/dialog from crossing train/dev/test. It does not establish
speaker-disjointness: speaker IDs are not present in this manifest contract,
and speakers may recur across meetings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import wave
from collections import Counter
from pathlib import Path

WORD = re.compile(r"[\w]+(?:['-][\w]+)?", re.UNICODE)
MEETING = re.compile(r"^([A-Za-z0-9]{6,8})\.")


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = WORD.findall(reference.casefold())
    hyp = WORD.findall(hypothesis.casefold())
    previous = list(range(len(hyp) + 1))
    for i, token in enumerate(ref, 1):
        current = [i]
        for j, candidate in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[-1] + 1,
                               previous[j - 1] + (token != candidate)))
        previous = current
    return previous[-1] / max(1, len(ref))


def partition(group: str, seed: str) -> str:
    bucket = int.from_bytes(hashlib.sha256(f"{seed}:{group}".encode()).digest()[:4], "big") % 100
    return "train" if bucket < 80 else "dev" if bucket < 90 else "test"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True,
                        help="human-approved V6 real-derived AMI JSONL")
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="non-Git destination for generated manifests")
    parser.add_argument("--seed", default="vaani-v6-stt-20260927")
    parser.add_argument("--weighting", choices=("raw-stt-wer", "uniform"),
                        default="raw-stt-wer",
                        help="uniform avoids weighting from an upstream recognizer")
    parser.add_argument("--skip-checksums", action="store_true",
                        help="skip full WAV SHA-256 verification")
    args = parser.parse_args()

    split_rows: dict[str, list[dict]] = {name: [] for name in ("train", "dev", "test")}
    meeting_splits: dict[str, str] = {}
    counts = Counter()
    checked: set[Path] = set()
    for line_no, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        annotation = row.get("annotation", {})
        source = row.get("source", {})
        utterance = row.get("utterance", {})
        audio = row.get("audio", {})
        record_id = source.get("record_id", "")
        match = MEETING.match(record_id)
        reference = utterance.get("reference_transcript")
        raw_stt = utterance.get("raw_stt")
        if (row.get("schema_version") != "vaani.v6.formatter-example/2"
                or row.get("source", {}).get("type") != "real_derived"
                or source.get("name") != "ami-meeting-corpus-v1.6.2"
                or annotation.get("review_status") != "approved"
                or annotation.get("method") != "human-review"
                or not annotation.get("reviewer") or not annotation.get("review_notes")
                or "CC BY 4.0" not in row.get("provenance", {}).get("license_ref", "")
                or not match or not isinstance(reference, str) or not reference.strip()
                or not isinstance(raw_stt, str) or not raw_stt.strip()
                or not isinstance(audio, dict) or not audio.get("ref") or not audio.get("sha256")):
            raise SystemExit(f"invalid or unapproved V6 STT row at line {line_no}")

        meeting = match.group(1)
        split = partition(meeting, args.seed)
        old_split = meeting_splits.setdefault(meeting, split)
        if old_split != split:
            raise AssertionError("meeting split collision")
        audio_path = (args.input.parent / audio["ref"]).resolve()
        try:
            audio_path.relative_to(args.input.parent.resolve())
        except ValueError:
            raise SystemExit(f"audio reference escapes the approved data root at line {line_no}")
        if not audio_path.is_file():
            raise SystemExit(f"approved AMI audio is missing at line {line_no}")
        if not args.skip_checksums and audio_path not in checked:
            digest = hashlib.sha256(audio_path.read_bytes()).hexdigest()
            if digest != audio["sha256"]:
                raise SystemExit(f"approved AMI audio checksum mismatch at line {line_no}")
            checked.add(audio_path)
        try:
            with wave.open(str(audio_path), "rb") as wav:
                if wav.getnchannels() not in (1, 2) or wav.getframerate() != 16_000 or wav.getsampwidth() != 2:
                    raise SystemExit(f"AMI clip is not 16-kHz mono/stereo PCM16 at line {line_no}")
        except (wave.Error, OSError):
            raise SystemExit(f"invalid AMI WAV at line {line_no}")

        raw_wer = word_error_rate(reference, raw_stt) if args.weighting == "raw-stt-wer" else None
        training_row = {
            "audio_path": str(audio_path),
            "text": reference.strip(),
            "reference": reference.strip(),
            "source": "ami-meeting-corpus-v1.6.2",
            "license": "CC BY 4.0",
            "source_record_id": record_id,
            "meeting_group": meeting,
            "example_id": row["example_id"],
            "sample_weight": round(min(2.5, 1.0 + raw_wer), 4) if raw_wer is not None else 1.0,
        }
        if raw_wer is not None:
            training_row["raw_stt_wer"] = round(raw_wer, 4)
        split_rows[split].append(training_row)
        counts[split] += 1
        if raw_wer is not None:
            counts["hard_rows"] += raw_wer >= 0.20

    if not all(split_rows.values()):
        raise SystemExit("group-hash split produced an empty partition")
    if set(meeting_splits.values()) != {"train", "dev", "test"}:
        raise SystemExit("group-hash split must populate train, dev, and test")
    try:
        args.out_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise SystemExit("output directory already exists; choose a new destination") from None
    for split, rows in split_rows.items():
        rows.sort(key=lambda item: item["example_id"])
        out = args.out_dir / f"{split}.jsonl"
        out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                       encoding="utf-8")
    manifest = {
        "schema": "vaani.v6.stt-manifest/1",
        "source": "AMI v1.6.2, CC BY 4.0",
        "label": "human-reviewed source reference transcript",
        "weighting": args.weighting,
        "audio_integrity": "SHA-256 verified" if not args.skip_checksums else "not checked",
        "split_unit": "meeting",
        "seed": args.seed,
        "meeting_groups": {key: len([x for x in meeting_splits.values() if x == key])
                           for key in ("train", "dev", "test")},
        "rows": {key: len(split_rows[key]) for key in split_rows},
        "hard_rows_raw_stt_wer_ge_0_20": (
            counts["hard_rows"] if args.weighting == "raw-stt-wer" else None
        ),
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                                 encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
