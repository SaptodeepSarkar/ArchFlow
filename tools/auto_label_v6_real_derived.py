#!/usr/bin/env python3
"""Automatically admit only lexically exact real-speech formatter pairs.

Any content-word insertion, substitution, deletion, reordering, or renderer
disagreement excludes the row. No lexical edits are trained from these rows;
they provide real-speech casing/punctuation supervision only. No utterance
text is printed in reports.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

from v6_real_alignment import build_plan


def auto_labels(labels: list[str]) -> list[str]:
    return sorted((set(labels) - {"formatter_target_unreviewed", "human_reviewed"})
                  | {"real_derived", "auto_reference_aligned", "meaning_preservation"})


def load_split_map(split_dir: Path) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for split in ("train", "dev", "test"):
        path = split_dir / f"{split}.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            record_id = str(row["source_record_id"])
            value = (split, str(row["meeting_group"]))
            if record_id in result and result[record_id] != value:
                raise SystemExit("source record assigned to multiple splits or meetings")
            result[record_id] = value
    return result


def load_forbidden(paths: list[Path]) -> set[str]:
    forbidden = set()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            source = row.get("source")
            if isinstance(source, dict):
                source = row.get("utterance", {}).get("raw_stt", "")
            if isinstance(source, str) and source.strip():
                forbidden.add(" ".join(source.casefold().split()))
    return forbidden


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True,
                        help="existing licensed real-derived manifest with raw STT and reference")
    parser.add_argument("--split-dir", type=Path, required=True,
                        help="meeting-isolated train.jsonl/dev.jsonl/test.jsonl directory")
    parser.add_argument("--exclude", type=Path, action="append", default=[],
                        help="held-out source JSONL to exclude by normalized exact text; repeatable")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite output")
    if not args.input.is_file():
        raise SystemExit("input manifest is missing")
    for split in ("train", "dev", "test"):
        if not (args.split_dir / f"{split}.jsonl").is_file():
            raise SystemExit(f"missing {split} split manifest")
    root = Path(__file__).resolve().parents[1]
    out_resolved = args.out.resolve()
    if out_resolved == root or root in out_resolved.parents:
        raise SystemExit("training rows must be written outside the Git worktree")

    split_map = load_split_map(args.split_dir)
    forbidden = load_forbidden(args.exclude)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    seen_sources: set[str] = set()
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=args.out.parent,
                                         prefix=f".{args.out.name}.", suffix=".tmp", delete=False) as output:
            temp_name = output.name
            for line in args.input.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                counts["input_rows"] += 1
                row = json.loads(line)
                record_id = str(row.get("source", {}).get("record_id", ""))
                split_info = split_map.get(record_id)
                if split_info is None:
                    counts["missing_split"] += 1
                    continue
                split, meeting = split_info
                if row.get("source", {}).get("type") != "real_derived":
                    counts["wrong_source_type"] += 1
                    continue
                utterance = row.get("utterance", {})
                raw = utterance.get("raw_stt", "")
                reference = utterance.get("reference_transcript", "")
                key = " ".join(raw.casefold().split())
                if key in forbidden:
                    counts["heldout_source_collision"] += 1
                    continue
                plan = build_plan(raw, reference)
                if plan is None:
                    counts["lexical_or_render_mismatch"] += 1
                    continue
                if key in seen_sources:
                    counts["duplicate_source"] += 1
                    continue
                seen_sources.add(key)
                cleaned = dict(row)
                cleaned["split"] = split
                cleaned["group_id"] = meeting
                cleaned["source_tokens"] = plan["source_tokens"]
                cleaned["token_labels"] = plan["token_labels"]
                cleaned["punctuation_after"] = plan["punctuation_after"]
                cleaned["speech_act"] = plan["speech_act"]
                cleaned["structure"] = plan["structure"]
                cleaned["emoji_intent"] = plan["emoji_intent"]
                cleaned["target_text"] = plan["target_text"]
                cleaned["metadata"] = {**row.get("metadata", {}),
                                        "categories": ["real-derived-auto"],
                                        "source": "ami-reference-aligned"}
                cleaned["utterance"] = {**utterance, "clean_target": plan["target_text"]}
                cleaned["labels"] = auto_labels(row.get("labels", []))
                cleaned["provenance"] = {
                    **row.get("provenance", {}),
                    "transformation_history": list(row.get("provenance", {}).get("transformation_history", []))
                    + ["strict source/reference token alignment",
                       "no lexical edits; case and punctuation normalization only",
                       "deterministic source-grounded V6 renderer"],
                }
                validation_rules = [
                    "human reference and final target-STT hypothesis match exactly in lexical order",
                    "no lexical edits; case and punctuation normalization only",
                    "clean target reproduced by deterministic source-grounded renderer",
                    "meeting-isolated split preserved from the STT manifest",
                ]
                if forbidden:
                    validation_rules.append("exact normalized source exclusions applied before admission")
                cleaned["annotation"] = {
                    "method": "reference-grounded-deterministic-validator",
                    "review_status": "automated_validated",
                    "reviewer": None,
                    "validator": "v6-real-lexical-alignment-v1",
                    "validation_rules": validation_rules,
                }
                output.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
                counts["admitted_rows"] += 1
                counts[f"admitted_{split}"] += 1
        os.replace(temp_name, args.out)
    except BaseException:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)
        raise
    counts["unique_sources"] = len(seen_sources)
    print(json.dumps({**counts, "out": str(args.out)}, sort_keys=True))


if __name__ == "__main__":
    main()
