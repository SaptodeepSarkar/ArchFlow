#!/usr/bin/env python3
"""Create controlled STT-style variants from trusted V6 rows.

Every variant keeps the reviewed target and source content. Only explicit
disfluency/error operations are added, with corresponding closed labels.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

TOKEN = re.compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")
PUNCT = {",", ".", "?", "!", ":", ";"}


def toks(s: str) -> list[str]: return TOKEN.findall(s)


def text(ts: list[str]) -> str:
    out = ""
    for t in ts:
        if not out or t in PUNCT or t == "'": out += t
        elif out.endswith("'"): out += t
        elif t.startswith(("/", ".")): out += " " + t
        else: out += " " + t
    return out


def shifted(row: dict, source_tokens: list[str], labels: list[str], index_map: dict[int, int], suffix: str) -> dict:
    punctuation = {}
    for old, value in row["punctuation_after"].items():
        if int(old) in index_map: punctuation[str(index_map[int(old)])] = value
    spans = {str(index_map[int(k)]): v for k, v in row["span_types"].items() if int(k) in index_map}
    out = dict(row); out["id"] = f"v6-aug-{suffix}"; out["source_tokens"] = source_tokens
    out["source"] = text(source_tokens); out["token_labels"] = labels
    out["punctuation_after"] = punctuation; out["span_types"] = spans
    out["metadata"] = dict(row["metadata"]); out["metadata"]["source"] = "augmented-stt"
    out["metadata"]["augmentation"] = suffix
    out["metadata"]["base_id"] = row["id"]
    return out


def variants(row: dict, ordinal: int) -> list[dict]:
    base = row["source_tokens"]; labels = row["token_labels"]; out = []
    fillers = [["uh"], ["um"], ["uh", "um"], ["you", "know"]]
    for n, prefix in enumerate(fillers):
        ts = prefix + base; ls = ["DELETE_FILLER"] * len(prefix) + labels
        out.append(shifted(row, ts, ls, {i: i + len(prefix) for i in range(len(base))}, f"{ordinal}-prefix{n}"))
    for n, filler in enumerate(("uh", "um")):
        out.append(shifted(row, base + [filler], labels + ["DELETE_FILLER"], {i: i for i in range(len(base))}, f"{ordinal}-suffix{n}"))
    content_indices = [i for i, token in enumerate(base) if re.search(r"[A-Za-z0-9]", token)]
    if content_indices:
        for n, pos in enumerate((content_indices[0], content_indices[-1])):
            ts = base[:pos] + [base[pos]] + base[pos:]
            ls = labels[:pos] + ["DELETE_FALSE_START"] + labels[pos:]
            mapping = {i: i if i < pos else i + 1 for i in range(len(base))}
            out.append(shifted(row, ts, ls, mapping, f"{ordinal}-duplicate{n}"))
    if not row["protected_spans"]:
        ts = [t.lower() for t in base]
        lower_labels = ["CAPITALIZE" if token[:1].isupper() and token.lower() != token else label for token, label in zip(base, labels)]
        out.append(shifted(row, ts, lower_labels, {i: i for i in range(len(base))}, f"{ordinal}-lower"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--input", type=Path, required=True); ap.add_argument("--out", type=Path, required=True); ap.add_argument("--count", type=int, default=10000); args = ap.parse_args()
    bases = [json.loads(x) for x in args.input.read_text().splitlines() if x.strip()]
    rows, seen = [], set()
    for i, base in enumerate(bases, 1):
        for candidate in variants(base, i):
            key = candidate["source"].casefold()
            if key in seen: continue
            seen.add(key); rows.append(candidate)
            if len(rows) >= args.count: break
        if len(rows) >= args.count: break
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(json.dumps({"rows": len(rows), "base_rows": len(bases), "out": str(args.out)}))


if __name__ == "__main__": main()
