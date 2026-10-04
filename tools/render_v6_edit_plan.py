#!/usr/bin/env python3
"""Deterministically render a V6 edit plan without regenerating source text."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EMOJIS = {"LAUGH": "😂", "THUMBS_UP": "👍", "CELEBRATION": "🎉", "HEART": "❤️", "OTHER_SUPPORTED": "🙂"}
EMOJI_PHRASES = {"LAUGH": ("laughing", "emoji"), "THUMBS_UP": ("thumbs", "up", "emoji"),
                 "CELEBRATION": ("celebration", "emoji"), "HEART": ("heart", "emoji")}
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
        intent = plan["emoji_intent"]
        categories = plan.get("metadata", {}).get("categories", [])
        if "explicit-formatting" not in categories:
            return f"{prefix} {EMOJIS.get(intent, '🙂')}".strip()
        phrase = EMOJI_PHRASES.get(intent)
        replacement = EMOJIS.get(intent, "🙂")
        replaced = False
        if phrase:
            folded = [token.casefold() for token in tokens]
            for start in range(len(tokens) - len(phrase) + 1):
                if tuple(folded[start:start + len(phrase)]) == phrase:
                    tokens[start:start + len(phrase)] = [replacement]
                    replaced = True
                    break
        if not replaced:
            return f"{prefix} {replacement}".strip()
        text = join_tokens(tokens)
        if text:
            text = text[:1].upper() + text[1:]
        mark = PUNCT.get(plan.get("punctuation_after", {}).get(str(len(plan["source_tokens"]) - 1), ""))
        if mark and not text.endswith(tuple(PUNCT.values())):
            text += mark
        return f"{prefix} {text}".strip()
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
        folded = [t.casefold() for t in kept]
        if folded[:2] == ["please", "list"]:
            head_tokens, item_tokens = kept[:2], kept[2:]
        elif folded[:4] == ["make", "a", "list", "of"]:
            head_tokens, item_tokens = kept[:3], kept[4:]
        else:
            head_tokens = item_tokens = []
        if head_tokens and item_tokens:
            items = [x for x in item_tokens if x.casefold() != "and"]
            head = preserve_case(join_tokens(head_tokens))
            result = head + ":\n" + "\n".join(f"- {preserve_case(normalize_token(x))}" for x in items)
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()
    rows = exact = 0
    digest = hashlib.sha256()
    for line in args.input.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows += 1
            digest.update(hashlib.sha256(str(row.get("id", "")).encode("utf-8")).digest())
            exact += int(render(row) == row.get("target_text"))
    report = {
        "schema_version": 1,
        "rows": rows,
        "exact": exact,
        "exact_rate": exact / max(1, rows),
        "evaluated_row_ids_sha256": digest.hexdigest(),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__": main()
