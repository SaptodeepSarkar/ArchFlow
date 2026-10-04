#!/usr/bin/env python3
"""Convert the V6 edit-plan control corpus into review-required V6 v2 rows.

This is deliberately *not* a promotion or approval path.  The source corpus
is deterministic synthetic scaffolding, useful for coverage and architecture
experiments but not equivalent to independently authored formatter examples.
Every emitted row remains ``needs_human_review`` and has no split.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


def group_for(source: str) -> str:
    """Match the foundation validator's near-duplicate comparison bucket.

    Keeping every possible compared pair in one group means later splitting
    cannot put template neighbours into distinct evaluation partitions.
    """
    tokens = re.findall(r"[\w']+", source)
    signature = tuple(tokens[:2] + tokens[-2:]) if len(tokens) >= 4 else tuple(tokens)
    encoded = f"{len(tokens) // 4}:{'|'.join(signature)}".encode()
    return "control-family-" + hashlib.sha256(encoded).hexdigest()[:16]


def convert(index: int, item: dict) -> dict:
    categories = list(item.get("metadata", {}).get("categories", []))
    return {
        "schema_version": "vaani.v6.formatter-example/2",
        "example_id": f"v6-control-synthetic-{index:06d}",
        "source": {
            "name": "v6-edit-plan-control",
            "record_id": item["id"],
            "type": "synthetic",
        },
        "provenance": {
            "license_ref": "organization-authored",
            "transformation_history": [
                "deterministic source-grounded template generation",
                "converted from v6 edit-plan control corpus",
                "requires blinded semantic review before split or training",
            ],
        },
        "utterance": {
            "raw_stt": item["source"],
            "reference_transcript": None,
            "clean_target": item["target_text"],
        },
        "stt": {"backend": None, "model": None, "final": True, "words": []},
        "labels": sorted(set(categories + ["meaning_preservation", "template_control"])),
        "language": {
            "primary": "en",
            "code_switching": False,
            "accent_or_domain": "synthetic-template-control",
        },
        "annotation": {
            "method": "deterministic-template-proposal",
            "review_status": "needs_human_review",
            "reviewer": None,
        },
        "split": None,
        "group_id": group_for(item["source"]),
        "audio": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--forbid-sources", type=Path,
                        help="evaluation JSONL whose raw/source text must be excluded")
    args = parser.parse_args()

    forbidden = set()
    if args.forbid_sources:
        for line in args.forbid_sources.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                forbidden.add(str(item.get("source", item.get("utterance", {}).get("raw_stt", ""))).casefold())
    rows, sources, ids, categories, excluded = [], set(), set(), Counter(), 0
    for index, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        source = json.loads(line)
        key = source["source"].casefold()
        if key in forbidden:
            excluded += 1
            continue
        if key in sources:
            raise SystemExit(f"duplicate source at input row {index}: {source['id']}")
        if source["id"] in ids:
            raise SystemExit(f"duplicate control id at input row {index}: {source['id']}")
        sources.add(key); ids.add(source["id"])
        categories.update(source.get("metadata", {}).get("categories", []))
        rows.append(convert(len(rows) + 1, source))

    if not rows:
        raise SystemExit("input has no rows")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({
        "synthetic_candidates": len(rows),
        "forbidden_sources_excluded": excluded,
        "review_status": "needs_human_review",
        "splits_assigned": 0,
        "categories": categories,
        "out": str(args.out),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
