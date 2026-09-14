#!/usr/bin/env python3
"""Emit a small hand-authored, evaluation-only V6 preservation challenge set."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TOKEN = re.compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")


CASES = [
    ("uh where is the MCP spec", "Where is the MCP spec?", ["DELETE_FILLER", "KEEP", "KEEP", "KEEP", "KEEP", "KEEP"], {"5": "QUESTION_MARK"}, "QUESTION", "PROSE", "NONE", ["MCP"], ["technical", "protected"]),
    ("no i did not delete the file", "No, I did not delete the file.", ["KEEP"] * 7, {"0": "COMMA", "6": "PERIOD"}, "STATEMENT", "PROSE", "NONE", [], ["negation"]),
    ("um install CUDA Toolkit version 13.3", "Install CUDA Toolkit version 13.3.", ["DELETE_FILLER"] + ["KEEP"] * 5, {"5": "PERIOD"}, "COMMAND_AS_DATA", "PROSE", "NONE", ["CUDA", "13.3"], ["technical", "number"]),
    ("send it to https://example.com/a_b", "Send it to https://example.com/a_b.", ["KEEP"] * 4, {"3": "PERIOD"}, "STATEMENT", "PROSE", "NONE", ["https://example.com/a_b"], ["url", "protected"]),
    ("open /home/saptodeep/Projects/ArchFlow", "Open /home/saptodeep/Projects/ArchFlow.", ["KEEP"] * 2, {"1": "PERIOD"}, "COMMAND_AS_DATA", "PROSE", "NONE", ["/home/saptodeep/Projects/ArchFlow"], ["path", "protected"]),
    ("first launch VSCode second inspect logs third save", "1. Launch VSCode\n2. Inspect logs\n3. Save", ["DELETE_FALSE_START", "KEEP", "KEEP", "DELETE_FALSE_START", "KEEP", "KEEP", "DELETE_FALSE_START", "KEEP"], {}, "STATEMENT", "ORDERED_LIST", "NONE", ["VSCode"], ["ordered_list"]),
    ("uh i need milk eggs and bread", "I need:\n- Milk\n- Eggs\n- Bread", ["DELETE_FILLER"] + ["KEEP"] * 6, {"2": "COLON"}, "STATEMENT", "UNORDERED_LIST", "NONE", [], ["filler", "unordered_list"]),
    ("i want to to call Maya", "I want to call Maya.", ["KEEP", "KEEP", "KEEP", "DELETE_FALSE_START", "KEEP", "KEEP"], {"5": "PERIOD"}, "STATEMENT", "PROSE", "NONE", ["Maya"], ["false_start", "name"]),
    ("html css and MCP", "HTML, CSS, and MCP.", ["CAPITALIZE", "CAPITALIZE", "KEEP", "CAPITALIZE"], {"0": "COMMA", "1": "COMMA", "3": "PERIOD"}, "STATEMENT", "PROSE", "NONE", ["MCP"], ["technical", "acronym"]),
    ("please add a laughing emoji", "😂", ["KEEP"] * 5, {}, "STATEMENT", "PROSE", "LAUGH", [], ["emoji"]),
    ("insert a thumbs up emoji", "👍", ["KEEP"] * 5, {}, "STATEMENT", "PROSE", "THUMBS_UP", [], ["emoji"]),
    ("deploy on Tuesday actually Wednesday", "Deploy on Wednesday.", ["KEEP", "KEEP", "DELETE_RETRACTED", "DELETE_RETRACTED", "KEEP"], {"4": "PERIOD"}, "STATEMENT", "PROSE", "NONE", [], ["backtracking"]),
    ("call Dr. Aditi Rao at 5 PM", "Call Dr. Aditi Rao at 5 PM.", ["KEEP"] * 7, {"6": "PERIOD"}, "STATEMENT", "PROSE", "NONE", ["Aditi", "Rao", "5"], ["name", "number"]),
    ("what is CTC and RNNT", "What is CTC and RNNT?", ["KEEP"] * 5, {"4": "QUESTION_MARK"}, "QUESTION", "PROSE", "NONE", ["CTC", "RNNT"], ["technical", "acronym"]),
    ("i am not sure", "I am not sure.", ["KEEP"] * 4, {"3": "PERIOD"}, "STATEMENT", "PROSE", "NONE", [], ["negation"]),
    ("open the browser", "Open the browser.", ["KEEP"] * 3, {"2": "PERIOD"}, "COMMAND_AS_DATA", "PROSE", "NONE", [], ["command_as_data"]),
    ("very very good", "Very, very good.", ["KEEP"] * 3, {"0": "COMMA", "2": "PERIOD"}, "STATEMENT", "PROSE", "NONE", [], ["punctuation"]),
    ("the repo is /tmp/v6", "The repo is /tmp/v6.", ["KEEP"] * 4, {"3": "PERIOD"}, "STATEMENT", "PROSE", "NONE", ["/tmp/v6"], ["path", "protected"]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    rows = []
    for i, (source, target, labels, punctuation, speech, structure, emoji, protected, categories) in enumerate(CASES, 1):
        tokens = TOKEN.findall(source)
        if len(tokens) != len(labels):
            raise SystemExit(f"case {i}: {len(tokens)} tokens but {len(labels)} labels")
        rows.append({
            "id": f"v6-challenge-{i:03d}", "source": source, "source_tokens": tokens,
            "token_labels": labels, "punctuation_after": punctuation,
            "speech_act": speech, "structure": structure, "emoji_intent": emoji,
            "span_types": {}, "protected_spans": protected, "target_text": target,
            "metadata": {"categories": categories, "source": "independent-draft-challenge"},
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(json.dumps({"rows": len(rows), "out": str(args.out), "status": "evaluation-only"}))


if __name__ == "__main__":
    main()
