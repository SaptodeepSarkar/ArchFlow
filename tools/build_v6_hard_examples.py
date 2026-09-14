#!/usr/bin/env python3
"""Build a deterministic, challenge-disjoint V6 hard-example replay shard.

The phrases are new compositional examples, not copies of the frozen challenge.
They target the measured residuals: punctuation, conservative token edits,
backtracking, list structure, emoji cues, and protected technical spans.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TOKEN_RE = re.compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")
TERMS = ["CUDA", "MCP", "HTML", "CSS", "CTC", "RNNT", "ONNX", "Hyprland", "Neovim", "Kotlin", "PostgreSQL", "RTX 3050"]
FILLERS = ["uh", "um", "erm", "hmm"]
SUBJECTS = ["the build", "the app", "the model", "the service", "the benchmark", "the upload", "the keyboard", "the report"]
OBJECTS = ["the browser", "the logs", "the tests", "the config", "the recording", "the backup", "the project", "the terminal"]
ITEMS = ["apples", "bananas", "bread", "coffee", "eggs", "flour", "lentils", "milk", "rice", "salt", "tea", "water"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def protected(source: str) -> list[str]:
    found = re.findall(r"https?://[^\s]+|/[^\s]+|\b(?:CUDA|MCP|HTML|CSS|CTC|RNNT|ONNX|Hyprland|Neovim|Kotlin|PostgreSQL|RTX 3050)\b", source)
    return sorted(set(found))


def make(idx: int, source: str, target: str, labels: list[str], punct: dict[str, str], *, category: str,
         speech: str = "STATEMENT", structure: str = "PROSE", emoji: str = "NONE") -> dict:
    ts = tokens(source)
    if len(ts) != len(labels):
        raise ValueError((source, ts, labels))
    return {"id": f"v6-hard-{idx:06d}", "source": source, "source_tokens": ts,
            "token_labels": labels, "punctuation_after": punct,
            "speech_act": speech, "structure": structure, "emoji_intent": emoji,
            "span_types": {str(i): "TECHNICAL_TERM" for i, t in enumerate(ts) if t in TERMS},
            "protected_spans": protected(source), "target_text": target,
            "metadata": {"categories": [category], "source": "hard-replay-generated"}}


def build(count: int) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()

    def add(source: str, target: str, labels: list[str], punct: dict[str, str], **kw) -> None:
        key = source.casefold()
        if key in seen or len(rows) >= count:
            return
        seen.add(key); rows.append(make(len(rows) + 1, source, target, labels, punct, **kw))

    # New question/statement/exclamation combinations exercise terminal and
    # internal punctuation without using the frozen challenge wording.
    for subject in SUBJECTS:
        for verb in ("ready", "available", "working", "finished", "connected"):
            source = f"is {subject} {verb}"
            ts = tokens(source); add(source, source[:1].upper() + source[1:] + "?", ["KEEP"] * len(ts), {str(len(ts) - 1): "QUESTION_MARK"}, category="punctuation", speech="QUESTION")
    for subject in SUBJECTS:
        for context in ("today", "right now", "in the test", "on the phone"):
            source = f"{subject} is working {context}"
            ts = tokens(source); add(source, source[:1].upper() + source[1:] + ".", ["KEEP"] * len(ts), {str(len(ts) - 1): "PERIOD"}, category="punctuation")
    for obj in OBJECTS:
        source = f"that is fantastic {obj}"
        ts = tokens(source); add(source, source[:1].upper() + source[1:] + "!", ["KEEP"] * len(ts), {str(len(ts) - 1): "EXCLAMATION_MARK"}, category="punctuation", speech="EXCLAMATION")

    # Filler removal with different lexical surroundings.
    for filler in FILLERS:
        for verb in ("check", "open", "save", "review", "run", "send", "copy", "update"):
            for obj in OBJECTS[:6]:
                source = f"{filler} {verb} {obj}"
                ts = tokens(source); n = len(tokens(filler)); clean = " ".join(ts[n:])
                add(source, clean[:1].upper() + clean[1:] + ".", ["DELETE_FILLER"] * n + ["KEEP"] * (len(ts) - n), {str(len(ts) - 1): "PERIOD"}, category="filler", speech="COMMAND_AS_DATA")

    # A small, explicit false-start family; content words remain source-bound.
    for old, new in zip(("Monday", "Tuesday", "Thursday", "Friday"), ("Wednesday", "Thursday", "Saturday", "Sunday")):
        for verb in ("schedule", "move", "publish", "review", "deploy"):
            source = f"{verb} it on {old} actually on {new}"
            ts = tokens(source); start = ts.index(old); end = ts.index(new)
            labels = ["DELETE_RETRACTED" if start <= i < end else "KEEP" for i in range(len(ts))]
            kept = " ".join(t for i, t in enumerate(ts) if labels[i] == "KEEP")
            add(source, kept[:1].upper() + kept[1:] + ".", labels, {str(len(ts) - 1): "PERIOD"}, category="backtracking")

    # Ordered and unordered lists with varied lead-ins and item counts.
    for a, b, c, d in ((ITEMS[i], ITEMS[i + 1], ITEMS[i + 2], ITEMS[i + 3]) for i in range(0, 8)):
        source = f"first {a} second {b} third {c} fourth {d}"
        ts = tokens(source); target = "\n".join(f"{i}. {x.title()}" for i, x in enumerate((a, b, c, d), 1))
        add(source, target, ["KEEP"] * len(ts), {}, category="ordered-list", structure="ORDERED_LIST")
    for lead in ("i need", "please get", "make a list of", "remember"):
        for i in range(0, 8):
            chosen = ITEMS[i:i + 4]; source = lead + " " + " ".join(chosen)
            ts = tokens(source); target = lead.title() + ":\n" + "\n".join(f"- {x.title()}" for x in chosen)
            add(source, target, ["KEEP"] * len(ts), {str(len(tokens(lead)) - 1): "COLON"}, category="unordered-list", structure="UNORDERED_LIST")

    # Explicit emoji requests use unseen wording while remaining closed-label
    # and source-grounded.
    emoji_phrases = [("send me a laughing emoji", "😂", "LAUGH"), ("put a thumbs-up emoji here", "👍", "THUMBS_UP"),
                     ("add a heart symbol", "❤️", "HEART"), ("include a celebration emoji", "🎉", "CELEBRATION")]
    for phrase, symbol, intent in emoji_phrases:
        ts = tokens(phrase); add(phrase, symbol, ["KEEP"] * len(ts), {}, category="emoji", speech="EXCLAMATION", emoji=intent)

    # Technical/name preservation with punctuation remains a hard lexical case.
    for term in TERMS:
        for template in ("please compare {term} with the old build", "the {term} error is fixed", "can you explain {term} to me"):
            source = template.format(term=term); ts = tokens(source); terminal = "?" if source.startswith("can you") else "."
            punct_kind = "QUESTION_MARK" if terminal == "?" else "PERIOD"
            add(source, source[:1].upper() + source[1:] + terminal, ["KEEP"] * len(ts), {str(len(ts) - 1): punct_kind}, category="technical", speech="QUESTION" if terminal == "?" else "STATEMENT")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--count", type=int, default=600); ap.add_argument("--out", type=Path, required=True); args = ap.parse_args()
    rows = build(args.count); args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(json.dumps({"rows": len(rows), "out": str(args.out), "unique_sources": len({r['source'].casefold() for r in rows})}))


if __name__ == "__main__":
    main()
