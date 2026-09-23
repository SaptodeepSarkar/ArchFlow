#!/usr/bin/env python3
"""Extract a bounded AMI real-speech pilot into portable source-manifest rows."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

CHILD_RANGE = re.compile(r"#id\(([^)]+)\)(?:\.\.id\(([^)]+)\))?")
PRIORITY = {"um", "uh", "erm", "sorry", "actually", "well", "no"}


def spoken_text(words: list[ET.Element]) -> str:
    text = ""
    for word in words:
        value = (word.text or "").strip()
        if not value:
            continue
        if word.get("punc") == "true" and text:
            text += value
        else:
            text += ("" if not text else " ") + value
    return text


def word_map(path: Path) -> tuple[list[str], dict[str, ET.Element]]:
    root = ET.parse(path).getroot()
    timed = [element for element in root if "{http://nite.sourceforge.net/}id" in element.attrib]
    return [element.attrib["{http://nite.sourceforge.net/}id"] for element in timed], {
        element.attrib["{http://nite.sourceforge.net/}id"]: element for element in timed
    }


def dialogue_spans(words_dir: Path, acts_dir: Path, meeting: str) -> list[dict]:
    candidates = []
    for act_file in sorted(acts_dir.glob(f"{meeting}.*.dialog-act.xml")):
        speaker = act_file.name.split(".")[1]
        identifiers, mapping = word_map(words_dir / f"{meeting}.{speaker}.words.xml")
        for act in ET.parse(act_file).getroot():
            child = next((node for node in act if node.tag.endswith("child")), None)
            if child is None:
                continue
            match = CHILD_RANGE.search(child.get("href", ""))
            if not match or match.group(1) not in mapping:
                continue
            start = identifiers.index(match.group(1))
            end = identifiers.index(match.group(2) or match.group(1))
            selected = [mapping[identifier] for identifier in identifiers[start:end + 1]]
            text = spoken_text(selected)
            lexical = [node for node in selected if (node.text or "").strip() and node.get("punc") != "true"]
            if not 3 <= len(lexical) <= 30:
                continue
            start_ms = round(float(selected[0].get("starttime", "0")) * 1000)
            end_ms = round(float(selected[-1].get("endtime", "0")) * 1000)
            if not text or end_ms <= start_ms or end_ms - start_ms > 15_000:
                continue
            identifier = act.attrib["{http://nite.sourceforge.net/}id"]
            priority = sum(token.casefold().strip(".,?!") in PRIORITY for token in text.split())
            candidates.append({"id": identifier, "speaker": speaker, "reference": text,
                               "start_ms": start_ms, "end_ms": end_ms, "priority": priority})
    return candidates


def write_slice(source: wave.Wave_read, destination: Path, start_ms: int, end_ms: int) -> None:
    rate = source.getframerate()
    source.setpos(round(start_ms * rate / 1000))
    frames = source.readframes(round((end_ms - start_ms) * rate / 1000))
    with wave.open(str(destination), "wb") as output:
        output.setparams(source.getparams())
        output.writeframes(frames)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True, help="mono AMI Mix-Headset WAV")
    parser.add_argument("--meeting", default="ES2002a")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--offset", type=int, default=0,
                        help="number of deterministically ranked candidates to skip")
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 25 or args.offset < 0:
        raise SystemExit("limit must be between 1 and 25 for this bounded pilot")
    words = args.annotations / "words"
    acts = args.annotations / "dialogueActs"
    candidates = dialogue_spans(words, acts, args.meeting)
    if not candidates:
        raise SystemExit("no eligible AMI dialogue-act spans found")
    rng = random.Random("v6-ami-pilot-2026-09-23")
    prioritized = [row for row in candidates if row["priority"]]
    regular = [row for row in candidates if not row["priority"]]
    rng.shuffle(prioritized); rng.shuffle(regular)
    selected = (prioritized + regular)[args.offset:args.offset + args.limit]
    if not selected:
        raise SystemExit("offset is beyond eligible AMI dialogue-act spans")
    args.out.mkdir(parents=True, exist_ok=True)
    audio_dir = args.out / "audio"
    audio_dir.mkdir(exist_ok=True)
    manifest = []
    with wave.open(str(args.audio), "rb") as source:
        for index, candidate in enumerate(selected, 1):
            filename = f"{args.meeting}-{args.offset + index:04d}.wav"
            destination = audio_dir / filename
            write_slice(source, destination, candidate["start_ms"], candidate["end_ms"])
            manifest.append({
                "audio_ref": f"audio/{filename}", "reference": candidate["reference"],
                "source_name": "ami-meeting-corpus-v1.6.2", "source_record_id": candidate["id"],
                "license_ref": "https://groups.inf.ed.ac.uk/ami/download/ (CC BY 4.0)",
                "language": "en", "accent_or_domain": "English multiparty meeting",
                "speaker_id": f"{args.meeting}-{candidate['speaker']}",
                "source_timestamps": {"start_ms": candidate["start_ms"], "end_ms": candidate["end_ms"]},
            })
    output = args.out / "source.jsonl"
    output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in manifest), encoding="utf-8")
    print(json.dumps({"rows": len(manifest), "offset": args.offset,
                      "priority_rows": sum(row["priority"] > 0 for row in selected),
                      "source_manifest": str(output), "audio_sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
