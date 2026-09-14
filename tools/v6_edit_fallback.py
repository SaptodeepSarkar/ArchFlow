#!/usr/bin/env python3
"""Closed, conservative edit-plan fallback for obvious transcript operations."""
from __future__ import annotations

import re

try:
    from .v6_semantic_fallback import classify
except ImportError:
    from v6_semantic_fallback import classify

TOKEN = re.compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")
FILLERS = {"uh", "um", "erm", "hmm", "mmm"}
FUNCTION_DUPES = {"to", "the", "a", "an", "is", "are", "of"}
WH = {"who", "what", "where", "when", "why", "how", "which"}


def plan(source: str) -> dict:
    tokens = TOKEN.findall(source); labels = ["KEEP"] * len(tokens); punctuation = {}
    low = [t.casefold() for t in tokens]
    for i, token in enumerate(low):
        if token in FILLERS: labels[i] = "DELETE_FILLER"
    for i in range(1, len(tokens)):
        if low[i] == low[i - 1] and low[i] in FUNCTION_DUPES:
            labels[i] = "DELETE_FALSE_START"
    # A common spoken correction: discard the earlier value and the marker.
    if "actually" in low:
        i = low.index("actually")
        if i > 0 and i + 1 < len(tokens) and re.search(r"[A-Za-z0-9]", tokens[i - 1]) and re.search(r"[A-Za-z0-9]", tokens[i + 1]):
            labels[i - 1] = "DELETE_RETRACTED"; labels[i] = "DELETE_RETRACTED"
    semantic = classify(source)
    structure = semantic["structure"]; emoji = semantic["emoji_intent"]
    if emoji != "NONE":
        return {"token_labels": labels, "punctuation_after": {}, "speech_act": "STATEMENT", "structure": structure, "emoji_intent": emoji}
    live = [i for i, label in enumerate(labels) if label not in {"DELETE_FILLER", "DELETE_FALSE_START", "DELETE_RETRACTED"}]
    if structure == "UNORDERED_LIST":
        need = next((i for i in live if low[i] in {"need", "needs"}), None)
        if need is not None: punctuation[str(need)] = "COLON"
    elif structure == "PROSE" and live:
        last = live[-1]
        conjunction = next((i for i in live if low[i] == "and"), None)
        if conjunction is not None and conjunction >= 2 and low[live[0]] not in WH:
            punctuation[str(live[live.index(conjunction) - 2])] = "COMMA"
            punctuation[str(live[live.index(conjunction) - 1])] = "COMMA"
        if low[live[0]] in WH: punctuation[str(last)] = "QUESTION_MARK"
        elif low[0] == "no": punctuation["0"] = "COMMA"; punctuation[str(last)] = "PERIOD"
        elif len(live) >= 2 and low[live[0]] == low[live[1]] and low[live[0]] not in {"no", "very"}:
            punctuation[str(live[0])] = "COMMA"; punctuation[str(last)] = "PERIOD"
        elif len(live) >= 3 and low[live[0]] == "very" and low[live[1]] == "very":
            punctuation[str(live[0])] = "COMMA"; punctuation[str(last)] = "PERIOD"
        else: punctuation[str(last)] = "PERIOD"
    speech = "QUESTION" if live and low[live[0]] in WH else "STATEMENT"
    if low and low[0] in {"open", "install", "delete", "send", "run"}: speech = "COMMAND_AS_DATA"
    return {"token_labels": labels, "punctuation_after": punctuation, "speech_act": speech, "structure": structure, "emoji_intent": emoji}


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(); ap.add_argument("text"); args = ap.parse_args()
    print(json.dumps(plan(args.text), ensure_ascii=False))
