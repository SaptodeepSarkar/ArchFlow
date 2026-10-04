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
from pathlib import Path
import sys
from v6_stt_run_manifest import run_identity, verify_or_create


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-split", action="store_true")
    parser.add_argument("--streaming", action="store_true")
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--sqlite-manifest", type=Path, action="append", default=[])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--init-adapter", type=Path)
    parser.add_argument("--resume-from-checkpoint", type=Path)
    args, _ = parser.parse_known_args()
    if not args.pre_split:
        raise SystemExit("V6 STT requires --pre-split; use the V6 meeting-isolated manifest builder")
    if not args.streaming:
        raise SystemExit("V6 STT requires --streaming to bound feature memory")
    root = Path(__file__).resolve().parents[1]
    if args.out.resolve().is_relative_to(root):
        raise SystemExit("V6 STT output must stay outside Git")
    import torch
    if not torch.cuda.is_available():
        raise SystemExit("CUDA unavailable; no run directory created")
    settings = sys.argv[1:].copy()
    if "--resume-from-checkpoint" in settings:
        index = settings.index("--resume-from-checkpoint")
        del settings[index:index + 2]
    if any(value.startswith("--resume-from-checkpoint=") for value in settings):
        settings = [value for value in settings if not value.startswith("--resume-from-checkpoint=")]
    identity = run_identity(args.manifest, args.sqlite_manifest, args.model,
                            [Path(__file__), root / "tools/train_v5_whisper_lora.py",
                             root / "tools/v6_stt_run_manifest.py"], settings,
                            adapters=[args.init_adapter] if args.init_adapter else [])
    verify_or_create(args.out, identity, args.resume_from_checkpoint)
    from train_v5_whisper_lora import main as train_whisper
    train_whisper()


if __name__ == "__main__":
    main()
