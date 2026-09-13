#!/usr/bin/env python3
"""Prepare a text coverage report for the v3 public Indian STT benchmark."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED = [
    "HTML", "CSS", "narcotics", "acrobat", "Celsius", "MCP", "CTC",
    "glioblastoma", "pharmacokinetics", "otorhinolaryngology", "CUDA",
    "PyTorch", "CTranslate2", "NVIDIA", "IRCTC", "Bengaluru", "₹",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    corpus = "\n".join(str(row.get("text", "")) for row in rows)
    coverage = []
    for term in REQUIRED:
        pattern = re.escape(term)
        coverage.append({"term": term, "present_in_text": bool(re.search(pattern, corpus, re.IGNORECASE)), "audio_count": sum(bool(re.search(pattern, str(row.get("text", "")), re.IGNORECASE)) for row in rows)})
    result = {"manifest": str(args.manifest), "clips": len(rows), "terms": coverage, "missing_audio_terms": [item["term"] for item in coverage if item["audio_count"] == 0]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"clips={len(rows)} covered={sum(item['audio_count'] > 0 for item in coverage)}/{len(coverage)} missing_audio={len(result['missing_audio_terms'])}")


if __name__ == "__main__":
    main()
