#!/usr/bin/env python3
"""Validate V6 v2 manifest safety, provenance, and split isolation."""
from __future__ import annotations

import argparse
import difflib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

REQUIRED = {"schema_version", "example_id", "source", "provenance", "utterance", "stt", "labels", "language", "annotation", "split", "group_id", "audio"}
TYPES = {"real_derived", "synthetic", "corpus_derived", "manual"}
REVIEWS = {"needs_human_review", "approved", "rejected"}
SPLITS = {None, "train", "dev", "test"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-approved", action="store_true")
    parser.add_argument("--forbid-sources", type=Path,
                        help="evaluation-only JSONL whose raw text must not enter this manifest")
    parser.add_argument("--near-duplicate-threshold", type=float, default=0.90,
                        help="cross-group token similarity that constitutes leakage")
    args = parser.parse_args()
    if not 0 < args.near_duplicate_threshold <= 1:
        raise SystemExit("near-duplicate-threshold must be in (0, 1]")
    errors, ids, groups, review, labels, normalized_sources = [], set(), {}, Counter(), Counter(), {}
    near_buckets: dict[tuple[int, tuple[str, ...]], list[tuple[int, str, list[str]]]] = {}
    forbidden = set()
    if args.forbid_sources:
        for line in args.forbid_sources.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                forbidden.add(re.sub(r"\s+", " ", item.get("source", item.get("utterance", {}).get("raw_stt", "")).casefold()).strip())
    rows = 0
    for line_number, line in enumerate(args.path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        rows += 1
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{line_number}: invalid JSON: {exc}")
            continue
        missing = REQUIRED - item.keys()
        if missing:
            errors.append(f"{line_number}: missing {sorted(missing)}")
            continue
        if item["schema_version"] != "vaani.v6.formatter-example/2": errors.append(f"{line_number}: schema version")
        if item["example_id"] in ids: errors.append(f"{line_number}: duplicate example_id")
        ids.add(item["example_id"])
        source, utterance, stt, annotation = item["source"], item["utterance"], item["stt"], item["annotation"]
        if source.get("type") not in TYPES: errors.append(f"{line_number}: invalid source type")
        if not isinstance(utterance.get("raw_stt"), str) or not utterance["raw_stt"].strip(): errors.append(f"{line_number}: missing raw_stt")
        if not isinstance(utterance.get("clean_target"), str) or not utterance["clean_target"].strip(): errors.append(f"{line_number}: missing clean_target")
        for field in (utterance.get("raw_stt", ""), utterance.get("clean_target", "")):
            if unicodedata.normalize("NFC", field) != field or any(ord(char) < 32 and char not in "\n\t" for char in field):
                errors.append(f"{line_number}: invalid unicode/control character")
        source_key = re.sub(r"\s+", " ", utterance.get("raw_stt", "").casefold()).strip()
        if source_key in normalized_sources: errors.append(f"{line_number}: duplicate raw_stt (first at {normalized_sources[source_key]})")
        normalized_sources[source_key] = line_number
        if source_key in forbidden: errors.append(f"{line_number}: evaluation-set contamination")
        if not stt.get("final"): errors.append(f"{line_number}: non-final STT")
        if source.get("type") == "real_derived" and (not utterance.get("reference_transcript") or not stt.get("backend") or not stt.get("model")):
            errors.append(f"{line_number}: real-derived evidence incomplete")
        if annotation.get("review_status") not in REVIEWS: errors.append(f"{line_number}: review status")
        if annotation.get("review_status") in {"approved", "rejected"}:
            if annotation.get("method") != "human-review": errors.append(f"{line_number}: finalized review must be human-review")
            if not isinstance(annotation.get("reviewer"), str) or not annotation["reviewer"].strip(): errors.append(f"{line_number}: finalized review missing reviewer")
            if not isinstance(annotation.get("review_notes"), str) or not annotation["review_notes"].strip(): errors.append(f"{line_number}: finalized review missing notes")
        if annotation.get("review_status") == "approved" and "formatter_target_unreviewed" in item.get("labels", []):
            errors.append(f"{line_number}: approved row retains unreviewed target label")
        if item["split"] not in SPLITS: errors.append(f"{line_number}: split")
        if args.require_approved and annotation.get("review_status") != "approved": errors.append(f"{line_number}: unapproved row")
        if item["audio"] and (Path(item["audio"].get("ref", "")).is_absolute() or not item["audio"].get("sha256")):
            errors.append(f"{line_number}: nonportable audio reference")
        for word in stt.get("words", []):
            start, end = word.get("word_start_ms"), word.get("word_end_ms")
            if start is not None and end is not None and (not isinstance(start, int) or not isinstance(end, int) or end < start): errors.append(f"{line_number}: timestamp")
        group = item["group_id"]
        if group in groups and groups[group] != item["split"] and groups[group] is not None and item["split"] is not None: errors.append(f"{line_number}: group split leakage")
        groups.setdefault(group, item["split"])
        token_sequence = re.findall(r"[\w']+", source_key)
        if len(token_sequence) >= 4:
            # A shared head/tail signature cheaply limits comparison to likely
            # template/source variants instead of taking O(n²) on a 100k corpus.
            signature = tuple(token_sequence[:2] + token_sequence[-2:])
            bucket = near_buckets.setdefault((len(token_sequence) // 4, signature), [])
            for other_line, other_group, other_tokens in bucket:
                if other_group == group:
                    continue
                similarity = difflib.SequenceMatcher(a=token_sequence, b=other_tokens, autojunk=False).ratio()
                if similarity >= args.near_duplicate_threshold:
                    errors.append(f"{line_number}: near-duplicate cross-group leakage (line {other_line}, similarity {similarity:.3f})")
            bucket.append((line_number, group, token_sequence))
        review[annotation.get("review_status")] += 1
        labels.update(item.get("labels", []))
    reasons = Counter(error.split(": ", 1)[-1].split(" (")[0] for error in errors)
    print(json.dumps({"rows": rows, "errors": len(errors), "rejection_reasons": reasons,
                      "review_status": review, "phenomena": labels}, sort_keys=True))
    for error in errors[:30]: print(error)
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
