#!/usr/bin/env python3
"""Reduce a private Whisper evaluator JSONL into an aggregate-only report.

The input is the legacy evaluator's local JSONL, which contains only hashed row
IDs and numeric counts.  This reducer writes no utterance text, audio path, or
row-level metric, so the resulting report is safe to retain with V6 evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for line_no, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            required = ("reference_words", "literal_errors", "normalized_errors",
                        "normalized_wer", "protected_terms", "missing_protected_terms")
            if not isinstance(row, dict) or not isinstance(row.get("row_id"), str):
                raise ValueError("missing numeric evaluator fields")
            counts = ("reference_words", "literal_errors", "normalized_errors",
                      "protected_terms", "missing_protected_terms")
            if any(type(row.get(key)) is not int or row[key] < 0 for key in counts):
                raise ValueError("metric counts must be nonnegative integers")
            normalized_wer = row.get("normalized_wer")
            if (isinstance(normalized_wer, bool)
                    or not isinstance(normalized_wer, (int, float))
                    or not math.isfinite(normalized_wer) or normalized_wer < 0):
                raise ValueError("normalized WER must be finite and nonnegative")
            if row["missing_protected_terms"] > row["protected_terms"]:
                raise ValueError("missing protected-term count exceeds total")
            rows.append(row)
        except (json.JSONDecodeError, ValueError) as error:
            raise SystemExit(f"invalid evaluator row at line {line_no}") from error
    if not rows:
        raise SystemExit("evaluator output has no rows")
    row_ids = [row["row_id"] for row in rows]
    if len(set(row_ids)) != len(row_ids):
        raise SystemExit("evaluator output has duplicate row IDs")

    reference_words = sum(int(row["reference_words"]) for row in rows)
    literal_errors = sum(int(row["literal_errors"]) for row in rows)
    normalized_errors = sum(int(row["normalized_errors"]) for row in rows)
    protected_terms = sum(int(row["protected_terms"]) for row in rows)
    missing_protected_terms = sum(int(row["missing_protected_terms"]) for row in rows)
    report = {
        "schema_version": 1,
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        # Output files differ across models. This stable digest proves both
        # reports cover exactly the same private rows without releasing IDs.
        "evaluated_row_ids_sha256": hashlib.sha256(
            "\n".join(sorted(row_ids)).encode("utf-8")).hexdigest(),
        "rows": len(rows),
        "reference_words": reference_words,
        "literal_wer_percent": round(100 * literal_errors / max(reference_words, 1), 4),
        "normalized_wer_percent": round(100 * normalized_errors / max(reference_words, 1), 4),
        "mean_row_normalized_wer_percent": round(
            100 * sum(float(row["normalized_wer"]) for row in rows) / len(rows), 4),
        "protected_terms": protected_terms,
        "protected_terms_recognized": protected_terms - missing_protected_terms,
        "protected_term_accuracy_percent": (
            round(100 * (protected_terms - missing_protected_terms) / protected_terms, 4)
            if protected_terms else None
        ),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
