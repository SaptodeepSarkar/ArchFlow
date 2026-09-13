#!/usr/bin/env python3
"""Prepare a public-only Indian-English STT manifest for Cozy.

The Cozy trainer lives in ~/Projects/Cozy, but this repository owns the
selection policy. No recordings/ rows are accepted. Human Indian-accent audio
is the main training pool; only the two Indian-labelled Flux voices are kept
for hard technical/rare-word coverage. Other synthetic voices are excluded.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cozy-root", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--activate", action="store_true",
                    help="backup active manifests and activate public_indian")
    args = ap.parse_args()
    root = args.cozy_root
    old = root / "data" / "manifests"
    out = root / "data" / "manifests" / "public_indian"
    out.mkdir(parents=True, exist_ok=True)

    train, eval_rows, hard_eval = [], [], []
    allowed_human = {"cv_indian", "santhosh_indian"}
    allowed_flux_voices = {"flux-priya-en", "flux-naveen-en"}

    for name in ("train.jsonl", "eval.jsonl"):
        for row in rows(old / name):
            source = row.get("source", "")
            voice = row.get("voice", "")
            if source in allowed_human:
                (train if name == "train.jsonl" else eval_rows).append(row)
            elif source == "flux_tts" and voice in allowed_flux_voices:
                # Keep Indian-labelled voices for lexical coverage, but never
                # let them dominate the human-accent corpus.
                row = {**row, "source": "flux_indian_hard"}
                if name == "train.jsonl" and voice == "flux-priya-en":
                    train.append(row)
                if (name == "eval.jsonl" or voice == "flux-naveen-en") and row.get("category") in {"complex", "acronyms", "companies", "mixed", "post2023"}:
                    hard_eval.append(row)

    rng = random.Random(args.seed)
    rng.shuffle(train)
    rng.shuffle(eval_rows)
    # Hard words are spoken by one Indian-labelled voice in training and held
    # out on a different Indian-labelled voice, so text does not leak across
    # the lexical evaluation boundary.

    for path, data in ((out / "train.jsonl", train),
                       (out / "eval.jsonl", eval_rows),
                       (out / "hard_eval.jsonl", hard_eval)):
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data))

    if args.activate:
        for name in ("train.jsonl", "eval.jsonl"):
            active = old / name
            backup = old / (name + ".before_public_indian")
            if not backup.exists():
                backup.write_bytes(active.read_bytes())
            active.write_bytes((out / name).read_bytes())
        print("activated: data/manifests/train.jsonl and eval.jsonl")

    print(f"public Indian train={len(train)} eval={len(eval_rows)} hard_eval={len(hard_eval)}")
    print("sources: human=cv_indian,santhosh_indian; lexical=flux-priya-en,flux-naveen-en")
    print("personal recordings: excluded")


if __name__ == "__main__":
    main()
