#!/usr/bin/env python3
"""Import only source-grounded rows from existing formatter corpora.

Rows whose target paraphrases, invents, or deletes unsupported content are
rejected. This is deliberately conservative: a smaller trusted pool is better
than teaching the V6 tagger that a grammar dataset is permission to rewrite.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TOKEN = re.compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")
FILLERS = {"uh", "um", "erm", "hmm", "mmm", "actually", "like", "you", "know"}
COMMANDS = {"open", "install", "delete", "send", "run", "check", "compare", "write", "read", "remove"}
EMOJI = {"laughing": "LAUGH", "laugh": "LAUGH", "thumbs": "THUMBS_UP", "celebration": "CELEBRATION", "birthday": "CELEBRATION", "heart": "HEART", "smiley": "OTHER_SUPPORTED", "smile": "OTHER_SUPPORTED"}
PROTECTED = re.compile(r"https?://[^\s]+|/[^\s]+|\b(?:CUDA|MCP|HTML|CSS|CTC|LLM|API|GitHub|Hyprland|Whisper|CT2|RTX 3050)\b|\b[A-Z][A-Z0-9_.-]{2,}\b")


def toks(text: str) -> list[str]: return TOKEN.findall(text)


def content(text: str) -> list[str]: return [x for x in toks(text) if re.search(r"[A-Za-z0-9]", x)]


def extract_source(value: str) -> str:
    value = value.strip()
    match = re.match(r"(?:fix|correct|rewrite|format|remove|identify|improve|paraphrase)[^:]{0,100}:\s*(.*)$", value, re.I | re.S)
    return match.group(1).strip() if match else value


def grounded_labels(source: str, target: str) -> list[str] | None:
    st, tt = content(source), content(target)
    target_tokens = toks(target)
    source_symbols = set(toks(source))
    list_target = bool(re.search(r"(?m)^\s*[-•*]\s", target))
    for symbol in toks(target):
        if re.search(r"[A-Za-z0-9]", symbol) or symbol in {",", ".", "?", "!", ":", ";"}:
            continue
        if symbol == "-" and list_target:
            continue
        if symbol not in source_symbols:
            return None
    labels = ["KEEP"] * len(toks(source))
    pos = 0
    matched: set[int] = set()
    for idx, token in enumerate(toks(source)):
        if not re.search(r"[A-Za-z0-9]", token):
            continue
        norm = token.casefold()
        found = next((j for j in range(pos, len(tt)) if tt[j].casefold() == norm), None)
        if found is not None:
            if token != tt[found]:
                previous_target = target_tokens[:target_tokens.index(tt[found])]
                sentence_start = not previous_target or previous_target[-1] in {".", "?", "!"}
                if not sentence_start:
                    return None
            matched.add(found); pos = found + 1
            continue
        low = norm.strip(".,!?;:")
        duplicate = source.casefold().split().count(low) > 1
        if low in FILLERS or duplicate:
            labels[idx] = "DELETE_FILLER" if low in FILLERS else "DELETE_FALSE_START"
        else:
            return None
    if pos != len(tt) or len(matched) != len(tt):
        return None
    return labels


def make_row(idx: int, source: str, target: str, labels: list[str], origin: str) -> dict | None:
    source_tokens = toks(source)
    target_tokens = toks(target)
    # A leading bullet/number can be ordinary prose copied from a document,
    # not spoken list structure. A one-line source/target must not teach the
    # formatter that every bullet-prefixed sentence is a list.
    stripped_source = source.lstrip()
    if (re.match(r"^[-•*]\s", stripped_source) or re.match(r"^\d+[.)]\s", stripped_source)) and "\n" not in target:
        return None
    protected = sorted(set(PROTECTED.findall(source)))
    if any(span not in target for span in protected):
        return None
    structure = "ORDERED_LIST" if re.search(r"(?m)^\s*\d+[.)]\s", target) else "UNORDERED_LIST" if re.search(r"(?m)^\s*[-•*]\s", target) else "PROSE"
    emoji = next((kind for word, kind in EMOJI.items() if word in source.casefold() and any(ord(c) > 0x1F000 for c in target)), "NONE")
    speech = "QUESTION" if target.rstrip().endswith("?") else "EXCLAMATION" if target.rstrip().endswith("!") else "COMMAND_AS_DATA" if source_tokens and source_tokens[0].casefold() in COMMANDS else "STATEMENT"
    punctuation = {}
    source_content_indices = [i for i, token in enumerate(source_tokens) if re.search(r"[A-Za-z0-9]", token)]
    content_no_punct = 0
    for token in target_tokens:
        if re.search(r"[A-Za-z0-9]", token):
            content_no_punct += 1
            continue
        if token in {",", ".", "?", "!", ":", ";"} and content_no_punct:
            source_index = source_content_indices[min(content_no_punct - 1, len(source_content_indices) - 1)]
            punctuation[str(source_index)] = {",": "COMMA", ".": "PERIOD", "?": "QUESTION_MARK", "!": "EXCLAMATION_MARK", ":": "COLON", ";": "SEMICOLON"}[token]
    categories = [origin]
    if any(x in source.casefold().split() for x in FILLERS): categories.append("filler")
    if structure != "PROSE": categories.append(structure.lower())
    if protected: categories.append("protected")
    return {"id": f"v6-reviewed-{idx:06d}", "source": source, "source_tokens": source_tokens,
            "token_labels": labels, "punctuation_after": punctuation, "speech_act": speech,
            "structure": structure, "emoji_intent": emoji,
            "span_types": {}, "protected_spans": protected, "target_text": target,
            "metadata": {"categories": categories, "source": origin}}


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--inputs", type=Path, nargs="+", required=True); ap.add_argument("--out", type=Path, required=True); args = ap.parse_args()
    rows, seen, rejected = [], set(), 0
    for path in args.inputs:
        for line in path.read_text().splitlines():
            if not line.strip(): continue
            raw = json.loads(line); source = extract_source(raw.get("input", "")); target = raw.get("output", "")
            if not source or not target or source.casefold() in seen: rejected += 1; continue
            labels = grounded_labels(source, target)
            row = make_row(len(rows) + 1, source, target, labels, path.stem) if labels else None
            if row is None: rejected += 1; continue
            seen.add(source.casefold()); rows.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(json.dumps({"accepted": len(rows), "rejected": rejected, "out": str(args.out)}))


if __name__ == "__main__": main()
