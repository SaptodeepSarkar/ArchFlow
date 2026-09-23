#!/usr/bin/env python3
"""Apply explicit human V6 review decisions; never infer approval from a target."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    reviews = {}
    for line in args.reviews.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        review = json.loads(line)
        identifier, decision = review.get("example_id"), review.get("decision")
        reviewer = review.get("reviewer")
        notes = review.get("notes")
        if not identifier or decision not in {"ACCEPT", "CORRECT", "REJECT"} or not isinstance(reviewer, str) or not reviewer.strip() or not isinstance(notes, str) or not notes.strip():
            raise SystemExit("each review needs example_id, ACCEPT/CORRECT/REJECT decision, non-empty reviewer, and non-empty notes")
        if decision == "CORRECT" and (not isinstance(review.get("clean_target"), str) or not review["clean_target"].strip()):
            raise SystemExit(f"CORRECT review needs clean_target: {identifier}")
        if identifier in reviews:
            raise SystemExit(f"duplicate review: {identifier}")
        reviews[identifier] = review
    output, counts = [], {"approved": 0, "rejected": 0, "pending": 0}
    for line in args.candidates.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        review = reviews.get(row["example_id"])
        if review is None:
            counts["pending"] += 1
        elif review["decision"] == "REJECT":
            row["annotation"] = {
                "method": "human-review",
                "review_status": "rejected",
                "reviewer": review["reviewer"].strip(),
                "review_notes": review["notes"].strip(),
            }
            row["labels"] = [*row["labels"], "human_rejected"]
            counts["rejected"] += 1
        else:
            if review["decision"] == "CORRECT":
                row["utterance"]["clean_target"] = review["clean_target"]
            row["annotation"] = {
                "method": "human-review",
                "review_status": "approved",
                "reviewer": review["reviewer"].strip(),
                "review_notes": review["notes"].strip(),
            }
            row["labels"] = [label for label in row["labels"] if label != "formatter_target_unreviewed"]
            row["labels"].append("human_reviewed")
            counts["approved"] += 1
        output.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in output), encoding="utf-8")
    print(json.dumps(counts | {"out": str(args.out)}))


if __name__ == "__main__":
    main()
