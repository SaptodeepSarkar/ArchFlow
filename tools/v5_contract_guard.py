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


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP}


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text.endswith(('.', '?', '!')) else text + "."


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
            return "numbered_list", items
    if " and " in low and any(prefix in low for prefix in ("i need ", "buy ", "get ", "things ")):
        body = re.sub(r"^(things i need are|i need|buy|get)\s+", "", source.strip(), flags=re.I)
        raw = re.split(r"\s+and\s+|,", body)
        items = [re.sub(r"^(and|a)\s+", "", x.strip(), flags=re.I) for x in raw if x.strip()]
        if len(items) >= 2:
            return "make_list", [_sentence(item) for item in items]
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
            base = re.sub(r"\b(with|add|a|an|the)?\s*(?:laughing|thumbs[- ]up|birthday|celebration|heart|fire)?\s*emoji\b", "", source, flags=re.I)
            result = _sentence(base.strip())[:-1] + f" {emoji}."
        return json.dumps({"operation": "emoji", "result": result,
                           "changed_spans": [emoji], "needs_confirmation": False}, ensure_ascii=False, separators=(",", ":"))

    listing = _list_items(source)
    if listing:
        operation, items = listing
        return json.dumps({"operation": operation, "result": {"title": None, "items": items},
                           "changed_spans": [], "needs_confirmation": False}, ensure_ascii=False, separators=(",", ":"))

    operation = record.get("operation")
    result = record.get("result")
    if operation not in ALLOWED or not isinstance(result, (str, dict)):
        operation = "format_only"
    result_text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    if len(_words(source)) >= 4 and len(_words(source) - _words(result_text)) > max(1, len(_words(source)) // 3):
        result_text = _sentence(source)
    if operation in {"make_list", "numbered_list"}:
        if not isinstance(result, dict) or not isinstance(result.get("items"), list):
            operation = "format_only"
            result_text = _sentence(source)
    return json.dumps({"operation": operation, "result": result if operation in {"make_list", "numbered_list"} else result_text,
                       "changed_spans": record.get("changed_spans", []) if isinstance(record.get("changed_spans", []), list) else [],
                       "needs_confirmation": bool(record.get("needs_confirmation", False))}, ensure_ascii=False, separators=(",", ":"))
