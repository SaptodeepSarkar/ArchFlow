#!/usr/bin/env python3
"""Create grouped, source-grounded variants for V6 emoji/list cue rows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

TOKEN = __import__("re").compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")


def make(row: dict, source: str, labels: list[str], suffix: str) -> dict:
    out = dict(row); out["id"] = f"v6-semaug-{row['id']}-{suffix}"
    out["source"] = source; out["source_tokens"] = TOKEN.findall(source); out["token_labels"] = labels
    out["metadata"] = dict(row["metadata"]); out["metadata"]["source"] = "semantic-cue-augmentation"
    out["metadata"]["base_id"] = row["id"]; out["metadata"]["augmentation"] = suffix
    return out


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--input", type=Path, required=True); ap.add_argument("--out", type=Path, required=True); ap.add_argument("--exclude", type=Path, required=True); args = ap.parse_args()
    excluded = {json.loads(x)["source"].casefold() for x in args.exclude.read_text().splitlines() if x.strip()}
    rows = []; seen = set(excluded)
    for line in args.input.read_text().splitlines():
        if not line.strip(): continue
        row = json.loads(line); source = row["source"]; kind = row["emoji_intent"] != "NONE"
        candidates = []
        if kind:
            phrase = source.replace("laughing emoji", "laughing emoji").replace("thumbs up emoji", "thumbs up emoji").replace("heart emoji", "heart emoji")
            candidates = [f"say {phrase}", f"put a {phrase}", f"use one {phrase}", f"include {phrase}", f"can you use {phrase}"]
        elif row["structure"] == "ORDERED_LIST":
            candidates = ["uh " + source, "um " + source, source.replace("first ", "first please ", 1)]
        for n, candidate in enumerate(candidates):
            if candidate.casefold() in seen: continue
            tokens = TOKEN.findall(candidate)
            labels = ["DELETE_FILLER"] + ["KEEP"] * (len(tokens) - 1) if tokens and tokens[0].casefold() in {"uh", "um"} else ["KEEP"] * len(tokens)
            if row["structure"] == "ORDERED_LIST":
                labels = ["DELETE_FALSE_START" if t.casefold() in {"first", "second", "third", "fourth", "fifth", "then", "please"} else label for t, label in zip(tokens, labels)]
            out = make(row, candidate, labels, str(n))
            rows.append(out); seen.add(candidate.casefold())
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(json.dumps({"rows": len(rows), "excluded": len(excluded), "out": str(args.out)}))


if __name__ == "__main__": main()
