#!/usr/bin/env python3
"""Build a deterministic, challenge-disjoint V6 hard-example replay shard.

The phrases are new compositional examples, not copies of the frozen challenge.
They target the measured residuals: punctuation, conservative token edits,
backtracking, list structure, emoji cues, and protected technical spans.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

TOKEN_RE = re.compile(r"https?://[^\s]+(?<![.,!?;:])|/[^\s]+(?<![.,!?;:])|[A-Za-z0-9_](?:[A-Za-z0-9_-]|\.(?=[A-Za-z0-9]))*|[^\w\s]")
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


def build(count: int, excluded: set[str] | None = None) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    excluded = {source.casefold() for source in (excluded or set())}

    def add(source: str, target: str, labels: list[str], punct: dict[str, str], **kw) -> None:
        key = source.casefold()
        if key in seen or key in excluded or len(rows) >= count:
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
    # Lists require an explicit request; nearby ordinary prose is a negative.
    for lead in ("please list", "make a list of"):
        for i in range(0, 8):
            chosen = ITEMS[i:i + 4]; source = lead + " " + " ".join(chosen)
            head = "Please list" if lead == "please list" else "Make a list"
            ts = tokens(source); target = head + ":\n" + "\n".join(f"- {x.title()}" for x in chosen)
            add(source, target, ["KEEP"] * len(ts), {str(len(tokens(lead)) - 1): "COLON"}, category="unordered-list", structure="UNORDERED_LIST")
    for i in range(0, 8):
        chosen = ITEMS[i:i + 4]
        source = "i need " + " ".join(chosen[:-1]) + " and " + chosen[-1]
        ts = tokens(source)
        punctuation = {"2": "COMMA", "3": "COMMA", str(len(ts) - 1): "PERIOD"}
        target = "I need " + ", ".join(chosen[:-1]) + " and " + chosen[-1] + "."
        add(source, target, ["KEEP"] * len(ts), punctuation, category="prose-not-list")

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

    # Negation is protected content, never a generic false-start cue. These
    # controls pair imperative and declarative forms so the tagger learns that
    # "not"/"never" must remain even when the surrounding phrasing changes.
    for subject in SUBJECTS:
        for verb in ("delete", "publish", "send", "restart"):
            source = f"do not {verb} {subject}"
            ts = tokens(source)
            add(source, source[:1].upper() + source[1:] + ".", ["KEEP"] * len(ts),
                {str(len(ts) - 1): "PERIOD"}, category="negation", speech="COMMAND_AS_DATA")
    for subject in SUBJECTS:
        for predicate in ("is not ready", "never finished", "is not connected"):
            source = f"{subject} {predicate}"
            ts = tokens(source)
            add(source, source[:1].upper() + source[1:] + ".", ["KEEP"] * len(ts),
                {str(len(ts) - 1): "PERIOD"}, category="negation")

    # Spoken acronyms need mechanical casing and punctuation while retaining
    # every source token. This is deliberately distinct from entity guessing.
    for term in ("MCP", "CTC", "RNNT", "ONNX", "HTML", "CSS"):
        for template in ("the {term} benchmark is ready", "please review the {term} result", "is the {term} export complete"):
            source = template.format(term=term)
            ts = tokens(source)
            question = source.startswith("is the")
            add(source, source[:1].upper() + source[1:] + ("?" if question else "."),
                ["KEEP"] * len(ts), {str(len(ts) - 1): "QUESTION_MARK" if question else "PERIOD"},
                category="acronym", speech="QUESTION" if question else "STATEMENT")

    # Fresh sentence-boundary variants supplement the older punctuation
    # templates. The held-out exclusion set is applied before admission.
    for subject in SUBJECTS:
        for predicate in ("ready", "working", "available", "connected", "finished", "running", "installed", "offline"):
            for context in ("today", "right now", "after reboot", "on your phone"):
                source = f"is {subject} {predicate} {context}"
                ts = tokens(source)
                add(source, source[:1].upper() + source[1:] + "?", ["KEEP"] * len(ts),
                    {str(len(ts) - 1): "QUESTION_MARK"}, category="punctuation-fresh", speech="QUESTION")
                source = f"i think {subject} is {predicate} {context}"
                ts = tokens(source)
                target = re.sub(r"\bi\b", "I", source, flags=re.IGNORECASE)
                add(source, target[:1].upper() + target[1:] + ".", ["KEEP"] * len(ts),
                    {str(len(ts) - 1): "PERIOD"}, category="punctuation-fresh")
        for predicate in ("fantastic", "ready", "working", "excellent"):
            source = f"wow {subject} is {predicate}"
            ts = tokens(source)
            add(source, source[:1].upper() + source[1:] + "!", ["KEEP"] * len(ts),
                {str(len(ts) - 1): "EXCLAMATION_MARK"}, category="punctuation-fresh", speech="EXCLAMATION")
            source = f"oh {subject} is {predicate}"
            ts = tokens(source)
            target = source[:1].upper() + source[1:]
            add(source, "Oh, " + target[3:] + ".", ["KEEP"] * len(ts),
                {"0": "COMMA", str(len(ts) - 1): "PERIOD"}, category="punctuation-fresh")

    # Contrastive preservation controls: cue words are sometimes content,
    # not edit commands. All targets are deterministic casing/punctuation
    # normalizations, so these rows teach the tagger to retain every word.
    for phrase in (
        "i actually need the backup today", "i actually changed the config",
        "she said sorry before the meeting", "we can do it friday actually",
        "the word um appears in the transcript", "he quoted uh in the demo",
        "please preserve the word hmm", "never remove the word not",
        "i am not ready yet", "do not restart the service",
        "i said friday then i said monday", "i changed friday to monday",
        "i thought it was ready but it is not", "we should keep the first draft",
        "i am unsure whether the upload finished", "maybe the model is working",
    ):
        ts = tokens(phrase)
        normalized = re.sub(r"\bi\b", "I", phrase, flags=re.IGNORECASE)
        target = normalized[:1].upper() + normalized[1:] + ("?" if phrase.startswith(("maybe", "is ")) else ".")
        punct = {str(len(ts) - 1): "QUESTION_MARK" if target.endswith("?") else "PERIOD"}
        add(phrase, target, ["KEEP"] * len(ts), punct, category="cue-preservation",
            speech="QUESTION" if target.endswith("?") else "STATEMENT")

    # Compositional cue variations increase lexical diversity without
    # changing the deterministic target rule or touching held-out sources.
    subjects = ("the upload", "the backup", "the browser", "the service", "the model", "the report")
    contexts = ("today", "right now", "after lunch", "in the test", "on my phone", "before the meeting")
    for subject in subjects:
        for context in contexts:
            source = f"i actually need {subject} {context}"
            ts = tokens(source)
            target = source[:1].upper() + source[1:] + "."
            add(source, target, ["KEEP"] * len(ts), {str(len(ts) - 1): "PERIOD"},
                category="cue-preservation")

    # Explicit retractions contrasted with narration: only the material
    # marked as superseded is removed; reasoning and reported alternatives
    # remain. Targets encode a single unambiguous deterministic cue.
    for old in DAYS:
        for new in DAYS:
            if old == new:
                continue
            source = f"schedule it for {old} no wait schedule it for {new}"
            ts = tokens(source)
            # Remove the first complete clause through the repair cue, keeping
            # the repeated, explicitly corrected clause as the final request.
            second_schedule = ts.index("schedule", 1)
            labels = ["DELETE_RETRACTED" if i < second_schedule else "KEEP" for i in range(len(ts))]
            kept = " ".join(token for i, token in enumerate(ts) if labels[i] == "KEEP")
            add(source, kept[:1].upper() + kept[1:] + ".", labels,
                {str(len(ts) - 1): "PERIOD"}, category="explicit-repair")

    # Fresh, grammatical filler contexts are generated compositionally. The
    # filler position varies, while the only permitted edit is its deletion.
    # Existing held-out phrases are skipped inside add(), then generation
    # continues until the requested quota or this finite recipe is exhausted.
    for filler in FILLERS:
        for prefix in ("i need to", "i can", "we should", "please"):
            for verb in ("check", "open", "save", "review", "run", "send", "copy", "update"):
                for obj in OBJECTS:
                    source = f"{prefix} {filler} {verb} {obj}"
                    ts = tokens(source)
                    filler_index = ts.index(filler)
                    labels = ["DELETE_FILLER" if i == filler_index else "KEEP" for i in range(len(ts))]
                    kept = [token for i, token in enumerate(ts) if i != filler_index]
                    normalized = ["I" if token.casefold() == "i" else token for token in kept]
                    target = " ".join(normalized)
                    target = target[:1].upper() + target[1:] + "."
                    add(source, target, labels, {str(len(ts) - 1): "PERIOD"},
                        category="filler-context")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--count", type=int, default=2000); ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--exclude", type=Path, action="append", default=[],
                     help="JSONL source set to exclude by case-insensitive exact match; may be repeated")
    args = ap.parse_args()
    excluded = set()
    for path in args.exclude:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                source = row.get("source")
                if isinstance(source, str):
                    excluded.add(source.casefold())
    rows = build(args.count, excluded)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    ids_digest = hashlib.sha256("\n".join(r["id"] for r in rows).encode("utf-8")).hexdigest()
    print(json.dumps({"rows": len(rows), "excluded_collisions": len(excluded & {row["source"].casefold() for row in build(args.count)}),
                      "out": str(args.out), "unique_sources": len({r['source'].casefold() for r in rows}),
                      "row_ids_sha256": ids_digest}))


if __name__ == "__main__":
    main()
