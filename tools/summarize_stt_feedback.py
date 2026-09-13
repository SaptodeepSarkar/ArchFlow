#!/usr/bin/env python3
"""Create an aggregate, transcript-free audit of a scored STT report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.report.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("report contains no rows")
    ref_words = sum(len(str(row.get("reference", "")).split()) for row in rows)
    substitutions = sum(int(row.get("substitutions", 0)) for row in rows)
    deletions = sum(int(row.get("deletions", 0)) for row in rows)
    insertions = sum(int(row.get("insertions", 0)) for row in rows)
    protected_total = sum(len(row.get("protected_terms", [])) for row in rows)
    protected_missing = sum(len(row.get("missing_protected_terms", [])) for row in rows)
    errors = sum(len(row.get("errors", [])) for row in rows)
    result = {
        "rows": len(rows),
        "reference_words": ref_words,
        "word_errors": errors,
        "wer_from_totals": round((substitutions + deletions + insertions) / max(1, ref_words), 6),
        "mean_row_wer": round(sum(float(row.get("wer", 0.0)) for row in rows) / len(rows), 6),
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "substitution_rate": round(substitutions / max(1, ref_words), 6),
        "deletion_rate": round(deletions / max(1, ref_words), 6),
        "insertion_rate": round(insertions / max(1, ref_words), 6),
        "mean_reward": round(sum(float(row.get("reward", 0.0)) for row in rows) / len(rows), 6),
        "protected_terms": protected_total,
        "protected_terms_missing": protected_missing,
        "protected_term_accuracy": round(1.0 - protected_missing / max(1, protected_total), 6),
        "reference_confirmed_rows": sum(bool(row.get("reference_confirmed")) for row in rows),
        "source_report": str(args.report),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
