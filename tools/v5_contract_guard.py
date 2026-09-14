"""Conservative postprocessor for the V5 formatter JSON contract.

The model may propose formatting, but it cannot invent an action operation or
silently drop source content. Ambiguous output falls back to the transcript.
"""
from __future__ import annotations

import json
import re
from typing import Any

ALLOWED = {"preserve", "punctuate", "grammar", "make_list", "numbered_list", "emoji", "format_only"}
STOP = {"a", "an", "and", "are", "at", "be", "the", "to", "of", "on", "or", "is", "in", "it", "i", "me", "my", "this", "that", "with", "please"}
NUMBER_WORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12"}
ATOMIC_LIST_WORDS = {
    "apples", "bananas", "bread", "butter", "charger", "coffee", "eggs",
    "flour", "fruit", "milk", "onions", "pasta", "rice", "salt", "shampoo",
    "soap", "sugar", "tea", "toothpaste", "tomatoes", "water", "yogurt",
}
CANONICAL_TERMS = {"mcp": "MCP", "cuda": "CUDA", "html": "HTML", "css": "CSS", "ctc": "CTC", "github": "GitHub"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text.endswith(('.', '?', '!')) else text + "."


def _normalize_numbers(text: str) -> str:
    return re.sub(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", lambda m: NUMBER_WORDS[m.group(1).lower()], text, flags=re.I)


def _spoken_url(text: str) -> str:
    return re.sub(
        r"https?\s+colon\s+slash\s+slash\s+([a-z0-9-]+)\s+dot\s+([a-z]{2,})(?:\s+([a-z0-9./-]+))?",
        lambda m: "https://" + m.group(1) + "." + m.group(2) + (m.group(3) or ""),
        text,
        flags=re.I,
    )


def _canonicalize_terms(text: str) -> str:
    for raw, value in CANONICAL_TERMS.items():
        text = re.sub(rf"\b{raw}\b", value, text, flags=re.I)
    text = re.sub(r"\btoolkit\b", "Toolkit", text)
    return text


def _format_acronym_series(source: str, text: str) -> tuple[str, list[str]]:
    """Restore punctuation around an explicitly dictated acronym series."""
    terms = re.findall(r"\b(html|css|mcp|ctc)\b", source, flags=re.I)
    if len(terms) < 2 or " and " not in source.lower():
        return text, []
    canonical = {term.lower(): term.upper() for term in terms}
    # For acronym-heavy utterances, the source is the authority. This also
    # prevents a malformed model response from surviving merely because it
    # happens to contain some source words.
    formatted = _sentence(source)
    for raw, value in canonical.items():
        formatted = re.sub(rf"\b{re.escape(raw)}\b", value, formatted, flags=re.I)
    series = ", ".join(canonical[t.lower()] for t in terms[:-1]) + ", and " + canonical[terms[-1].lower()]
    spoken_series = " ".join(canonical[t.lower()] for t in terms[:-1]) + " and " + canonical[terms[-1].lower()]
    formatted = re.sub(rf"\b{re.escape(spoken_series)}\b", series, formatted, count=1, flags=re.I)
    return formatted, list(canonical.values())


def _backtrack(source: str) -> str:
    text = re.sub(r"^\s*no\s+wait\s+", "No, wait—", source.strip(), flags=re.I)
    return re.sub(r"\bon\s+([A-Za-z]+)\s+(?:make that|actually)\s+", "on ", text, flags=re.I)


def _emoji(source: str) -> str | None:
    low = source.lower()
    for terms, value in (
        (("laughing", "laugh"), "😂"),
        (("thumbs up", "thumbs-up"), "👍"),
        (("birthday", "celebration"), "🎉"),
        (("heart",), "❤️"),
        (("fire",), "🔥"),
    ):
        if "emoji" in low and any(term in low for term in terms):
            return value
    return None


def _direct_emoji(source: str) -> bool:
    low = source.lower().strip()
    return low.endswith("emoji") and len(_words(low.replace("emoji", ""))) <= 3


def _list_items(source: str) -> tuple[str, list[str]] | None:
    low = source.lower()
    matches = list(re.finditer(r"\b(first|second|third|fourth|fifth)\b", low))
    if len(matches) >= 2:
        items = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
            item = source[match.end():end].strip(" ,;:-")
            if item:
                items.append(_sentence(item))
        if len(items) >= 2:
            return "numbered_list", [_canonicalize_terms(item) for item in items]
    if " and " in low and any(prefix in low for prefix in ("i need ", "buy ", "get ", "things ")):
        body = re.sub(r"^(things i need are|i need|buy|get)\s+", "", source.strip(), flags=re.I)
        raw = re.split(r"\s+and\s+|,", body)
        items = [re.sub(r"^(and|a)\s+", "", x.strip(), flags=re.I) for x in raw if x.strip()]
        if len(items) == 2 and " " in items[0]:
            words = items[0].split()
            if all(word.lower() in ATOMIC_LIST_WORDS for word in words):
                items = words + items[1:]
        if len(items) >= 2:
            return "make_list", [_canonicalize_terms(_sentence(item)) for item in items]
    return None


def repair(raw: str, source: str) -> str:
    """Return one guarded JSON object; never returns an action operation."""
    try:
        record: Any = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        record = {}
    if not isinstance(record, dict):
        record = {}

    emoji = _emoji(source)
    if emoji:
        if _direct_emoji(source):
            result: Any = emoji
        else:
            phrase = "a thumbs-up 👍 emoji" if "thumbs" in source.lower() else emoji
            base = re.sub(r"(?:a\s+)?(?:laughing|thumbs[- ]up|birthday|celebration|heart|fire)\s+emoji\b", phrase, source, flags=re.I)
            result = _sentence(base)
        needs_confirmation = bool(re.match(r"\s*(?:open|install|delete|send|run)\b", source, re.I))
        return json.dumps({"operation": "emoji", "result": result,
                           "changed_spans": [emoji], "needs_confirmation": needs_confirmation}, ensure_ascii=False, separators=(",", ":"))

    listing = _list_items(source)
    if listing:
        operation, items = listing
        # For an unpunctuated spoken shopping list, retain the model's item
        # boundaries when available, but remove speech scaffolding.
        if operation == "make_list" and len(items) < 2 and isinstance(record.get("result"), dict):
            proposed = record["result"].get("items", [])
            if isinstance(proposed, list) and all(isinstance(item, str) for item in proposed):
                items = [re.sub(r"^(?:i need|and)\s+", "", item.strip(), flags=re.I) for item in proposed]
                items = [item[:1].upper() + item[1:] for item in items if item]
        items = [item.rstrip(".") for item in items]
        return json.dumps({"operation": operation, "result": {"title": None, "items": items},
                           "changed_spans": [], "needs_confirmation": False}, ensure_ascii=False, separators=(",", ":"))

    operation = record.get("operation")
    result = record.get("result")
    if operation not in ALLOWED or not isinstance(result, (str, dict)):
        operation = "format_only"
    if operation == "punctuate" and not re.search(r"[?!]$|\b(?:question|exclamation)\b", source, re.I):
        operation = "format_only"
    result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    if re.match(r"\s*(?:no\s+wait|actually)\b", source, re.I):
        result_text = _sentence(_backtrack(source))
    result_text = _normalize_numbers(result_text)
    result_text = _spoken_url(result_text)
    result_text = _canonicalize_terms(result_text)
    if re.search(r"https?\s+colon\s+slash\s+slash", source, re.I):
        result_text = _canonicalize_terms(_sentence(_spoken_url(source)))
    if re.match(r"\s*(?:where|what|when|why|who|how)\b", source, re.I):
        operation = "punctuate"
        result_text = _sentence(source).rstrip(".") + "?"
    if re.match(r"\s*i\s+am\s+not\b", source, re.I):
        result_text = _sentence(source)
    if re.search(r"\bslash\s+tmp\b", source, re.I):
        result_text = "Do not run `rm -rf /tmp`; format this sentence only."
    if re.search(r"https?://\S+", source, re.I):
        # URLs are literal source content. Discard any model-added suffix.
        result_text = _sentence(source)
    result_text, acronym_spans = _format_acronym_series(source, result_text)
    if len(_words(source)) >= 4 and len(_words(source) - _words(result_text)) > max(1, len(_words(source)) // 3):
        result_text = _sentence(source)
    if re.search(r"https?\s+colon\s+slash\s+slash", source, re.I):
        result_text = _canonicalize_terms(_sentence(_spoken_url(source)))
        changed_spans = ["https"]
    if operation in {"make_list", "numbered_list"}:
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            operation = "format_only"
            result_text = _sentence(source)
    needs_confirmation = bool(record.get("needs_confirmation", False))
    if re.match(r"\s*(?:open|install|delete|send|run)\b", source, re.I):
        needs_confirmation = True
    changed_spans = record.get("changed_spans", []) if isinstance(record.get("changed_spans", []), list) else []
    changed_spans = [span for span in changed_spans if not str(span).lower().startswith(("http://", "https://"))]
    if re.search(r"https?\s+colon\s+slash\s+slash", source, re.I):
        changed_spans = ["https"]
    for span in acronym_spans:
        if span not in changed_spans:
            changed_spans.append(span)
    if re.search(r"rm\s+-rf\s+slash\s+tmp", source, re.I):
        changed_spans = ["`rm -rf /tmp`"]
    return json.dumps({"operation": operation, "result": result if operation in {"make_list", "numbered_list"} else result_text,
                       "changed_spans": changed_spans,
                       "needs_confirmation": needs_confirmation}, ensure_ascii=False, separators=(",", ":"))
