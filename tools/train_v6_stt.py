#!/usr/bin/env python3
"""Train a V6 Whisper STT candidate from a pre-split V6 corpus manifest.

The tested Whisper LoRA/streaming implementation is shared with V5. V6's
distinct path is a provenance-reviewed manifest with meeting-isolated splits
and explicit sample weighting. The clean AMI run uses uniform weights and does
not inherit V5 hypotheses or Flux-derived examples. This script requires a
pre-split manifest so it cannot silently create a random, speaker-leaking
holdout.
"""
from __future__ import annotations

import argparse
from train_v5_whisper_lora import main as train_whisper


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--pre-split", action="store_true")
    args, _ = parser.parse_known_args()
    if not args.pre_split:
        raise SystemExit("V6 STT requires --pre-split; use the V6 meeting-isolated manifest builder")
    train_whisper()


if __name__ == "__main__":
    main()
