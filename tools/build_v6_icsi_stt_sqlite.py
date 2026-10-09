#!/usr/bin/env python3
"""Build private, speaker-disjoint ICSI Whisper manifests from official NXT data.

The output SQLite schema is compatible with train_v5_whisper_lora.py's
--sqlite-manifest input. Transcripts are kept in SQLite, never printed or
written to a JSON manifest. Source audio, crops, and databases must stay outside
the repository. This tool does not download audio or accept corpus terms.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
import wave
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

CORPUS = "ICSI Meeting Corpus core annotations v1.0"
LICENSE = "CC BY 4.0"
SOURCE_URL = "https://groups.inf.ed.ac.uk/ami/icsi/download/"
CHILD_RANGE = re.compile(r"#id\(([^)]+)\)(?:\.\.id\(([^)]+)\))?")
WORD_FILE = re.compile(r"([^/.]+)\.([^.]+)\.words\.xml$")
ACT_FILE = re.compile(r"([^/.]+)\.([^.]+)\.dialogue-acts\.xml$")
PUNCT_ONLY = re.compile(r"[^\w\s]+", re.UNICODE)
MAX_DURATION_S = 15.0


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def nite_id(element: ET.Element) -> str | None:
    return next((value for key, value in element.attrib.items()
                 if local(key) == "id"), None)


def participant_split(participant: str, seed: str) -> str:
    digest = hashlib.sha256(f"{seed}:{participant}".encode()).digest()
    bucket = int.from_bytes(digest[:4], "big") % 100
    return "train" if bucket < 80 else "dev" if bucket < 90 else "test"


def timestamp(element: ET.Element) -> tuple[float, float] | None:
    try:
        start, end = float(element.get("starttime", "")), float(element.get("endtime", ""))
    except ValueError:
        return None
    if start < 0 or end <= start:
        return None
    return start, end


def transcript(elements: list[ET.Element]) -> tuple[str, int]:
    pieces: list[str] = []
    lexical = 0
    for element in elements:
        if local(element.tag) != "w":
            # In particular, <disfmarker> is an editorial placeholder, not speech.
            continue
        token = (element.text or "").strip()
        if not token:
            continue
        category = element.get("c", "")
        punctuation = bool(PUNCT_ONLY.fullmatch(token))
        if not punctuation:
            lexical += 1
        if not pieces:
            pieces.append(token)
        elif punctuation or category == "APOSS" or token.startswith("'"):
            pieces[-1] += token
        elif pieces[-1].endswith(("(", "[", "{", "\"")):
            pieces[-1] += token
        else:
            pieces.append(token)
    return " ".join(pieces), lexical


def parse_corpus(archive: Path):
    """Return per-meeting spans and speaker/channel mapping without demographics."""
    with zipfile.ZipFile(archive) as source:
        names = source.namelist()
        word_paths = [name for name in names if name.endswith(".words.xml")]
        act_paths = [name for name in names if name.endswith(".dialogue-acts.xml")]
        if not word_paths or not act_paths or "ICSI/speakers.xml" not in names:
            raise ValueError("archive does not match the audited ICSI core NXT layout")

        acts_by_meeting: dict[str, list[tuple[str, ET.Element]]] = defaultdict(list)
        channel_participants: dict[tuple[str, str], set[str]] = defaultdict(set)
        for path in act_paths:
            match = ACT_FILE.search(Path(path).name)
            if not match:
                continue
            meeting, channel = match.groups()
            for act in ET.fromstring(source.read(path)):
                participant = act.get("participant", "").strip()
                if participant:
                    channel_participants[(meeting, channel)].add(participant)
                    acts_by_meeting[meeting].append((channel, act))

        # Speaker attributes and demographics are intentionally never parsed.
        participants: dict[tuple[str, str], str] = {}
        for key, values in channel_participants.items():
            if len(values) == 1:
                participants[key] = next(iter(values))

        words_by_meeting: dict[str, list[dict]] = defaultdict(list)
        word_maps: dict[tuple[str, str], tuple[list[str], dict[str, ET.Element], dict[str, int]]] = {}
        for path in word_paths:
            match = WORD_FILE.search(Path(path).name)
            if not match:
                continue
            meeting, channel = match.groups()
            elements = list(ET.fromstring(source.read(path)))
            ordered_ids, mapping = [], {}
            participant = participants.get((meeting, channel))
            for element in elements:
                identifier = nite_id(element)
                if identifier:
                    ordered_ids.append(identifier)
                    mapping[identifier] = element
                if local(element.tag) != "w" or not participant:
                    continue
                bounds = timestamp(element)
                if bounds is not None:
                    words_by_meeting[meeting].append({
                        "participant": participant, "channel": channel,
                        "start": bounds[0], "end": bounds[1],
                    })
            positions = {identifier: index for index, identifier in enumerate(ordered_ids)}
            word_maps[(meeting, channel)] = (ordered_ids, mapping, positions)

        interval_index = {}
        for meeting, intervals in words_by_meeting.items():
            intervals.sort(key=lambda item: item["start"])
            starts = [item["start"] for item in intervals]
            maximum_ends = []
            maximum_end = 0.0
            for item in intervals:
                maximum_end = max(maximum_end, item["end"])
                maximum_ends.append(maximum_end)
            interval_index[meeting] = (intervals, starts, maximum_ends)

        spans = []
        for meeting, acts in acts_by_meeting.items():
            intervals, starts, maximum_ends = interval_index.get(meeting, ([], [], []))
            for channel, act in acts:
                participant = act.get("participant", "").strip()
                if not participant or participants.get((meeting, channel)) != participant:
                    continue
                child = next((node for node in act if local(node.tag) == "child"), None)
                match = CHILD_RANGE.search(child.get("href", "")) if child is not None else None
                stream = word_maps.get((meeting, channel))
                if not match or stream is None:
                    continue
                ordered_ids, mapping, positions = stream
                try:
                    first = positions[match.group(1)]
                    last = positions[match.group(2) or match.group(1)]
                except KeyError:
                    continue
                if last < first:
                    continue
                selected = [mapping[key] for key in ordered_ids[first:last + 1]
                            if key in mapping]
                utterance, lexical_count = transcript(selected)
                lexical_words = [element for element in selected
                                 if local(element.tag) == "w"
                                 and not PUNCT_ONLY.fullmatch((element.text or "").strip())]
                bounds = [timestamp(element) for element in lexical_words]
                if (not utterance or lexical_count < 3 or lexical_count > 80
                        or not bounds or any(value is None for value in bounds)):
                    continue
                start = min(value[0] for value in bounds if value is not None)
                end = max(value[1] for value in bounds if value is not None)
                if end <= start or end - start > MAX_DURATION_S:
                    continue
                # Mixed audio is ambiguous whenever another participant's
                # transcribed word overlaps this single-speaker source span.
                interval_start = bisect_left(maximum_ends, start + 0.05)
                interval_stop = bisect_left(starts, end - 0.05)
                overlap = False
                for interval_position in range(interval_start, interval_stop):
                    item = intervals[interval_position]
                    if item["participant"] != participant and item["end"] > start + 0.05:
                        overlap = True
                        break
                if overlap:
                    continue
                act_id = nite_id(act)
                if not act_id:
                    continue
                row_id = hashlib.sha256(
                    f"icsi-v1:{meeting}:{participant}:{act_id}".encode()).hexdigest()
                spans.append({"id": row_id, "meeting": meeting,
                              "participant": participant, "start": start,
                              "end": end, "text": utterance})
        return spans, len(word_paths), len(act_paths), len(participants)


def write_clip(reader: wave.Wave_read, target: Path,
               start_s: float, end_s: float) -> None:
    rate = reader.getframerate()
    start = max(0, round(start_s * rate))
    stop = min(reader.getnframes(), round(end_s * rate))
    if stop <= start:
        raise ValueError("invalid audio bounds")
    reader.setpos(start)
    frames = reader.readframes(stop - start)
    if len(frames) != (stop - start) * reader.getnchannels() * reader.getsampwidth():
        raise ValueError("truncated source audio")
    with wave.open(str(target), "wb") as output:
        output.setparams(reader.getparams())
        output.writeframes(frames)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True,
                        help="official ICSI core NXT annotation ZIP")
    parser.add_argument("--audio-dir", type=Path, required=True,
                        help="official headset-mix WAVs downloaded for selected meetings")
    parser.add_argument("--audio-pattern", default="{meeting}.interaction.wav",
                        help="filename template with a {meeting} field")
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="new private directory outside the repository")
    parser.add_argument("--seed", default="vaani-v6-icsi-speaker-split-v1")
    parser.add_argument("--max-hours", type=float, default=2.0,
                        help="maximum total clip duration across all splits")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    out = args.out_dir.resolve()
    try:
        out.relative_to(repo)
    except ValueError:
        pass
    else:
        raise SystemExit("private dataset output must be outside the Git repository")
    if out.exists():
        raise SystemExit("refusing to overwrite an existing output directory")
    if args.max_hours <= 0 or args.max_hours > 70:
        raise SystemExit("max-hours must be greater than 0 and no more than 70")
    if "{meeting}" not in args.audio_pattern:
        raise SystemExit("audio-pattern must contain {meeting}")
    spans, word_streams, act_streams, channel_mappings = parse_corpus(args.annotations)
    if not spans:
        raise SystemExit("no valid, timed ICSI dialogue-act spans found")

    # Deterministic ordering, with a hard cap so an initial import is bounded.
    spans.sort(key=lambda row: hashlib.sha256(row["id"].encode()).digest())
    max_seconds = args.max_hours * 3600
    per_split: Counter[str] = Counter()
    speakers: dict[str, set[str]] = defaultdict(set)
    total_seconds = 0.0
    parent = out.parent
    parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=".icsi-v6-", dir=parent))
    try:
        audio_out = scratch / "audio"
        audio_out.mkdir()
        dbs: dict[str, sqlite3.Connection] = {}
        audio_readers: dict[str, wave.Wave_read] = {}
        try:
            for split in ("train", "dev", "test"):
                connection = sqlite3.connect(scratch / f"{split}.sqlite3")
                connection.execute("CREATE TABLE examples (id TEXT PRIMARY KEY, audio_path TEXT NOT NULL, target_text TEXT NOT NULL, sample_weight REAL NOT NULL DEFAULT 1.0)")
                dbs[split] = connection
            seen = set()
            for row in spans:
                split = participant_split(row["participant"], args.seed)
                duration = row["end"] - row["start"]
                if total_seconds + duration > max_seconds:
                    continue
                meeting = row["meeting"]
                audio_path = (args.audio_dir / args.audio_pattern.format(meeting=meeting)).resolve()
                try:
                    audio_path.relative_to(args.audio_dir.resolve())
                except ValueError:
                    continue
                if not audio_path.is_file():
                    continue
                if meeting not in audio_readers:
                    reader = wave.open(str(audio_path), "rb")
                    if reader.getframerate() not in (16_000, 32_000, 44_100, 48_000) or reader.getsampwidth() != 2:
                        reader.close()
                        continue
                    audio_readers[meeting] = reader
                reader = audio_readers[meeting]
                if row["end"] > reader.getnframes() / reader.getframerate():
                    continue
                clip_name = f"{row['id']}.wav"
                clip_path = audio_out / clip_name
                try:
                    write_clip(reader, clip_path, row["start"], row["end"])
                except (OSError, wave.Error, ValueError):
                    clip_path.unlink(missing_ok=True)
                    continue
                final_audio = out / "audio" / clip_name
                try:
                    dbs[split].execute("INSERT INTO examples VALUES (?, ?, ?, ?)",
                                       (row["id"], str(final_audio), row["text"], 1.0))
                except sqlite3.IntegrityError:
                    clip_path.unlink(missing_ok=True)
                    continue
                seen.add(split)
                speakers[split].add(row["participant"])
                per_split[split] += 1
                total_seconds += duration
            if seen != {"train", "dev", "test"}:
                raise RuntimeError("available official audio did not populate all speaker-disjoint splits")
            for connection in dbs.values():
                connection.commit()
                connection.execute("CREATE INDEX examples_audio_idx ON examples(audio_path)")
                connection.commit()
        finally:
            for connection in dbs.values():
                connection.close()
            for reader in audio_readers.values():
                reader.close()

        archive_sha = hashlib.sha256(args.annotations.read_bytes()).hexdigest()
        manifest = [
            f'corpus = "{CORPUS}"', f'license = "{LICENSE}"',
            f'source_url = "{SOURCE_URL}"', f'annotation_archive_sha256 = "{archive_sha}"',
            'split_unit = "participant id; IDs discarded after split assignment"',
            'label = "official NXT orthographic transcript; nonlexical disfmarker excluded"',
            f'max_hours = {args.max_hours}', f'actual_hours = {total_seconds / 3600:.6f}',
            f'word_streams = {word_streams}', f'dialogue_act_streams = {act_streams}',
            f'unique_channel_participant_mappings = {channel_mappings}',
            f'train_rows = {per_split["train"]}', f'dev_rows = {per_split["dev"]}',
            f'test_rows = {per_split["test"]}',
            f'train_speakers = {len(speakers["train"])}',
            f'dev_speakers = {len(speakers["dev"])}',
            f'test_speakers = {len(speakers["test"])}',
            'overlap_policy = "exclude source spans overlapped by another annotated speaker"',
        ]
        (scratch / "provenance.toml").write_text("\n".join(manifest) + "\n", encoding="utf-8")
        (scratch / "audio").mkdir(exist_ok=True)
        os.replace(scratch, out)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"ICSI import ready: train={per_split['train']} dev={per_split['dev']} "
          f"test={per_split['test']} rows; {total_seconds / 3600:.2f} audio hours; "
          f"participant-disjoint; attribution=CC BY 4.0")


if __name__ == "__main__":
    main()
