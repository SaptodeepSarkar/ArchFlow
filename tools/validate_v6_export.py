#!/usr/bin/env python3
"""Validate a V6TG package against its source PyTorch state dict.

This is an offline packaging check: it compares every exported float32 tensor
byte-for-byte and emits aggregate metadata only. It never prints transcript or
other user content.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import torch

from export_v6_tagger import MAGIC, ORDER


def read_package(path: Path) -> dict[str, tuple[tuple[int, ...], bytes]]:
    data = path.read_bytes()
    pos = 0

    def take(size: int) -> bytes:
        nonlocal pos
        if pos + size > len(data):
            raise ValueError("truncated V6TG package")
        result = data[pos:pos + size]
        pos += size
        return result

    if take(len(MAGIC)) != MAGIC:
        raise ValueError("bad V6TG magic")
    count = struct.unpack("<I", take(4))[0]
    tensors: dict[str, tuple[tuple[int, ...], bytes]] = {}
    for _ in range(count):
        name_len = struct.unpack("<I", take(4))[0]
        name = take(name_len).decode("utf-8")
        rank = struct.unpack("<I", take(4))[0]
        dims = tuple(struct.unpack("<" + "I" * rank, take(4 * rank)))
        size = 4
        for dim in dims:
            size *= dim
        tensors[name] = (dims, take(size))
    if pos != len(data):
        raise ValueError("trailing bytes in V6TG package")
    return tensors


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--package", type=Path, required=True)
    args = ap.parse_args()
    state = torch.load(args.model, map_location="cpu", weights_only=True)
    package = read_package(args.package)
    if tuple(package) != ORDER:
        raise SystemExit("tensor order or set does not match the V6 export contract")
    checked = 0
    for name in ORDER:
        tensor = state[name].detach().contiguous().float()
        dims, raw = package[name]
        expected = tensor.numpy().tobytes(order="C")
        if dims != tuple(int(dim) for dim in tensor.shape) or raw != expected:
            raise SystemExit(f"tensor mismatch: {name}")
        checked += tensor.numel()
    print(json.dumps({"package": str(args.package), "tensors": len(ORDER), "parameters": checked, "byte_exact": True}))


if __name__ == "__main__":
    main()
