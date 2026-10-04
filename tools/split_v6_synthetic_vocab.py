#!/usr/bin/env python3
"""Create deterministic synthetic-vocabulary train/eval splits.

The input SQLite manifest is local-only and contains target speech text. This
tool writes the text only to the local evaluation manifest, never stdout or a
repo file. Term-disjoint splits measure unseen vocabulary; seen-term-context
splits measure new contexts. Both require a complete term/template/voice grid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


TABLE_SQL = """CREATE TABLE examples (
    id TEXT PRIMARY KEY, audio_path TEXT NOT NULL, target_text TEXT NOT NULL,
    term_pack TEXT NOT NULL, term_sha256 TEXT NOT NULL,
    template_index INTEGER NOT NULL, voice TEXT NOT NULL,
    sample_rate INTEGER NOT NULL, audio_sha256 TEXT NOT NULL,
    provenance TEXT NOT NULL)"""
TEMPLATES = {
    0: ("Please explain ", " in the Vaani project."),
    1: ("Check the ", " configuration before deployment."),
    2: ("Could you repeat the ", " result?"),
    3: ("I heard ", " during the review yesterday."),
    4: ("The documentation uses ", " in this example."),
    5: ("We should verify ", " before publishing the update."),
    6: ("Did you say ", " or the earlier option?"),
    7: ("Put ", " near the top of the notes."),
    8: ("I will ask the team whether ", " is available."),
    9: ("Can you spell ", " for me one more time?"),
    10: ("The new build reports a problem with ", "."),
    11: ("I think the audio says ", ", but I'm not sure."),
}


def validate_grid(rows, expected_terms=None, expected_templates=None, expected_voices=None):
    terms = {row["term_sha256"] for row in rows}
    templates = {int(row["template_index"]) for row in rows}
    voices = {row["voice"] for row in rows}
    for expected, actual, name in ((expected_terms, len(terms), "terms"),
                                   (expected_templates, len(templates), "templates"),
                                   (expected_voices, len(voices), "voices")):
        if expected is not None and expected != actual:
            raise SystemExit(f"incomplete vocabulary grid: expected {expected} {name}, found {actual}")
    if not voices or any(not voice for voice in voices):
        raise SystemExit("input has a missing voice identity")
    combinations = {(row["term_sha256"], int(row["template_index"]), row["voice"])
                    for row in rows}
    if len(combinations) != len(rows):
        raise SystemExit("duplicate term/template/voice combination")
    if len(combinations) != len(terms) * len(templates) * len(voices):
        raise SystemExit("incomplete term/template/voice grid; finish generation before splitting")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--holdout-percent", type=int, default=20)
    parser.add_argument("--strategy", choices=("term-disjoint", "seen-term-context"),
                        default="term-disjoint")
    parser.add_argument("--protocol", default=None)
    parser.add_argument("--expected-terms", type=int)
    parser.add_argument("--expected-templates", type=int)
    parser.add_argument("--expected-voices", type=int)
    args = parser.parse_args()
    if any(value is not None and value <= 0 for value in
           (args.expected_terms, args.expected_templates, args.expected_voices)):
        parser.error("expected grid dimensions must be positive")
    if args.protocol is None:
        args.protocol = ("v6-vocab-seen-term-context-v2"
                         if args.strategy == "seen-term-context"
                         else "v6-vocab-term-disjoint-v1")
    if not 1 <= args.holdout_percent <= 49:
        raise SystemExit("holdout percent must be between 1 and 49")
    if not args.manifest.is_file():
        raise SystemExit("input vocabulary manifest is missing")
    if args.out_dir.exists():
        raise SystemExit("refusing to overwrite an existing split directory")

    source = sqlite3.connect(f"file:{args.manifest.resolve()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    rows = source.execute("SELECT * FROM examples ORDER BY id").fetchall()
    source.close()
    if not rows:
        raise SystemExit("input vocabulary manifest is empty")
    hashes = sorted({str(row["term_sha256"]) for row in rows})
    if len(hashes) < 2:
        raise SystemExit("at least two distinct terms are required")
    validate_grid(rows, args.expected_terms, args.expected_templates, args.expected_voices)
    heldout = set()
    heldout_template: dict[str, int] = {}
    template_indices = sorted({int(row["template_index"]) for row in rows})
    if any(index not in TEMPLATES for index in template_indices):
        raise SystemExit("input contains an unknown synthetic template")
    if args.strategy == "term-disjoint":
        holdout_count = max(1, round(len(hashes) * args.holdout_percent / 100))
        ranked = sorted(hashes, key=lambda value: hashlib.sha256(
            f"{args.protocol}\0{value}".encode("ascii")).hexdigest())
        heldout = set(ranked[:holdout_count])
    else:
        # Vocabulary terms must be represented in train when measuring whether
        # acoustically fine-tuning teaches those terms. Hold out one complete
        # sentence frame per term (both voices) to test new-context transfer;
        # retain the term-disjoint suite separately as an unseen-word diagnostic.
        for term_hash in hashes:
            digest = hashlib.sha256(
                f"{args.protocol}\0context\0{term_hash}".encode("ascii")).digest()
            choice = int.from_bytes(digest[:4], "big") % len(template_indices)
            heldout_template[term_hash] = template_indices[choice]

    train_db_path = args.out_dir / "train.sqlite3"
    eval_path = args.out_dir / "heldout.jsonl"
    eval_rows = []
    train_rows = []
    for row in rows:
        fields = tuple(row[key] for key in row.keys())
        is_eval = (row["term_sha256"] in heldout if args.strategy == "term-disjoint"
                   else int(row["template_index"]) == heldout_template[row["term_sha256"]])
        index = int(row["template_index"])
        if index not in TEMPLATES:
            raise SystemExit("input contains an unknown synthetic template")
        prefix, suffix = TEMPLATES[index]
        target = str(row["target_text"])
        if not target.startswith(prefix) or not target.endswith(suffix):
            raise SystemExit("input target does not match its recorded template")
        term = target[len(prefix):len(target) - len(suffix)]
        if not term.strip() or hashlib.sha256(term.encode("utf-8")).hexdigest() != row["term_sha256"]:
            raise SystemExit("term hash does not match the synthetic target")
        audio = Path(str(row["audio_path"]))
        if not audio.is_file():
            raise SystemExit("input audio file is missing")
        if hashlib.sha256(audio.read_bytes()).hexdigest() != row["audio_sha256"]:
            raise SystemExit("input audio checksum mismatch")
        if not is_eval:
            train_rows.append(fields)
            continue
        eval_rows.append({
            "example_id": str(row["id"]),
            "audio_path": str(audio),
            "reference": target,
            "challenge_terms": [term],
            "challenge_tags": (["synthetic_vocab_unseen_term"] if args.strategy == "term-disjoint"
                               else ["synthetic_vocab_seen_term_new_context"]),
            "license": "organization-authored synthetic audio",
            "source": "local-kokoro-synthetic-vocabulary",
        })

    if not train_rows or not eval_rows:
        raise SystemExit("split produced an empty partition")
    args.out_dir.mkdir(parents=True)
    train_db = sqlite3.connect(train_db_path)
    train_db.execute(TABLE_SQL)
    placeholders = ",".join("?" for _ in range(10))
    train_db.executemany(f"INSERT INTO examples VALUES ({placeholders})", train_rows)
    train_db.commit()
    train_db.close()
    with eval_path.open("x", encoding="utf-8") as handle:
        for item in eval_rows:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    print(json.dumps({
        "protocol": args.protocol,
        "strategy": args.strategy,
        "source_manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "train_terms": len(hashes) - len(heldout) if args.strategy == "term-disjoint" else len(hashes),
        "heldout_terms": len(heldout) if args.strategy == "term-disjoint" else len(heldout_template),
        "train_rows": len(train_rows),
        "heldout_rows": len(eval_rows),
        "train_manifest_sha256": hashlib.sha256(train_db_path.read_bytes()).hexdigest(),
        "heldout_manifest_sha256": hashlib.sha256(eval_path.read_bytes()).hexdigest(),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
