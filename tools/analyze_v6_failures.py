#!/usr/bin/env python3
"""Report V6 formatter failures by challenge category and prediction head.

The evaluator deliberately stores source/expected/generated plans rather than
rendered prose.  This report keeps failure analysis source-grounded and makes
it possible to choose new examples without tuning on aggregate exactness.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--results", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    source_rows = {r["id"]: r for line in args.data.read_text().splitlines() if line.strip() for r in [json.loads(line)]}
    result_rows = [json.loads(line) for line in args.results.read_text().splitlines() if line.strip()]
    grouped: dict[str, list[dict]] = defaultdict(list)
    failures: list[dict] = []
    head_names = ("token_labels", "punctuation_after", "structure", "speech_act", "emoji_intent")
    head_errors = Counter()

    for result in result_rows:
        source = source_rows.get(result["id"], {})
        categories = source.get("metadata", {}).get("categories", ["uncategorized"])
        expected = result["expected"]
        generated = result["generated"]
        mismatches = [name for name in head_names if expected[name] != generated[name]]
        protected = source.get("protected_spans", [])
        protected_ok = all(
            any(token.casefold() == span.casefold() for token, label in zip(source.get("source_tokens", []), generated["token_labels"]) if label == "KEEP")
            for span in protected
        )
        for name in mismatches:
            head_errors[name] += 1
        row = {
            "id": result["id"],
            "source": result["source"],
            "categories": categories,
            "exact": bool(result["exact"]),
            "token_accuracy": result["token_correct"] / max(1, result["token_count"]),
            "protected_ok": protected_ok,
            "head_mismatches": mismatches,
        }
        if not row["exact"]:
            failures.append(row)
        for category in categories:
            grouped[category].append(row)

    report = {"rows": len(result_rows), "exact": sum(bool(r["exact"]) for r in result_rows),
              "token_accuracy": sum(r["token_correct"] for r in result_rows) / max(1, sum(r["token_count"] for r in result_rows)),
              "head_errors": dict(head_errors), "protected_failures": sum(not r["protected_ok"] for r in failures),
              "by_category": {}}
    for category, rows in sorted(grouped.items()):
        report["by_category"][category] = {
            "rows": len(rows),
            "exact": sum(r["exact"] for r in rows),
            "exact_rate": sum(r["exact"] for r in rows) / len(rows),
            "token_accuracy": sum(r["token_accuracy"] for r in rows) / len(rows),
            "protected_failures": sum(not r["protected_ok"] for r in rows),
            "head_errors": dict(Counter(h for r in rows for h in r["head_mismatches"])),
        }
    report["failures"] = failures
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"rows": report["rows"], "exact": report["exact"], "categories": len(report["by_category"]), "out": str(args.out)}))


if __name__ == "__main__":
    main()
