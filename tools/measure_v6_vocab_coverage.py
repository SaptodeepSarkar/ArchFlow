#!/usr/bin/env python3
"""Measure curated vocabulary coverage without printing transcript text.

Input manifests may use the V6 ``utterance.reference_transcript`` schema or
the trainer's ``text``/``reference`` fields. Output contains only hashes,
counts, pack names, and the curated term names.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "models" / "vocabulary"


def read_packs(names: list[str]) -> list[str]:
    terms: list[str] = []
    for name in names:
        path = PACK_ROOT / f"{name}.txt"
        if not path.is_file():
            raise ValueError(f"unknown vocabulary pack: {name}")
        for raw in path.read_text(encoding="utf-8").splitlines():
            term = raw.strip()
            if term and not term.startswith("#") and term not in terms:
                terms.append(term)
    return terms


def row_text(row: dict) -> str:
    utterance = row.get("utterance")
    if isinstance(utterance, dict) and isinstance(utterance.get("reference_transcript"), str):
        return utterance["reference_transcript"]
    for key in ("reference", "text"):
        if isinstance(row.get(key), str):
            return row[key]
    raise ValueError("manifest row has no recognized reference-text field")


def measure(manifest: Path, pack_names: list[str]) -> dict:
    terms = read_packs(pack_names)
    patterns = {
        term: re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)
        for term in terms
    }
    per_term = {term: 0 for term in terms}
    rows = clips_with_terms = 0
    for line_no, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("manifest row must be an object")
            text = row_text(row)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid manifest row at line {line_no}") from error
        rows += 1
        row_hits = 0
        for term, pattern in patterns.items():
            if pattern.search(text):
                per_term[term] += 1
                row_hits += 1
        clips_with_terms += bool(row_hits)

    return {
        "schema_version": 1,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "packs": pack_names,
        "rows": rows,
        "terms_total": len(terms),
        "terms_present": sum(count > 0 for count in per_term.values()),
        "clips_with_terms": clips_with_terms,
        "term_clip_counts": per_term,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--packs", nargs="+", required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = measure(args.manifest, args.packs)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    serialized = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized, encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "manifest_sha256", "packs", "rows", "terms_total", "terms_present", "clips_with_terms"
    )}, sort_keys=True))


if __name__ == "__main__":
    main()
