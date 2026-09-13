#!/usr/bin/env python3
"""Apply conservative fuzzy contextual vocabulary bias to an STT report."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        next_row = [i]
        for j, right in enumerate(b, 1):
            next_row.append(min(row[j] + 1, next_row[-1] + 1, row[j - 1] + (left != right)))
        row = next_row
    return row[-1]


def vocabulary(root: Path) -> list[str]:
    terms = []
    for path in sorted(root.glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            term = line.strip()
            if term and not term.startswith("#") and " " not in term and term not in terms:
                terms.append(term)
    return [term for term in terms if len(re.sub(r"[^A-Za-z0-9]", "", term)) >= 4]


def bias(text: str, terms: list[str], threshold: float = 0.78) -> tuple[str, list[dict]]:
    candidates = [(term, term.lower()) for term in terms]
    changes = []

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        lower = word.lower()
        if len(lower) < 4:
            return word
        best = None
        for term, candidate in candidates:
            # Do not rewrite ordinary words to a vocabulary item unless the
            # item is visibly an acronym/name or a long technical term.
            if not (term.isupper() or term[:1].isupper() or len(candidate) >= 8):
                continue
            ratio = 1.0 - distance(lower, candidate) / max(len(lower), len(candidate))
            adjusted_threshold = threshold - 0.06 if term.isupper() else threshold
            if ratio >= adjusted_threshold and (best is None or ratio > best[0]):
                best = (ratio, term)
        if best and best[1] != word:
            changes.append({"from": word, "to": best[1], "score": round(best[0], 3)})
            return best[1]
        return word

    return re.sub(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9-]*", replace, text), changes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path)
    ap.add_argument("--vocabulary", type=Path, default=Path("models/vocabulary"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--threshold", type=float, default=0.78)
    args = ap.parse_args()
    terms = vocabulary(args.vocabulary)
    rows = []
    for line in args.report.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        hypothesis = row.get("v5_hypothesis", row.get("hypothesis", ""))
        row["biased_hypothesis"], row["bias_changes"] = bias(hypothesis, terms, args.threshold)
        rows.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"rows": len(rows), "terms": len(terms), "changed_rows": sum(bool(r["bias_changes"]) for r in rows), "out": str(args.out)}))


if __name__ == "__main__":
    main()
