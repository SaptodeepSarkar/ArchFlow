#!/usr/bin/env python3
"""Deterministically render a V6 edit plan without regenerating source text."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

EMOJIS = {"LAUGH": "😂", "THUMBS_UP": "👍", "CELEBRATION": "🎉", "HEART": "❤️", "OTHER_SUPPORTED": "🙂"}
PUNCT = {"COMMA": ",", "PERIOD": ".", "QUESTION_MARK": "?", "EXCLAMATION_MARK": "!", "COLON": ":", "SEMICOLON": ";"}
KNOWN_CASE = {"html": "HTML", "css": "CSS", "mcp": "MCP", "ctc": "CTC", "llm": "LLM", "rnnt": "RNNT", "cuda": "CUDA", "api": "API", "url": "URL", "ct2": "CT2", "neovim": "Neovim"}


def preserve_case(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def normalize_token(token: str) -> str:
    if token.casefold() == "i": return "I"
    return KNOWN_CASE.get(token.casefold(), token)


def join_tokens(tokens: list[str]) -> str:
    out = ""
    quote_open = False
    just_opened_quote = False
    just_opened_bracket = False
    for token in tokens:
        if token == '"':
            if quote_open:
                out = out.rstrip() + '"'
            else:
                if out and not out.endswith(" "): out += " "
                out += '"'
                just_opened_quote = True
            quote_open = not quote_open
            continue
        if not out or token in ",.!?:;)]}%": out += token
        elif token == "'" or out.endswith("'"): out += token
        elif just_opened_quote:
            out += token
            just_opened_quote = False
        elif token in "([": out += " " + token
        elif just_opened_bracket:
            out += token
            just_opened_bracket = False
        elif out.endswith(("/", "_", "-")): out += token
        elif token.startswith(("/", ".")): out += " " + token
        else: out += " " + token
        if token in "([": just_opened_bracket = True
    return out


def render(plan: dict) -> str:
    tokens = list(plan["source_tokens"])
    prefix = ""
    if tokens and tokens[0].lower().startswith("case") and tokens[0][4:].isdigit():
        prefix, tokens = tokens[0].capitalize(), tokens[1:]
    if plan.get("emoji_intent", "NONE") != "NONE":
        return f"{prefix} {EMOJIS.get(plan['emoji_intent'], '🙂')}".strip()
    structure = plan.get("structure", "PROSE")
    if structure == "ORDERED_LIST":
        items, current = [], []
        for token in tokens:
            if token.lower() in {"first", "second", "third", "fourth", "fifth"}:
                if current: items.append(current)
                current = []
            else:
                current.append(token)
        if current: items.append(current)
        result = "\n".join(f"{i}. {preserve_case(join_tokens(item))}" for i, item in enumerate(items, 1))
        return f"{prefix} {result}".strip()
    labels = plan["token_labels"][1:] if prefix else plan["token_labels"]
    punctuation = plan.get("punctuation_after", {})
    if prefix:
        punctuation = {str(int(i) - 1): value for i, value in punctuation.items() if int(i) > 0}
    deleted = {"DELETE_FILLER", "DELETE_FALSE_START", "DELETE_RETRACTED"}
    kept = []
    for i, (token, label) in enumerate(zip(tokens, labels)):
        if label in deleted:
            continue
        if token in ",.!?:;" and str(i) not in punctuation:
            continue
        kept.append(token)
    if structure == "UNORDERED_LIST":
        pivot = next((i for i, t in enumerate(kept) if t.lower() in {"need", "needs"}), None)
        if pivot is not None:
            head = join_tokens(kept[:pivot + 1]); items = [x for x in kept[pivot + 1:] if x.casefold() != "and"]
            result = preserve_case(head) + ":\n" + "\n".join(f"- {preserve_case(normalize_token(x))}" for x in items)
            return f"{prefix} {result}".strip()
    text = join_tokens(kept)
    if text: text = text[:1].upper() + text[1:]
    # Rebuild punctuation from source positions. This keeps commas and other
    # marks grounded in the source instead of asking a model to regenerate the
    # complete sentence.
    rebuilt = []
    capitalize_next = False
    for i, (token, label) in enumerate(zip(tokens, labels)):
        if label in deleted: continue
        token = normalize_token(token)
        if label == "CAPITALIZE" and token:
            token = token[:1].upper() + token[1:]
        if token in ",.!?:;": continue
        if capitalize_next and token:
            token = token[:1].upper() + token[1:]
            capitalize_next = False
        rebuilt.append(token)
        mark = PUNCT.get(punctuation.get(str(i), ""))
        if mark:
            rebuilt.append(mark)
            capitalize_next = mark in ".?!"
    if rebuilt:
        text = join_tokens(rebuilt)
        text = text[:1].upper() + text[1:]
    return f"{prefix} {text}".strip()


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("path", type=Path); args = ap.parse_args()
    for line in args.path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            print(json.dumps({"id": row.get("id"), "rendered": render(row), "target": row.get("target_text")}, ensure_ascii=False))


if __name__ == "__main__": main()
