#!/usr/bin/env python3
"""Split auto-aligned real formatter pairs without changing meeting groups."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from v6_real_alignment import validate_auto_row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_dir = args.out_dir.expanduser().resolve()
    if output_dir == repo_root or repo_root in output_dir.parents:
        raise SystemExit("split manifests contain transcript text and must stay outside the Git worktree")
    if output_dir.exists():
        raise SystemExit("refusing to overwrite split output directory")
    groups: dict[str, str] = {}
    ids: set[str] = set()
    sources: set[str] = set()
    rows: dict[str, list[dict]] = {split: [] for split in ("train", "dev", "test")}
    for line_no, line in enumerate(args.input.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        split = row.get("split")
        group = row.get("group_id")
        source = row.get("utterance", {}).get("raw_stt", "")
        if split not in rows or not isinstance(group, str) or not group:
            raise SystemExit(f"invalid split/group at row {line_no}")
        if not validate_auto_row(row):
            raise SystemExit(f"automatic validation failed at row {line_no}")
        if row["example_id"] in ids or source.casefold() in sources:
            raise SystemExit(f"duplicate ID/source at row {line_no}")
        if group in groups and groups[group] != split:
            raise SystemExit(f"meeting group crosses splits at row {line_no}")
        ids.add(row["example_id"])
        sources.add(source.casefold())
        groups[group] = split
        rows[split].append(row)
    if not ids:
        raise SystemExit("no validated rows")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{output_dir.name}.split-", dir=output_dir.parent) as temp_name:
        staged_dir = Path(temp_name) / "output"
        staged_dir.mkdir()
        for split, split_rows in rows.items():
            (staged_dir / f"{split}.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in split_rows),
                encoding="utf-8")
        if output_dir.exists():
            raise SystemExit("output directory appeared during split; refusing to overwrite")
        os.replace(staged_dir, output_dir)
    print(json.dumps({"rows": len(ids), "groups": len(groups),
                      "splits": {key: len(value) for key, value in rows.items()},
                      "out_dir": str(output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
