#!/usr/bin/env python3
"""Evaluate a learned V6 plan with conservative closed-rule overrides.

The learned tagger remains responsible for ordinary cases.  Explicitly
recognized filler, backtracking, list, punctuation, and emoji cues may be
overridden by deterministic code; URLs, snippets, replacements, and commands
remain outside the model.  Metrics include rendered exactness because plan
exactness alone does not describe the user-visible result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from render_v6_edit_plan import render
from v6_edit_fallback import plan as closed_plan


def merge(source: str, learned: dict) -> dict:
    closed = closed_plan(source)
    merged = dict(learned)
    # Closed token operations are authoritative only where they actually mark
    # a deletion; otherwise preserve the model's source-grounded label.
    labels = list(learned["token_labels"])
    for i, label in enumerate(closed["token_labels"]):
        if label != "KEEP" and i < len(labels): labels[i] = label
    merged["token_labels"] = labels
    # A non-empty closed punctuation plan is an explicit rule match, not a
    # language-model guess.
    if closed["punctuation_after"]:
        merged["punctuation_after"] = closed["punctuation_after"]
    if closed["structure"] != "PROSE": merged["structure"] = closed["structure"]
    if closed["emoji_intent"] != "NONE": merged["emoji_intent"] = closed["emoji_intent"]
    if closed["speech_act"] != "STATEMENT": merged["speech_act"] = closed["speech_act"]
    return merged


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--data", type=Path, required=True); ap.add_argument("--results", type=Path, required=True); ap.add_argument("--out", type=Path, required=True); args = ap.parse_args()
    source = {r["id"]: r for line in args.data.read_text().splitlines() if line.strip() for r in [json.loads(line)]}
    out = []; rendered_exact = 0; protected_failures = 0
    for line in args.results.read_text().splitlines():
        if not line.strip(): continue
        result = json.loads(line); row = source[result["id"]]
        plan = {"source_tokens": row["source_tokens"], **merge(row["source"], result["generated"])}
        rendered = render(plan); expected = row["target_text"]
        exact = rendered == expected; rendered_exact += exact
        kept = {token.casefold() for token, label in zip(row["source_tokens"], plan["token_labels"]) if label == "KEEP"}
        protected_ok = all(span.casefold() in kept for span in row.get("protected_spans", []))
        protected_failures += not protected_ok
        out.append({"id": row["id"], "source": row["source"], "rendered": rendered, "target": expected, "exact": exact, "protected_ok": protected_ok, "categories": row.get("metadata", {}).get("categories", [])})
    report = {"rows": len(out), "rendered_exact": rendered_exact, "rendered_exact_rate": rendered_exact / max(1, len(out)), "protected_failures": protected_failures, "rows_detail": out}
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("rows", "rendered_exact", "rendered_exact_rate", "protected_failures")}))


if __name__ == "__main__": main()
