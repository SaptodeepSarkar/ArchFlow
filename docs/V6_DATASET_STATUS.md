# V6 Dataset Status

Status: `DATASET_BUILDING` (audited foundation only; no final V6 training).

All counts below are actual as of 2026-09-25. A discovered source is not an
admitted example, and a generated candidate is not an approved training row.

| Measure | Actual count | Evidence |
| --- | ---: | --- |
| Legacy real clips discovered locally | 4,037 | Cozy manifests: 3,987 `cv_indian_full` + 50 `santhosh_indian`; neither is admitted |
| Official real audio acquired for V6 | 111 complete Mix-Headset WAVs + 1 partial WAV | Fresh official AMI v1.6.2 CC BY 4.0 annotation archive and 111 verified-complete Mix-Headset WAVs are present in the non-Git V6 workspace; one partial WAV is currently downloading. |
| Real source slices legally usable for V6 | 50,000 selected / 66,533 eligible | The deterministic AMI v1.6.2 source-only plan spanning 139 meetings is present in the non-Git V6 workspace. |
| Real audio processed with target STT | 5,747 slices | Frozen Cozy CT2 / faster-whisper; 1,832 rows use offline GPU `float16`, and 3,915 earlier rows used CPU `int8`. Every retained row has word and segment metadata. |
| Real-derived review candidates | 5,747 | Fresh source reference, raw STT, portable audio checksum, 63,981 word records, and 6,568 segment metadata records; all remain `needs_human_review`. |
| Real-derived formatter pairs approved | 0 | Reference-derived targets are still unreviewed proposals |
| Synthetic candidates generated | 50,048 | 48 hand-authored semantic seeds plus 50,000 deterministic control candidates; all remain unapproved |
| Synthetic approved | 0 | All 50,048 candidates have `needs_human_review` |
| Synthetic rejected | 0 | No review rejection has occurred |
| Duplicates removed | 1 previously admitted near-duplicate | The ingester also filters exact raw duplicates and cross-group near-duplicates before admission |
| Train / dev / test approved rows | 0 / 0 / 0 | Splitter intentionally excludes unapproved candidates |
| Frozen 18-case challenge rows used for training | 0 | Explicitly excluded by schema and workflow |

## Candidate coverage

The 48 review-required candidates include: explicit repair 3; implicit repair
1; repair-negative/reasoning preservation 4; false start 1; abandoned thought
preservation 1; accidental repetition 2; intentional repetition 1; filler 1;
hesitation 1; uncertainty 1; quoted/metalinguistic speech 3; factual-claim
preservation 1; contraction/capitalization/punctuation 1 each; technical term,
package, acronym, URL, path, and spoken-letter cases 1 each; Hinglish/code
switching 2; anger, affection, casual style, and swearing 1 each; already
correct/ambiguous/do-not-edit 1 each; prose-not-list, list request,
continuation, termination, bullets, numbered list, heading, table, and
paragraph request 1 each. Every candidate carries `meaning_preservation`.

The AMI scale manifest contains 5,747 `real_derived` /
`formatter_target_unreviewed` candidates. Its target-STT metadata is genuine;
its formatter targets have not received semantic review.

Lexical-risk triage flags 3,340 of the 5,747 rows as
`reference_content_mismatch` at a 0.85 LCS threshold. Those rows must not be
copy-approved from reference text; the remaining 2,407 also remain unapproved.

## Rejection and review ledger

No candidate has passed human review, so none is eligible for a split or
training. The local Indian-English audio is rejected for admission—not deleted
or discarded—because its exact upstream license/revision was not retained.
The audit rejects Switchboard, NXT annotations, and FluencyBank for license or
access incompatibility; it defers IndicVoices and People’s Speech until exact
terms are verified. Schema validation rejected 0 of 48 synthetic and 0 of
5,747 AMI candidates; this proves structure, not semantic quality.

## Validation evidence

```sh
python3 tools/build_v6_foundation_seed.py --out data/v6-foundation/candidates.jsonl
python3 tools/validate_v6_foundation.py data/v6-foundation/candidates.jsonl \
  --forbid-sources /tmp/v6-foundation-challenge.jsonl
# result: 48 rows, 0 structural errors, 48 needs_human_review, 0 challenge collisions
python3 tools/split_v6_foundation.py --input data/v6-foundation/candidates.jsonl --out data/v6-foundation/splits
# result: train 0, dev 0, test 0
```

