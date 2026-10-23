#!/usr/bin/env python3
"""Export the averaged STT model to CTranslate2 int8 (the shipped artefact)."""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

KEEP = ("*.json", "*.txt", "*.model", "*.tiktoken")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, help="averaged HF dir, e.g. $OUT/stt/averaged")
    parser.add_argument("--out", required=True, help="e.g. $OUT/export/stt-ct2-int8")
    parser.add_argument("--quantization", default="int8")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(os.path.join(args.model, "config.json")):
        raise SystemExit(f"{args.model}: not an HF model dir (config.json missing)")

    average = common.read_json(os.path.join(args.model, "average.json"))
    plan = {"source": os.path.abspath(args.model), "out": os.path.abspath(args.out),
            "quantization": args.quantization,
            "source_steps": (average or {}).get("source_steps")}

    if args.dry_run:
        os.makedirs(args.out, exist_ok=True)
        common.write_json(os.path.join(args.out, "export.dry-run.json"), plan)
        print(f"[dry-run] would convert {plan['source']} -> {plan['out']} "
              f"({plan['quantization']})", flush=True)
        return 0

    import ctranslate2

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    ctranslate2.converters.TransformersConverter(args.model).convert(
        args.out, quantization=args.quantization, force=True)
    for pattern in KEEP:
        for path in glob.glob(os.path.join(args.model, pattern)):
            shutil.copy2(path, os.path.join(args.out, os.path.basename(path)))
    plan["files"] = sorted(os.listdir(args.out))
    common.write_json(os.path.join(args.out, "export.json"), plan)
    print(f"exported {args.out} ({args.quantization})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
