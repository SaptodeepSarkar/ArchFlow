#!/usr/bin/env python3
"""Build a reproducible, bounded AMI acquisition plan for V6 real-derived data.

The output is *source evidence*, not V6 formatter training data.  It contains
only licensed transcript spans and official audio URLs; downstream processing
must obtain the audio, run the frozen target STT, and receive human review.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from build_v6_ami_pilot import dialogue_spans

BASE_URL = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/HeadsetAudio"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target-slices", type=int, default=50_000)
    args = parser.parse_args()
    if args.target_slices < 1:
        raise SystemExit("--target-slices must be positive")

    words, acts = args.annotations / "words", args.annotations / "dialogueActs"
    meetings = sorted({path.name.split(".")[0] for path in acts.glob("*.dialog-act.xml")})
    per_meeting = {meeting: dialogue_spans(words, acts, meeting) for meeting in meetings}
    available = sum(map(len, per_meeting.values()))
    if available < args.target_slices:
        raise SystemExit(f"only {available} eligible source slices, need {args.target_slices}")

    # Round-robin provides broad speaker/session coverage instead of filling
    # the pool from the longest meetings first.  Within each meeting, rows with
    # audible repair/filler cues lead, then stable source order breaks ties.
    for rows in per_meeting.values():
        rows.sort(key=lambda row: (-row["priority"], row["start_ms"], row["id"]))
    selected, cursor = [], defaultdict(int)
    while len(selected) < args.target_slices:
        made_progress = False
        for meeting in meetings:
            index = cursor[meeting]
            rows = per_meeting[meeting]
            if index >= len(rows):
                continue
            item = dict(rows[index]); item["meeting"] = meeting
            selected.append(item); cursor[meeting] += 1; made_progress = True
            if len(selected) == args.target_slices:
                break
        if not made_progress:
            raise AssertionError("selection stalled")

    needed_meetings = sorted({row["meeting"] for row in selected})
    args.out.mkdir(parents=True, exist_ok=True)
    audio_plan = []
    for meeting in needed_meetings:
        filename = f"{meeting}.Mix-Headset.wav"
        audio_plan.append({
            "meeting": meeting,
            "filename": filename,
            "url": f"{BASE_URL}/{filename}",
            "license_ref": "https://groups.inf.ed.ac.uk/ami/download/ (CC BY 4.0)",
        })
    source_rows = []
    for row in selected:
        source_rows.append({
            "source_name": "ami-meeting-corpus-v1.6.2",
            "source_record_id": row["id"],
            "meeting": row["meeting"],
            "speaker_id": f"{row['meeting']}-{row['speaker']}",
            "reference": row["reference"],
            "source_timestamps": {"start_ms": row["start_ms"], "end_ms": row["end_ms"]},
            "priority_cue": row["priority"],
            "license_ref": "https://groups.inf.ed.ac.uk/ami/download/ (CC BY 4.0)",
            "language": "en",
            "accent_or_domain": "English multiparty meeting",
        })
    (args.out / "audio-download-plan.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in audio_plan), encoding="utf-8")
    (args.out / "source-slice-plan.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in source_rows), encoding="utf-8")
    (args.out / "manifest.json").write_text(json.dumps({
        "source": "AMI manual annotations v1.6.2",
        "license": "CC BY 4.0",
        "eligible_slices": available,
        "selected_slices": len(source_rows),
        "meetings": len(needed_meetings),
        "selection": "round-robin meetings; priority cue then source order",
        "status": "source-only; audio/STT/review still required",
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"eligible_slices": available, "selected_slices": len(source_rows),
                      "meetings": len(needed_meetings), "out": str(args.out)}))


if __name__ == "__main__":
    main()
