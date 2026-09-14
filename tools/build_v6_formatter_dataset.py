#!/usr/bin/env python3
"""Build a deterministic, source-grounded V6 formatter corpus.

This creates unique compositional rows from reviewed templates. It is a
bootstrap corpus for the architecture and must be supplemented with human
review and real failure examples before promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from pathlib import Path

FILLERS = ["uh", "um", "erm", "hmm", "mmm", "actually", "you know", "let me think"]
TERMS = ["CUDA", "MCP", "HTML", "CSS", "CTC", "RNNT", "ONNX", "CT2", "Hyprland", "GitHub", "GitLab", "Neovim", "Android", "Kotlin", "Python", "Rust", "SQLite", "PostgreSQL", "RTX 3050", "WhisperFlow"]
ITEMS = ["bread", "milk", "eggs", "coffee", "soap", "shampoo", "toothpaste", "rice", "apples", "bananas", "lentils", "flour", "salt", "tea", "biscuits", "detergent", "batteries", "notebooks", "medicine", "water"]
VERBS = ["open", "install", "delete", "send", "run", "check", "compare", "update", "build", "review", "save", "find", "copy", "rename"]
OBJECTS = ["the browser", "the file", "the tests", "my GitHub link", "the logs", "the settings", "the audio", "the database", "the project", "the report", "the terminal", "the backup"]
QUESTIONS = [
    "where are you going", "what is the MCP spec", "why did the build fail", "can you check the logs",
    "how do I install CUDA", "when should I run the tests", "which file contains the config",
    "is the Android build ready", "could you compare the two models", "what happened to the upload",
]
SUBJECTS = ["the build", "the app", "the model", "the service", "the keyboard", "the benchmark", "the recording", "the dataset"]
CONTEXTS = ["in the morning", "before lunch", "after the meeting", "on my laptop", "for the next release", "in the test folder", "with the current config"]
PATHS = ["/tmp/test", "/home/user/project", "/work/vaani", "/data/audio", "/var/log/app", "the backup"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
EMOJIS = [("laughing emoji", "😂", "LAUGH"), ("thumbs up emoji", "👍", "THUMBS_UP"),
          ("celebration emoji", "🎉", "CELEBRATION"), ("heart emoji", "❤️", "HEART")]


def tokens(text: str) -> list[str]:
    return re.findall(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]", text)


def protected(source: str) -> list[str]:
    found = re.findall(r"https?://[^\s]+|/[^\s]+|\b(?:CUDA|MCP|HTML|CSS|CTC|GitHub|Hyprland|RTX 3050)\b|\b[A-Z][A-Z0-9_.-]{2,}\b", source)
    return sorted(set(found))


def row(idx: int, source: str, target: str, labels: list[str], punctuation: dict[str, str],
        speech: str = "STATEMENT", structure: str = "PROSE", emoji: str = "NONE",
        categories: list[str] | None = None) -> dict:
    ts = tokens(source)
    assert len(ts) == len(labels), (source, ts, labels)
    spans = {str(i): "TECHNICAL_TERM" for i, t in enumerate(ts) if t in TERMS}
    return {"id": f"v6-{idx:06d}", "source": source, "source_tokens": ts,
            "token_labels": labels, "punctuation_after": punctuation,
            "speech_act": speech, "structure": structure, "emoji_intent": emoji,
            "span_types": spans, "protected_spans": protected(source),
            "target_text": target,
            "metadata": {"categories": categories or ["preservation"], "source": "generated-template"}}


def build(count: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    out: list[dict] = []
    seen: set[str] = set()
    def add(source: str, target: str, labels: list[str], punctuation: dict[str, str], **kw) -> None:
        key = source.lower()
        if key in seen:
            # A repeated source is not new information.  Reject it instead of
            # adding artificial CaseN markers that would leak an identity token
            # into the training task.
            return
        if len(out) < count:
            seen.add(key); out.append(row(len(out) + 1, source, target, labels, punctuation, **kw))
    attempts = 0
    max_attempts = max(1000, count * 100)
    while len(out) < count:
        attempts += 1
        if attempts > max_attempts:
            raise RuntimeError(f"could only generate {len(out)} unique rows after {attempts} attempts; expand generators")
        # Random selection avoids deadlocking on a small category (for
        # example, the four closed emoji cues) once that category is
        # exhausted.  The resulting corpus is still deterministic by seed.
        kind = rng.randrange(10)
        if kind == 0:
            q = rng.choice(QUESTIONS); ts = tokens(q); add(q, q[:1].upper() + q[1:] + "?", ["KEEP"] * len(ts), {str(len(ts)-1): "QUESTION_MARK"}, speech="QUESTION", categories=["question"])
        elif kind == 1:
            f = rng.choice(FILLERS); term = rng.choice(TERMS); source = f"{f} {rng.choice(VERBS)} {term} version {rng.randint(1, 25)} point {rng.randint(0, 9)} {rng.choice(CONTEXTS)}"
            ts = tokens(source); labels = ["DELETE_FILLER"] * len(tokens(f)) + ["KEEP"] * (len(ts) - len(tokens(f)))
            clean = source[len(f) + 1:]
            add(source, clean[:1].upper() + clean[1:] + ".", labels, {str(len(ts)-1): "PERIOD"}, speech="COMMAND_AS_DATA", categories=["filler", "technical", "command-as-data"])
        elif kind in (2, 3):
            chosen = rng.sample(ITEMS, 4); source = rng.choice(["I need ", "please list ", "make a list of "]) + " ".join(chosen); ts = tokens(source)
            prefix = "I need:" if source.startswith("I need") else ("Please list:" if source.startswith("please") else "Make a list:")
            target = prefix + "\n" + "\n".join(f"- {x.capitalize()}" for x in chosen)
            add(source, target, ["KEEP"] * len(ts), {"1": "COLON"}, structure="UNORDERED_LIST", categories=["unordered-list"])
        elif kind == 4:
            chosen = rng.sample(ITEMS, rng.choice([3, 4, 5])); markers = ["first", "second", "third", "fourth", "fifth"]
            source = " ".join(f"{m} {x}" for m, x in zip(markers, chosen))
            ts = tokens(source); target = "1. " + chosen[0].capitalize() + "\n2. " + chosen[1].capitalize() + "\n3. " + chosen[2].capitalize()
            if len(chosen) > 3: target += "\n" + "\n".join(f"{i + 1}. {x.capitalize()}" for i, x in enumerate(chosen[3:], 3))
            add(source, target, ["KEEP"] * len(ts), {}, structure="ORDERED_LIST", categories=["ordered-list"])
        elif kind == 5:
            spoken, symbol, intent = rng.choice(EMOJIS); ts = tokens(spoken)
            add(spoken, symbol, ["KEEP"] * len(ts), {}, speech="EXCLAMATION", emoji=intent, categories=["emoji"])
        elif kind == 6:
            verb = rng.choice(VERBS); obj = rng.choice(OBJECTS); source = f"{verb} {obj}"
            add(source, source[:1].upper() + source[1:] + ".", ["KEEP"] * len(tokens(source)), {str(len(tokens(source))-1): "PERIOD"}, speech="COMMAND_AS_DATA", categories=["command-as-data"])
        elif kind == 7:
            term = rng.choice(TERMS); source = f"{rng.choice(VERBS)} {term} {rng.choice(CONTEXTS)}"; target = source[:1].upper() + source[1:] + "."
            add(source, target, ["KEEP"] * len(tokens(source)), {str(len(tokens(source))-1): "PERIOD"}, categories=["technical", "preservation"])
        elif kind == 8:
            day1, day2 = rng.sample(DAY_NAMES, 2); source = f"{rng.choice(VERBS)} {rng.choice(SUBJECTS)} on {day1} actually {day2}"
            ts = tokens(source); first = ts.index(day1); second = ts.index(day2)
            labels = ["DELETE_RETRACTED" if first <= i < second else "KEEP" for i in range(len(ts))]
            target = " ".join(t for i, t in enumerate(ts) if labels[i] == "KEEP")
            add(source, target[:1].upper() + target[1:] + ".", labels, {str(len(ts) - 1): "PERIOD"}, categories=["backtracking"])
        else:
            source = f"please do not {rng.choice(VERBS)} {rng.choice(PATHS)}"
            add(source, source.capitalize() + ".", ["KEEP"] * len(tokens(source)), {str(len(tokens(source))-1): "PERIOD"}, categories=["negation", "path"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--count", type=int, default=10000); ap.add_argument("--seed", type=int, default=20260914); ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(); rows = build(args.count, args.seed); args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)); print(json.dumps({"rows": len(rows), "out": str(args.out), "seed": args.seed}))


if __name__ == "__main__": main()
