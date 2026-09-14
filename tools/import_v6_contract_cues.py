#!/usr/bin/env python3
"""Import only source-grounded emoji and ordered-list contract cues for V6."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TOKEN = re.compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")
EMOJI = {"😂": "LAUGH", "👍": "THUMBS_UP", "🎉": "CELEBRATION", "❤️": "HEART", "🙂": "OTHER_SUPPORTED"}
MARKERS = {"first", "second", "third", "fourth", "fifth", "then"}


def make_row(idx: int, raw: dict) -> dict | None:
    contract = json.loads(raw["output"])
    source = raw.get("input", "").strip(); tokens = TOKEN.findall(source)
    operation = contract.get("operation")
    if operation == "emoji":
        target = contract.get("result", "")
        if target not in EMOJI or not tokens or not all(t.casefold() in {"laughing", "laugh", "thumbs", "up", "heart", "celebration", "emoji"} for t in tokens):
            return None
        return {"id": f"v6-contract-cue-{idx:04d}", "source": source, "source_tokens": tokens,
                "token_labels": ["KEEP"] * len(tokens), "punctuation_after": {},
                "speech_act": "STATEMENT", "structure": "PROSE", "emoji_intent": EMOJI[target],
                "span_types": {}, "protected_spans": [], "target_text": target,
                "metadata": {"categories": ["emoji", "contract-cue"], "source": "reviewed-contract"}}
    if operation == "numbered_list":
        result = contract.get("result", {})
        items = result.get("items", []) if isinstance(result, dict) else []
        if not items or any(not isinstance(item, str) for item in items): return None
        labels = ["DELETE_FALSE_START" if t.casefold() in MARKERS else "KEEP" for t in tokens]
        source_content = [t.casefold() for t, l in zip(tokens, labels) if l == "KEEP" and re.search(r"[A-Za-z0-9]", t)]
        target_content = [t.casefold() for item in items for t in TOKEN.findall(item) if re.search(r"[A-Za-z0-9]", t)]
        if source_content != target_content: return None
        target = "\n".join(f"{n}. {item}" for n, item in enumerate(items, 1))
        return {"id": f"v6-contract-cue-{idx:04d}", "source": source, "source_tokens": tokens,
                "token_labels": labels, "punctuation_after": {},
                "speech_act": "STATEMENT", "structure": "ORDERED_LIST", "emoji_intent": "NONE",
                "span_types": {}, "protected_spans": [], "target_text": target,
                "metadata": {"categories": ["ordered_list", "contract-cue"], "source": "reviewed-contract"}}
    return None


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--input", type=Path, required=True); ap.add_argument("--out", type=Path, required=True); args = ap.parse_args()
    rows = []; rejected = 0
    for line in args.input.read_text().splitlines():
        if not line.strip(): continue
        row = make_row(len(rows) + 1, json.loads(line))
        if row is None: rejected += 1
        else: rows.append(row)
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(json.dumps({"accepted": len(rows), "rejected": rejected, "out": str(args.out)}))


if __name__ == "__main__": main()
