#!/usr/bin/env python3
"""Build a hash-manifested, text-only V6 formatter Colab bundle.

The bundle is written outside the repository. It intentionally excludes audio,
weights, caches, and arbitrary files from the supplied data directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path


CODE_FILES = (
    "tools/train_v6_seq2seq.py",
    "tools/eval_v6_seq2seq.py",
    "tools/compare_v6_seq2seq.py",
    "tools/render_v6_edit_plan.py",
    "tools/validate_v6_foundation.py",
    "tools/v6_real_alignment.py",
    "training/cleanup-llm/scripts/formatter_protocol.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_file(archive: zipfile.ZipFile, path: Path, member: str) -> None:
    info = zipfile.ZipInfo(member, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED,
                     compresslevel=6)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--synthetic-dir", type=Path, required=True)
    parser.add_argument("--real-dir", type=Path, required=True)
    parser.add_argument("--hard-replay", type=Path, required=True)
    parser.add_argument("--foundation-replay", type=Path, required=True)
    parser.add_argument("--challenge", type=Path, required=True)
    parser.add_argument("--hard-eval", type=Path, required=True)
    parser.add_argument("--model-bundle", type=Path, required=True,
                        help="existing minimal base-model ZIP; it is verified but not copied")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    out = args.out_dir.expanduser().resolve()
    if out == repo or repo in out.parents:
        raise SystemExit("Colab bundles must be written outside the Git worktree")
    if out.exists():
        raise SystemExit(f"refusing to overwrite existing bundle directory: {out}")

    split_files = [args.synthetic_dir / f"{name}.jsonl" for name in ("train", "dev", "test")]
    split_files += [args.real_dir / f"{name}.jsonl" for name in ("train", "dev", "test")]
    named_data = [
        (args.hard_replay, "data/hard-replay.jsonl"),
        (args.foundation_replay, "data/foundation-seed-v1.jsonl"),
        (args.challenge, "data/challenge-contract-v3.jsonl"),
        (args.hard_eval, "data/hard-eval.jsonl"),
    ]
    named_data += [(path, f"data/synthetic/{path.name}") for path in split_files[:3]]
    named_data += [(path, f"data/real/{path.name}") for path in split_files[3:]]
    missing = [str(path) for path, _ in named_data if not path.is_file()]
    missing += [str(repo / name) for name in CODE_FILES if not (repo / name).is_file()]
    if missing:
        raise SystemExit("missing bundle inputs: " + ", ".join(missing))
    if not args.model_bundle.is_file():
        raise SystemExit(f"missing minimal model bundle: {args.model_bundle}")

    # Automated admission/provenance check for the only organization-authored
    # replay file; held-out challenge sources are excluded from it.
    subprocess.run([
        sys.executable, str(repo / "tools/validate_v6_foundation.py"),
        str(args.foundation_replay), "--require-approved",
    ], cwd=repo, check=True)

    out.mkdir(parents=True)
    code_zip = out / "archflow-v6-training-code.zip"
    data_zip = out / "v6-formatter-training-data.zip"
    with zipfile.ZipFile(code_zip, "w") as archive:
        for name in CODE_FILES:
            add_file(archive, repo / name, name)
        notice = ("Vaani V6 formatter training code. Python 3.11+; install the "
                  "pinned notebook requirements before use.\n")
        info = zipfile.ZipInfo("BUNDLE_NOTICE.txt", date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, notice)
    with zipfile.ZipFile(data_zip, "w") as archive:
        for path, member in named_data:
            add_file(archive, path, member)
        notice = (
            "Vaani V6 formatter training/evaluation text only. No audio or model "
            "weights are included. This bundle is for the declared private "
            "training run; do not redistribute it. Preserve source licenses and "
            "the provenance recorded in each row.\n"
        )
        info = zipfile.ZipInfo("data/DATA_NOTICE.txt", date_time=(2020, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, notice)

    manifest = {
        "format": "vaani-v6-colab-bundles/1",
        "code_bundle": {"file": code_zip.name, "sha256": sha256(code_zip), "bytes": code_zip.stat().st_size},
        "data_bundle": {"file": data_zip.name, "sha256": sha256(data_zip), "bytes": data_zip.stat().st_size},
        "model_bundle": {"file": args.model_bundle.name, "sha256": sha256(args.model_bundle), "bytes": args.model_bundle.stat().st_size},
        "data_members": [member for _, member in named_data],
        "audio_included": False,
    }
    (out / "bundle_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "bundle_manifest.sha256").write_text(
        f"{sha256(out / 'bundle_manifest.json')}  bundle_manifest.json\n", encoding="ascii")
    print(json.dumps({
        "out_dir": str(out),
        "code_sha256": manifest["code_bundle"]["sha256"],
        "data_sha256": manifest["data_bundle"]["sha256"],
        "model_sha256": manifest["model_bundle"]["sha256"],
        "data_members": len(named_data),
        "audio_included": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
