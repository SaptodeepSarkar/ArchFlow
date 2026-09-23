#!/usr/bin/env python3
"""Flag, never approve, candidates whose reference may overwrite raw STT content."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

TOKEN = re.compile(r"[\w']+", re.UNICODE)


def tokens(value: str) -> list[str]:
    return [token.casefold().replace("’", "'") for token in TOKEN.findall(value)]


def lcs_length(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    for item in left:
        current = [0]
        for index, other in enumerate(right, 1):
            current.append(previous[index - 1] + 1 if item == other else max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--minimum-lcs", type=float, default=0.85)
    args = parser.parse_args()
    if not 0 < args.minimum_lcs <= 1:
        raise SystemExit("minimum-lcs must be in (0, 1]")
    queue, risks = [], Counter()
    for line in args.input.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        raw = tokens(row["utterance"]["raw_stt"])
        reference = tokens(row["utterance"].get("reference_transcript") or "")
        overlap = lcs_length(raw, reference) / max(len(raw), len(reference), 1)
        flags = []
        if overlap < args.minimum_lcs:
            flags.append("reference_content_mismatch")
        if not raw:
            flags.append("empty_raw_stt")
        if not reference:
            flags.append("missing_reference")
        priority = "critical" if flags else "normal"
        risks.update(flags or ["no_lexical_risk_flag"])
        queue.append({"example_id": row["example_id"], "source": row["source"],
                      "raw_stt": row["utterance"]["raw_stt"],
                      "reference_transcript": row["utterance"]["reference_transcript"],
                      "proposed_target": row["utterance"]["clean_target"],
                      "labels": row["labels"], "lexical_lcs_ratio": round(overlap, 4),
                      "risk_flags": flags, "review_priority": priority,
                      "decision": "PENDING", "clean_target": None, "reviewer": None, "notes": None})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in queue), encoding="utf-8")
    args.report.write_text(json.dumps({"rows": len(queue), "minimum_lcs": args.minimum_lcs,
                                       "risk_flags": risks,
                                       "critical_review_rows": sum(row["review_priority"] == "critical" for row in queue)}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(queue), "critical_review_rows": sum(row["review_priority"] == "critical" for row in queue), "out": str(args.out)}))


if __name__ == "__main__":
    main()
