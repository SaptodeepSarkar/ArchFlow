#!/usr/bin/env python3
"""Build the V8 STT dataset (16 kHz mono PCM16 wav + jsonl) from Common Voice.

Source: `ishands/commonvoice-indian_accent` — a public, non-gated parquet
re-upload of Mozilla Common Voice v21 English recordings whose accent field is
"India" (163.89 h, 110,088 clips). Provenance is recorded in DATA-CARD.md; the
per-clip `accents` column is re-checked here so nothing is relabelled.

Two passes per shard: the first reads metadata only and decides speaker-disjoint
splits, the second streams the mp3 bytes through ffmpeg into 16 kHz mono PCM16
wav. Audio never reaches disk in its original form beyond a temp file that
ffmpeg reads; nothing is decoded into a Python audio array.

Usage:
  uv run --python 3.11 --with pyarrow --with requests --with tqdm \
      data-prep/prepare_stt.py                 # 60 h train
  ... prepare_stt.py --hours 40               # smaller subset
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pyarrow.parquet as pq
from tqdm import tqdm

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / ".data/v8/_raw"
OUT = REPO / ".data/v8/stt"

DATASET = "ishands/commonvoice-indian_accent"
SHARDS = [f"train-{i:05d}-of-00009.parquet" for i in range(9)]

MIN_S, MAX_S = 1.0, 30.0
MIN_CHARS, MAX_CHARS = 1, 200
MIN_WORDS = 3
DEV_SECONDS = 3600.0
TEST_CLIPS = 500


def norm(text: str) -> str:
    return " ".join(text.split())


def stable_key(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


def ffmpeg_wav(mp3: bytes) -> bytes:
    """mp3 bytes -> 16 kHz mono PCM16 wav bytes."""
    p = subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "mp3", "-i", "pipe:0",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"],
        input=mp3, capture_output=True, check=False,
    )
    if p.returncode != 0 or len(p.stdout) < 64:
        raise RuntimeError(p.stderr.decode()[-300:])
    # ffmpeg writing to a pipe cannot seek back, so it leaves RIFF/data sizes as
    # 0xFFFFFFFF. Patch them; wave.open() would otherwise report 2^31-1 frames.
    b = bytearray(p.stdout)
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        i = b.find(b"data")
        if i > 0:
            struct.pack_into("<I", b, 4, len(b) - 8)
            struct.pack_into("<I", b, i + 4, len(b) - i - 8)
    return bytes(b)


def wav_duration(wav: bytes) -> float:
    # 44-byte canonical header written by ffmpeg for PCM16.
    return max(0.0, (len(wav) - 44) / 32000.0)


def pass1() -> tuple[list, dict, dict]:
    """Metadata index + speaker-disjoint split assignment."""
    rows: list[tuple[int, int, str, str, float]] = []  # shard, rownum, id, text, dur
    for si, shard in enumerate(SHARDS):
        pf = pq.ParquetFile(RAW / shard)
        off = 0
        for b in pf.iter_batches(batch_size=8192, columns=[
                "client_id", "sentence", "up_votes", "down_votes", "accents", "duration_ms"]):
            cols = {n: b.column(n).to_pylist() for n in
                    ("client_id", "sentence", "up_votes", "down_votes", "accents", "duration_ms")}
            for i in range(b.num_rows):
                dur = (cols["duration_ms"][i] or 0) / 1000.0
                text = norm(cols["sentence"][i] or "")
                if int(cols["up_votes"][i] or 0) < 2 or int(cols["down_votes"][i] or 0) != 0:
                    continue
                if not (MIN_S <= dur <= MAX_S):
                    continue
                if not (MIN_CHARS <= len(text) <= MAX_CHARS) or len(text.split()) < MIN_WORDS:
                    continue
                acc = (cols["accents"][i] or "")
                if "india" not in acc.lower() or "indiana" in acc.lower():
                    continue
                if not cols["client_id"][i]:
                    continue
                rows.append((si, off + i, cols["client_id"][i], text, dur))
            off += b.num_rows

    by_spk: dict[str, list] = defaultdict(list)
    for r in rows:
        by_spk[r[2]].append(r)

    speakers = sorted(by_spk, key=stable_key)
    assigned: dict[tuple[int, int], str] = {}
    used: set[str] = set()

    # Take clips (not whole speakers) so the counts are exact, but always drop the
    # rest of a speaker's clips so no speaker reaches a second split.
    need = TEST_CLIPS
    for spk in speakers:
        if need <= 0:
            break
        clips = sorted(by_spk[spk], key=lambda c: (c[0], c[1]))
        take = clips[:min(need, 10)]  # cap per speaker: many speakers, not 2
        for c in take:
            assigned[(c[0], c[1])] = "test"
        need -= len(take)
        used.add(spk)

    need_s = DEV_SECONDS
    for spk in speakers:
        if spk in used or need_s <= 0:
            continue
        clips = sorted(by_spk[spk], key=lambda c: (c[0], c[1]))
        for c in clips[:10]:
            if need_s <= 0:
                break
            assigned[(c[0], c[1])] = "dev"
            need_s -= c[4]
        used.add(spk)
    return rows, assigned, by_spk


def pick_train(rows, assigned, by_spk, hours: float) -> None:
    target = hours * 3600.0
    used = {r[2] for r in rows if (r[0], r[1]) in assigned}
    total = 0.0
    for spk in sorted(by_spk, key=stable_key):
        if spk in used:
            continue
        d = sum(c[4] for c in by_spk[spk])
        if total + d > target * 1.05:
            if total >= target * 0.95:
                break
            continue  # a big speaker that would overshoot; try later ones
        for c in by_spk[spk]:
            assigned[(c[0], c[1])] = "train"
        total += d
    print(f"train budget {target/3600:.1f} h -> selected {total/3600:.1f} h")


def pass2(rows, assigned, workers: int) -> dict:
    key_of_id = sorted(((r[0], r[1]) for r in rows))
    id_of = {k: f"cv-en-in-{i+1:06d}" for i, k in enumerate(key_of_id)}
    wanted = {(r[0], r[1]): r for r in rows if (r[0], r[1]) in assigned}
    for split in ("train", "dev", "test"):
        (OUT / "audio" / split).mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    failed = 0
    pool = ThreadPoolExecutor(max_workers=workers)

    def record(k: int, split: str, accent: str, spk: str, dur: float) -> None:
        records.append({
            "id": id_of[k], "audio": f"audio/{split}/{id_of[k]}.wav",
            "text": wanted[k][3], "speaker_id": spk,
            "duration_s": round(dur, 2),
            "source": "common_voice_21_en_indian", "accent": accent,
        })

    for si, shard in enumerate(SHARDS):
        todo = {k for k in wanted if k[0] == si}
        if not todo:
            continue
        pf = pq.ParquetFile(RAW / shard)
        off = 0
        jobs = []
        for b in pf.iter_batches(batch_size=2048, columns=["audio", "accents", "client_id"]):
            if not todo:
                break
            blobs = b.column("audio").field("bytes")
            accents = b.column("accents").to_pylist()
            spks = b.column("client_id").to_pylist()
            for i in range(b.num_rows):
                k = (si, off + i)
                if k not in todo:
                    continue
                todo.discard(k)
                # Always re-decode: reusing an existing file let stale audio from an
                # earlier filter/mapping survive next to freshly mapped text.
                # shortcut: a rerun re-decodes every clip (~20 min), add a verified
                # id->row manifest if mid-build resume becomes necessary.
                jobs.append((k, blobs[i].as_py(), accents[i], spks[i]))
            off += b.num_rows
            if jobs:
                futs = [pool.submit(ffmpeg_wav, blob) for (_, blob, _, _) in jobs]
                for (k, _blob, accent, spk), fut in zip(jobs, futs):
                    try:
                        wav = fut.result()
                    except Exception as e:  # noqa: BLE001
                        failed += 1
                        if failed < 5:
                            print(f"ffmpeg failed {id_of[k]}: {e}", file=sys.stderr)
                        continue
                    dur = wav_duration(wav)
                    if not (MIN_S <= dur <= MAX_S):
                        failed += 1
                        continue
                    split = assigned[k]
                    (OUT / "audio" / split / f"{id_of[k]}.wav").write_bytes(wav)
                    record(k, split, accent, spk, dur)
                jobs = []
        print(f"{shard}: {len(records)} clips so far", flush=True)

    out = {}
    for split in ("train", "dev", "test"):
        rs = sorted((r for r in records if r["audio"].startswith(f"audio/{split}/")),
                    key=lambda r: r["id"])
        with (OUT / f"{split}.jsonl").open("w") as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        out[split] = rs
    print(f"failed/skipped: {failed} | re-encoded: {len(records)}")
    return out


def write_stats(splits: dict) -> None:
    st = {"dataset": DATASET, "sample_rate": 16000, "channels": 1,
          "encoding": "pcm_s16le", "splits": {}}
    accent_counter = Counter()
    for name, rs in splits.items():
        hours = sum(r["duration_s"] for r in rs) / 3600.0
        spk = {r["speaker_id"] for r in rs}
        st["splits"][name] = {"clips": len(rs), "hours": round(hours, 3),
                              "speakers": len(spk),
                              "mean_duration_s": round(sum(r["duration_s"] for r in rs) / max(len(rs), 1), 2)}
        st["splits"][name]["accent_counts"] = dict(Counter(r["accent"] for r in rs))
        accent_counter.update(r["accent"] for r in rs)
    st["total_clips"] = sum(len(v) for v in splits.values())
    st["total_hours"] = round(
        sum(sum(r["duration_s"] for r in rs) for rs in splits.values()) / 3600.0, 3)
    st["accent_counts"] = dict(accent_counter)
    st["filters"] = {
        "up_votes_min": 2, "down_votes_max": 0, "duration_s": [MIN_S, MAX_S],
        "text_chars": [MIN_CHARS, MAX_CHARS], "min_words": MIN_WORDS,
        "accent_contains": "india", "split_by": "speaker_id (client_id), speaker-disjoint",
        "wer_filtering": "none — no local WER budget; documented in DATA-CARD.md",
    }
    (OUT / "stats.json").write_text(json.dumps(st, indent=2) + "\n")
    print(json.dumps({k: st["splits"][k] for k in st["splits"]}, indent=2))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=60.0)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")

    missing = [s for s in SHARDS if not (RAW / s).exists()]
    if missing:
        sys.exit(f"missing shards in {RAW}: {missing}\nRun the download documented in README.md")

    rows, assigned, by_spk = pass1()
    print(f"{len(rows)} clips pass the metadata filter, {len(by_spk)} speakers")
    if not rows:
        sys.exit("no clips passed the filter")
    pick_train(rows, assigned, by_spk, args.hours)
    splits = pass2(rows, assigned, args.workers)
    write_stats(splits)

    tr = sum(r["duration_s"] for r in splits["train"]) / 3600
    print(f"\ntrain {tr:.2f} h / {len(splits['train'])} clips | "
          f"dev {sum(r['duration_s'] for r in splits['dev'])/3600:.2f} h | "
          f"test {len(splits['test'])} clips")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
