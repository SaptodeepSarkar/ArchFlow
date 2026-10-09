"""Strict, transcript-free-at-the-logs alignment for automatic V6 labels.

No lexical token may be deleted, inserted, substituted, or reordered. The
trusted reference is an automatic admission check, not a rewrite source; only
case and punctuation are normalized by the deterministic runtime renderer.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_v6_edit_plan import render  # noqa: E402

TOKEN_RE = re.compile(r"https?://[^\s]+(?<![.,!?;:])|/[^\s]+(?<![.,!?;:])|[A-Za-z0-9_](?:[A-Za-z0-9_-]|\.(?=[A-Za-z0-9]))*|[^\w\s]")
PUNCT = {",": "COMMA", ".": "PERIOD", "?": "QUESTION_MARK", "!": "EXCLAMATION_MARK",
         ":": "COLON", ";": "SEMICOLON"}
def words(text: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(text)
            if any(character.isalnum() or character == "_" for character in token)]


def is_word(token: str) -> bool:
    return any(character.isalnum() or character == "_" for character in token)


def build_plan(raw_stt: str, reference: str) -> dict | None:
    """Return a validated source-grounded plan, or None for any lexical risk."""
    if not raw_stt.strip() or not reference.strip():
        return None
    source_tokens = TOKEN_RE.findall(raw_stt)
    reference_words = words(reference)
    if not source_tokens or not reference_words:
        return None

    labels = ["KEEP"] * len(source_tokens)
    if words(raw_stt) != reference_words:
        return None

    punctuation: dict[str, str] = {}
    source_word_positions = [index for index, token in enumerate(source_tokens) if is_word(token)]
    reference_tokens = TOKEN_RE.findall(reference)
    reference_word_index = -1
    for token in reference_tokens:
        if is_word(token):
            reference_word_index += 1
        elif token in PUNCT and reference_word_index >= 0:
            punctuation[str(source_word_positions[reference_word_index])] = PUNCT[token]

    lower_words = words(raw_stt)
    if raw_stt.rstrip().endswith("?") or (lower_words and lower_words[0] in {
        "who", "what", "where", "when", "why", "how", "which", "can", "could", "do", "does", "did", "is", "are", "was", "were"
    }):
        speech = "QUESTION"
    elif raw_stt.rstrip().endswith("!"):
        speech = "EXCLAMATION"
    else:
        speech = "STATEMENT"
    plan = {
        "source_tokens": source_tokens,
        "token_labels": labels,
        "punctuation_after": punctuation,
        "speech_act": speech,
        "structure": "PROSE",
        "emoji_intent": "NONE",
    }
    target = render(plan)
    if words(target) != reference_words:
        return None
    plan["target_text"] = target
    return plan


def validate_auto_row(row: dict) -> bool:
    """Recompute all automatically admitted labels and compare, fail closed."""
    if row.get("source", {}).get("type") != "real_derived":
        return False
    annotation = row.get("annotation", {})
    if annotation.get("method") != "reference-grounded-deterministic-validator":
        return False
    if annotation.get("validator") != "v6-real-lexical-alignment-v1":
        return False
    plan = build_plan(row.get("utterance", {}).get("raw_stt", ""),
                      row.get("utterance", {}).get("reference_transcript", ""))
    if plan is None:
        return False
    for field in ("source_tokens", "token_labels", "punctuation_after", "speech_act", "structure", "emoji_intent"):
        if row.get(field) != plan[field]:
            return False
    return row.get("target_text") == plan["target_text"] == row.get("utterance", {}).get("clean_target")
