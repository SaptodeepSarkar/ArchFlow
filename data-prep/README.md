# V8 data preparation

Builds the two datasets used by `training/run_all.sh`. Contract:
`.research/full-finetune-small-models/03-run-contract.md`.

## Current artefacts (validated 2026-10-22)

| set | train | dev | test |
|---|---|---|---|
| STT | 62.72 h / 42,144 clips / 1,422 speakers | 1.00 h / 697 clips / 117 speakers | 0.82 h / 500 clips / 77 speakers |
| formatter | 16,077 pairs / 5,757 seeds | 1,893 / 687 | 2,030 / 722 |

Root: `.data/v8/` (gitignored). Bundle:
`.data/v8/bundles/vaani-v8-data.tar.zst` + `.sha256`.

STT source: `ishands/commonvoice-indian_accent`, a public non-gated parquet
re-upload of Common Voice 21 English clips whose accent field is Indian. Every
row keeps the original `accents` string in `accent`, so nothing is relabelled.

Formatter sources: Tatoeba English (CC-BY 2.0) for general seeds, GoEmotions
(Apache-2.0) for tone seeds, and hand-written templates in
`prepare_formatter.py` (CC0). The clean side is always human text; only the
noisy side is generated.

## Rebuild

```sh
# 1. raw Common Voice shards (already in .data/v8/_raw; ~3.9 GB)
mkdir -p .data/v8/_raw
for i in 0 1 2 3 4 5 6 7 8; do
  f="$(printf 'train-%05d-of-00009.parquet' "$i")"
  curl -L --fail -o ".data/v8/_raw/$f" \
    "https://huggingface.co/datasets/ishands/commonvoice-indian_accent/resolve/main/$f"
done

# 1b. formatter seeds (already in .data/v8/_seeds)
mkdir -p .data/v8/_seeds
curl -L --fail -o .data/v8/_seeds/eng_sentences.tsv.bz2 \
  https://downloads.tatoeba.org/exports/per_language/eng/eng_sentences.tsv.bz2
# GoEmotions (Apache-2.0): put a parquet with `text` and `labels` at
# .data/v8/_seeds/goemotions.parquet; if missing, tone falls back to templates.

# 2. STT: 60 h target, speaker-disjoint dev/test, capped clips per speaker
data-prep/.venv/bin/python data-prep/prepare_stt.py --hours 60

# 3. formatter: 20,000 pairs, exact mix, 80/10/10 by seed
data-prep/.venv/bin/python data-prep/prepare_formatter.py

# 4. contract check
python3 data-prep/validate.py
```

`prepare_stt.py` reads the parquet metadata first, assigns speakers to one split
only, then streams mp3 bytes through ffmpeg. Audio is never written as mp3.
`prepare_formatter.py` is deterministic (fixed seed), so a rebuild reproduces
the same 20,000 rows.

## Deliberate deviations from the contract

- STT has **64.54 h** total (62.72 h train), not exactly 60 h: whole speakers are selected, and the
  contract allows ±10%.
- Formatter `vocab` rows are **8.25%**, not ~20%. Only entity rows (1,600) and
  rows with a gazetteer name/number carry a rule-6 mapping. The earlier version
  auto-labelled every sentence-initial capital (`The`, `They`) as a name; that
  was removed.
- Mean disfluency density is **10.23%** (contract target 12–15%, hard bound
  8–20%).
- No WER filtering: there is no local model budget. Quality uses Common Voice
  votes (`up_votes >= 2`, `down_votes == 0`) and duration/text filters.
- WAV headers written through an ffmpeg pipe are patched in `prepare_stt.py`;
  without that, `wave.open()` reports 2^31−1 frames.

## Checks

`validate.py` is stdlib-only and exits non-zero on: missing audio, wrong sample
rate/channels/bit depth, duration mismatch, speaker/seed leakage, bad counts,
zero-edit non-identity pairs, protected-token loss, vocab inconsistency, or a
length ratio outside 0.85–1.6.
