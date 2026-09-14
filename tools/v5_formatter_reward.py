#!/usr/bin/env python3
"""Deterministic reward for Vaani formatter candidates.

The score is deliberately conservative: lexical grounding and safety outweigh
fluency. It is suitable for ranking SFT/DPO/RLVR candidates, not for claiming
human preference quality.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from v5_contract_guard import ALLOWED, _words  # noqa: E402


def reward(source: str, candidate: dict, target: dict | None = None) -> dict:
    op = candidate.get("operation")
    result = candidate.get("result", "")
    text = result if isinstance(result, str) else " ".join(str(x) for x in result.get("items", []))
    source_words = _words(source)
    result_words = _words(text)
    grounded = len(source_words & result_words) / max(1, len(source_words))
    mutation = len(result_words - source_words) / max(1, len(result_words))
    exact = float(target is not None and candidate == target)
    valid = float(op in ALLOWED and isinstance(result, (str, dict)))
    needs_confirmation = bool(re.match(r"\s*(open|install|delete|send|run)\b", source, re.I))
    safety = float(valid and bool(candidate.get("needs_confirmation")) == needs_confirmation)
    operation = float(target is not None and op == target.get("operation"))
    # Protect literal technical terms, names, URLs, paths, and acronym spans.
    protected = set(re.findall(r"(?:https?://\S+|\b[A-Z][A-Za-z0-9_.-]{2,}\b|\b\d+(?:\.\d+)?\b)", source))
    candidate_text = text
    protected_recall = (sum(term.lower() in candidate_text.lower() for term in protected) /
                        max(1, len(protected)))
    score = (0.25 * grounded + 0.15 * (1.0 - mutation) + 0.10 * valid +
             0.15 * safety + 0.15 * operation + 0.10 * protected_recall +
             0.10 * exact)
    return {"score": round(score, 6), "groundedness": round(grounded, 6),
            "mutation": round(mutation, 6), "valid": bool(valid),
            "safety_accuracy": bool(safety), "operation_accuracy": bool(operation),
            "protected_recall": round(protected_recall, 6), "exact": bool(exact)}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("candidate", type=Path)
    ap.add_argument("--target", type=Path)
    args = ap.parse_args()
    target = json.loads(args.target.read_text()) if args.target else None
    print(json.dumps(reward(args.source, json.loads(args.candidate.read_text()), target), ensure_ascii=False))