The output directory is Git-ignored. Audio, source corpora, generated datasets,
weights, and caches are not committed.

## Shortfall and next operation

Validated approved data is `0 / approximately 100,000`: real-derived `0 /
approximately 50,000`, synthetic `0 / approximately 50,000`. A reproducible
50,000-row synthetic *candidate* queue now exists outside Git, generated from
the source-grounded edit-plan control corpus and converted with
`tools/import_v6_control_candidates.py`. It is deliberately counted as zero
approved synthetic rows: deterministic templates are not independent,
human-reviewed formatter ground truth. The next operation is blinded human
review of the 5,747 AMI candidates and a representative, risk-stratified synthetic
queue to accept, correct, or reject formatter targets before assigning any
split.

The current AMI review queue is
`~/.local/share/vaani/v6-data/ami-v1.6.2/scale-50000/review-queue-triaged.jsonl`,
emitted by `tools/triage_v6_review_candidates.py`. A reviewer must set an explicit named
`ACCEPT`, `CORRECT`, or `REJECT` decision; `tools/apply_v6_reviews.py` is the
only provided path that changes review status. It does not infer approval.
Use the risk-prioritized combined queue and the checks in
`V6_REVIEW_PROTOCOL.md`.

The next audited acquisition source is Mozilla Common Voice Spontaneous Speech
3.0 English (dataset ID `cmn1pv5hi00uto1072y1074y7`). Its official download
path requires an authorized Mozilla Data Collective API credential and explicit
term acceptance, so no package or rows are claimed acquired from it.

Google FLEURS `en_in` remains deferred: the archive and TSV paths in Cozy's
existing downloader return HTTP 404 at its pinned `google/fleurs` revision.
No FLEURS package or row is claimed acquired; a current authoritative artifact
route must be audited before retrying.

AI4Bharat IndicVoices Hindi is now audit-accepted only as a supplemental Hindi
control source. Its CC BY 4.0 release has speaker/transcript metadata but no
English configuration or verified Hinglish coverage, and file access is gated;
no package or row is claimed acquired.

OpenSLR SLR104 (MUCS 2021) is a high-value 95.04-hour Hindi-English
code-switching candidate with sentence timestamps, but its authoritative CC
BY-SA 4.0 license needs a project distribution decision. No archive or row is
claimed acquired.

HiACC is rejected for product use: its data-access statement is CC BY-NC 4.0
for academic/research use, despite its article being CC BY. No archive or row
is claimed acquired.

OpenStax *Elementary Algebra 2e* is rejected pending written permission: its
current title page uses CC BY-NC-SA 4.0 and bars generative-AI ingestion, even
though an older PDF has a conflicting CC BY 4.0 notice. No text or synthetic
row from it is claimed acquired or generated.

The validator’s near-duplicate gate was exercised with a 0.923 token-similarity
cross-group variant and rejected it. Both the 48-row synthetic candidate file
and the 50-row combined AMI candidate file pass with zero structural or leakage
errors.

The review application path was separately exercised on a temporary copy of
the AMI manifest: one explicit fixture `ACCEPT` decision with named reviewer
and notes produced one structurally valid approved row, while the same decision
without notes was rejected. This did not modify the production queue or change
the actual approved count above. Approved and rejected rows now require the
human-review method, a named reviewer, and preserved review notes.

## Bounded real-derived importer

`tools/ingest_v6_real_derived.py` is ready for the pilot. Its defaults select
at most 25 clips and 300 seconds of audio before loading the frozen CT2 model;
it records faster-whisper word timings, word probabilities, segment-level
no-speech/average-log probabilities, and derived pauses only when produced.
It requires portable audio references, a license reference, and a trusted
source transcript; every output row remains `needs_human_review` and no output
is permitted into train/dev/test without approval. It ran once on the AMI
pilot: CUDA `int8_float16` failed before decoding because `libcublas.so.12`
was unavailable; CPU `int8` completed both 25-clip batches. No CPU latency or
memory measurement was captured, so none is claimed.
