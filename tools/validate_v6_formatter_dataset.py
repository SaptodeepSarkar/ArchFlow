#!/usr/bin/env python3
"""Validate source-grounded V6 JSONL rows and reject unsafe label drift."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

LABELS = {"KEEP", "DELETE_FILLER", "DELETE_FALSE_START", "DELETE_RETRACTED", "CAPITALIZE", "NORMALIZE_ALLOWED"}
PUNCT = {"NONE", "COMMA", "PERIOD", "QUESTION_MARK", "EXCLAMATION_MARK", "COLON", "SEMICOLON"}
STRUCT = {"PROSE", "UNORDERED_LIST", "ORDERED_LIST"}
EMOJI = {"NONE", "LAUGH", "THUMBS_UP", "CELEBRATION", "HEART", "OTHER_SUPPORTED"}
TOKEN = re.compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("path", type=Path); args = ap.parse_args(); errors = []; seen = set(); rows = 0
    for n, line in enumerate(args.path.read_text().splitlines(), 1):
        if not line.strip(): continue
        rows += 1
        try: r = json.loads(line)
        except Exception as exc: errors.append((n, f"invalid JSON: {exc}")); continue
        required = {"id", "source", "source_tokens", "token_labels", "punctuation_after", "speech_act", "structure", "emoji_intent", "span_types", "protected_spans", "target_text", "metadata"}
        missing = required - set(r)
        if missing: errors.append((n, f"missing {sorted(missing)}")); continue
        if r["id"] in seen: errors.append((n, "duplicate id"))
        seen.add(r["id"])
        actual = TOKEN.findall(r["source"])
        if actual != r["source_tokens"]: errors.append((n, "source_tokens do not match source"))
        if len(r["source_tokens"]) != len(r["token_labels"]): errors.append((n, "token label length mismatch"))
        if any(x not in LABELS for x in r["token_labels"]): errors.append((n, "unknown token label"))
        if any(x not in PUNCT for x in r["punctuation_after"].values()): errors.append((n, "unknown punctuation label"))
        if r["structure"] not in STRUCT or r["emoji_intent"] not in EMOJI: errors.append((n, "unknown closed label"))
        if not isinstance(r["target_text"], str) or not r["target_text"].strip(): errors.append((n, "empty target"))
        for span in r["protected_spans"]:
            if span not in r["source"]: errors.append((n, f"protected span missing from source: {span}"))
            if span not in r["target_text"]: errors.append((n, f"protected span changed/dropped: {span}"))
        digits = lambda s: "".join(c for c in s if c.isdigit())
        source_digits = digits(" ".join(token for token, label in zip(r["source_tokens"], r["token_labels"])
                                        if label not in {"DELETE_FALSE_START", "DELETE_RETRACTED", "DELETE_FILLER"}))
        target_digits = digits(r["target_text"])
        # Ordered-list rendering legitimately adds 1/2/3 markers. For all
        # source numbers, however, their digit sequence must remain present in
        # order in the target.
        if source_digits and source_digits not in target_digits: errors.append((n, "digit sequence changed"))
        for neg in ("not", "never", "no"):
            if re.search(rf"\b{neg}\b", r["source"], re.I) and not re.search(rf"\b{neg}\b", r["target_text"], re.I):
                errors.append((n, f"negation changed/dropped: {neg}"))
    print(json.dumps({"rows": rows, "errors": len(errors), "valid": not errors}))
    for n, err in errors[:20]: print(f"{args.path}:{n}: {err}")
    raise SystemExit(1 if errors else 0)

if __name__ == "__main__": main()
