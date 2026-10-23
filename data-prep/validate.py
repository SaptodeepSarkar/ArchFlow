#!/usr/bin/env python3
"""Validate the V8 data contract. Stdlib only.

    python3 data-prep/validate.py
    python3 data-prep/validate.py --data-root .data/v8
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from collections import Counter
from pathlib import Path

BUCKETS = {"asr": 6000, "filler": 4000, "repair": 3600, "identity": 2400,
           "entity": 1600, "tone": 1200, "code_switch": 800, "adversarial": 400}
STT_KEYS = {"id", "audio", "text", "speaker_id", "duration_s", "source", "accent"}
FMT_KEYS = {"id", "seed_id", "input", "output", "ops", "domain",
            "protected_tokens", "vocab", "variant"}

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def load(path: Path) -> list[dict]:
    if not path.exists():
        fail(f"missing {path}")
        return []
    return [json.loads(line) for line in path.open()]


def check_stt(root: Path) -> dict:
    base = root / "stt"
    splits = {s: load(base / f"{s}.jsonl") for s in ("train", "dev", "test")}
    speakers: dict[str, set[str]] = {}
    for name, rows in splits.items():
        ids = {r.get("id") for r in rows}
        if len(ids) != len(rows):
            fail(f"stt/{name}: duplicate ids")
        spk = {r.get("speaker_id") for r in rows}
        speakers[name] = spk
        missing = 0
        for r in rows:
            if set(r) < STT_KEYS:
                fail(f"stt/{name}: missing keys in {r.get('id')}")
                continue
            if not (1 <= len(r["text"]) <= 200):
                fail(f"stt/{name}: bad text length {r['id']}")
            if not (1.0 <= float(r["duration_s"]) <= 30.0):
                fail(f"stt/{name}: bad duration {r['id']}")
            p = base / r["audio"]
            if not p.exists():
                missing += 1
                continue
            try:
                with wave.open(str(p), "rb") as w:
                    if (w.getnchannels(), w.getframerate(), w.getsampwidth()) != (1, 16000, 2):
                        fail(f"stt/{name}: not 16k mono pcm16 {p}")
                    if abs(w.getnframes() / 16000 - float(r["duration_s"])) > 0.25:
                        fail(f"stt/{name}: duration mismatch {p}")
            except wave.Error as exc:
                fail(f"stt/{name}: unreadable {p}: {exc}")
        if missing:
            fail(f"stt/{name}: {missing} missing wav files")

    for a, b in (("train", "dev"), ("train", "test"), ("dev", "test")):
        shared = speakers[a] & speakers[b]
        if shared:
            fail(f"stt: {a}/{b} share {len(shared)} speakers")
    if len(splits["test"]) != 500:
        fail(f"stt/test: {len(splits['test'])} clips, need 500")
    if len(speakers["test"]) < 20:
        fail(f"stt/test: only {len(speakers['test'])} speakers")
    hours = {s: sum(float(r["duration_s"]) for r in rows) / 3600
             for s, rows in splits.items()}
    if not (54.0 <= hours["train"] <= 66.0):
        fail(f"stt/train: {hours['train']:.2f} h outside 54-66 h")
    if not (0.9 <= hours["dev"] <= 1.1):
        fail(f"stt/dev: {hours['dev']:.2f} h outside 0.9-1.1 h")
    stats = base / "stats.json"
    if not stats.exists():
        fail("stt/stats.json missing")
    return {"hours": hours, "clips": {s: len(r) for s, r in splits.items()},
            "speakers": {s: len(v) for s, v in speakers.items()}}


def check_formatter(root: Path) -> dict:
    base = root / "formatter"
    splits = {s: load(base / f"{s}.jsonl") for s in ("train", "dev", "test")}
    rows = [r for rs in splits.values() for r in rs]
    if not (19000 <= len(rows) <= 21000):
        fail(f"formatter: {len(rows)} pairs outside 19000-21000")
    got = Counter(r.get("bucket") for r in rows)
    if dict(got) != BUCKETS:
        fail(f"formatter: bucket counts {dict(got)} != {BUCKETS}")
    if len({r.get("id") for r in rows}) != len(rows):
        fail("formatter: duplicate ids")
    seeds = {s: {r.get("seed_id") for r in rs} for s, rs in splits.items()}
    for a, b in (("train", "dev"), ("train", "test"), ("dev", "test")):
        if seeds[a] & seeds[b]:
            fail(f"formatter: {a}/{b} share seeds")
    for name, rs in splits.items():
        frac = len(rs) / max(1, len(rows))
        ok = 0.78 <= frac <= 0.82 if name == "train" else 0.08 <= frac <= 0.12
        if not ok:
            fail(f"formatter/{name}: split fraction {frac:.3f}")
    for r in rows:
        rid = r.get("id")
        if set(r) < FMT_KEYS:
            fail(f"formatter: missing keys in {rid}")
            continue
        if not r["input"] or not r["output"]:
            fail(f"formatter: empty text {rid}")
        if r["bucket"] == "identity":
            if not (r["input"] == r["output"] and r["ops"] == []):
                fail(f"formatter: bad identity {rid}")
        elif r["input"] == r["output"] or not r["ops"]:
            fail(f"formatter: zero-edit non-identity {rid}")
        if not set(r["ops"]) <= {"delete", "replace", "restore"}:
            fail(f"formatter: bad ops {rid}")
        ratio = len(r["output"]) / max(1, len(r["input"]))
        if not (0.85 <= ratio <= 1.6):
            fail(f"formatter: ratio {ratio:.2f} {rid}")
        for p in r["protected_tokens"]:
            if p.lower() not in r["output"].lower():
                fail(f"formatter: protected token lost {p!r} {rid}")
        for sp, ty in r["vocab"]:
            if sp.lower() not in r["input"].lower():
                fail(f"formatter: spoken vocab missing {sp!r} {rid}")
            if ty.lower() not in r["output"].lower():
                fail(f"formatter: typed vocab missing {ty!r} {rid}")
    return {"pairs": len(rows), "buckets": dict(got),
            "splits": {s: len(rs) for s, rs in splits.items()},
            "seeds": {s: len(v) for s, v in seeds.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=".data/v8")
    args = ap.parse_args()
    root = Path(args.data_root)
    summary = {"stt": check_stt(root), "formatter": check_formatter(root)}
    print(json.dumps(summary, indent=2))
    if errors:
        print(f"\n{len(errors)} validation error(s):", file=sys.stderr)
        for e in errors[:40]:
            print(" -", e, file=sys.stderr)
        return 1
    print("\nVALIDATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
