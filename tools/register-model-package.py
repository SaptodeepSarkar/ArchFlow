#!/usr/bin/env python3
"""Register an existing local model directory as a checksum-verified package.

Weights are never copied into the repository. This tool only creates the
model.json sidecar next to a user-owned local artifact after hashing its files.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="existing local model directory")
    parser.add_argument("--id", required=True, help="stable package identifier")
    parser.add_argument("--kind", default="stt", choices=("stt", "formatter", "vad", "denoiser"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--quantization")
    parser.add_argument("--language", action="append", required=True)
    parser.add_argument("--file", action="append", required=True, help="relative artifact file; repeat")
    parser.add_argument("--minimum-ram-mb", type=int, required=True)
    parser.add_argument("--license", required=True)
    parser.add_argument("--capability", action="append", default=[])
    args = parser.parse_args()

    root = Path(args.path).expanduser().resolve()
    if not root.is_dir():
        parser.error("--path must be an existing directory")
    manifest_path = root / "model.json"
    if manifest_path.exists():
        parser.error("model.json already exists; inspect it instead of overwriting it")

    files = []
    for relative in args.file:
        candidate = (root / relative).resolve()
        if root not in candidate.parents or not candidate.is_file():
            parser.error(f"--file must name a regular file inside --path: {relative}")
        files.append({"path": relative, "bytes": candidate.stat().st_size, "sha256": digest(candidate)})

    manifest = {
        "schema_version": 1,
        "id": args.id,
        "kind": args.kind,
        "version": args.version,
        "runtime": args.runtime,
        "quantization": args.quantization,
        "languages": args.language,
        "files": files,
        "minimum_ram_mb": args.minimum_ram_mb,
        "license": args.license,
        "capabilities": args.capability,
    }
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=root, prefix=".model.json-", delete=False) as target:
        json.dump(manifest, target, indent=2, sort_keys=True)
        target.write("\n")
        temporary = target.name
    os.replace(temporary, manifest_path)
    print(f"registered checksum-verified package: {args.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
