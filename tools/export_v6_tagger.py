#!/usr/bin/env python3
"""Export a trained V6 hashed tagger to a tiny portable float32 package.

The package contains no tokenizer, transcript, or user data. It is deliberately
an inference-only interchange format so native Linux and Android runtimes can
share the same trained weights without importing PyTorch.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import torch


MAGIC = b"V6TG\x01\x00\x00\x00"
ORDER = (
    "embedding.weight", "body.0.weight", "body.0.bias",
    "token.weight", "token.bias", "punct.weight", "punct.bias",
    "structure.weight", "structure.bias", "speech.weight", "speech.bias",
    "emoji.weight", "emoji.bias",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    state = torch.load(args.model, map_location="cpu", weights_only=True)
    missing = [name for name in ORDER if name not in state]
    if missing:
        raise SystemExit(f"not a V6 hashed tagger; missing tensors: {missing}")
    config = json.loads(args.config.read_text())
    if config.get("model", "hashed") != "hashed":
        raise SystemExit("only the bounded hashed V6 tagger has a native export")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as stream:
        stream.write(MAGIC)
        stream.write(struct.pack("<I", len(ORDER)))
        for name in ORDER:
            tensor = state[name].detach().contiguous().float()
            dims = tuple(int(dim) for dim in tensor.shape)
            if len(dims) > 4:
                raise SystemExit(f"unsupported tensor rank: {name}")
            stream.write(struct.pack("<I", len(name)))
            stream.write(name.encode())
            stream.write(struct.pack("<I", len(dims)))
            stream.write(struct.pack("<" + "I" * len(dims), *dims))
            stream.write(tensor.numpy().tobytes(order="C"))
    manifest = {
        "schema": "vaani.v6.tagger.float32/1",
        "model": "hashed",
        "source_config": str(args.config),
        "parameters": sum(int(state[name].numel()) for name in ORDER),
        "tensor_order": list(ORDER),
        "magic": MAGIC.decode("latin1"),
        "native_ready": False,
        "note": "Weights export is validated; native Linux/Android loaders must pass the V6 challenge gates before promotion.",
    }
    args.out.with_suffix(".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"out": str(args.out), "bytes": args.out.stat().st_size, "parameters": manifest["parameters"]}))


if __name__ == "__main__":
    main()
