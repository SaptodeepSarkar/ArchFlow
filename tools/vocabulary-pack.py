#!/usr/bin/env python3
"""Print selected STT vocabulary packs as a config-ready TOML array."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "models" / "vocabulary"


def read_pack(name: str) -> list[str]:
    path = ROOT / f"{name}.txt"
    if not path.is_file():
        raise SystemExit(f"unknown vocabulary pack: {name}")
    terms: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        term = raw.strip()
        if term and not term.startswith("#") and term not in terms:
            terms.append(term)
    return terms


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packs", nargs="*", help="pack names, or none to list packs")
    parser.add_argument("--max", type=int, default=200, dest="limit")
    args = parser.parse_args()
    available = sorted(path.stem for path in ROOT.glob("*.txt"))
    if not args.packs:
        print("available packs: " + ", ".join(available))
        return
    if args.limit < 1:
        raise SystemExit("--max must be positive")
    terms: list[str] = []
    for pack in args.packs:
        for term in read_pack(pack):
            if term not in terms:
                terms.append(term)
    print("vocabulary = [")
    for term in terms[: args.limit]:
        escaped = term.replace("\\", "\\\\").replace('"', '\\"')
        print(f'  "{escaped}",')
    print("]")


if __name__ == "__main__":
    main()
