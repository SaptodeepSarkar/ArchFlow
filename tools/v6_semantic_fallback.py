#!/usr/bin/env python3
"""Conservative closed-cue fallback for V6 semantic heads.

This is deliberately not a general language model: it emits a cue only when
the transcript contains an explicit, supported marker. Unknown text returns
the neutral plan so the learned tagger or user can decide.
"""
from __future__ import annotations

import re

EMOJI_CUES = {
    "laughing emoji": "LAUGH", "laugh emoji": "LAUGH",
    "thumbs up emoji": "THUMBS_UP", "heart emoji": "HEART",
    "celebration emoji": "CELEBRATION", "smiley emoji": "OTHER_SUPPORTED",
}
ORDER_MARKERS = {"first", "second", "third", "fourth", "fifth"}


def classify(source: str) -> dict[str, str]:
    low = " ".join(source.casefold().split())
    for phrase, emoji in EMOJI_CUES.items():
        if phrase in low and (low.startswith(phrase) or re.search(r"\b(?:add|insert|use|put|include|send|give)\b", low)):
            return {"structure": "PROSE", "emoji_intent": emoji, "reason": "explicit_emoji_cue"}
    words = re.findall(r"[a-z0-9]+", low)
    marker_count = sum(word in ORDER_MARKERS for word in words)
    if marker_count >= 2:
        return {"structure": "ORDERED_LIST", "emoji_intent": "NONE", "reason": "explicit_order_markers"}
    if re.search(r"\b(?:make|create|give|buy|need|remind me to)\b", low) and re.search(r"\band\b", low):
        return {"structure": "UNORDERED_LIST", "emoji_intent": "NONE", "reason": "explicit_list_cue"}
    return {"structure": "PROSE", "emoji_intent": "NONE", "reason": "no_supported_cue"}


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(); ap.add_argument("text"); args = ap.parse_args()
    print(json.dumps(classify(args.text)))
