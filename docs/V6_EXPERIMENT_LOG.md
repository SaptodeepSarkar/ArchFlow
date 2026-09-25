# V6 Dataset Experiment Log

This log records bounded data experiments only. It does not contain formatter
training runs or promotion claims.

## Licensed real-derived pilot 001

- **Status:** completed as a data-pipeline pilot; all output remains review
  required and no training was launched.
- **Hypothesis:** actual frozen V5 faster-whisper output plus genuine timestamp
  metadata will expose formatter-relevant disfluency and punctuation cases that
  perfect source transcripts cannot represent.
- **Changed variable:** source audio passes through frozen V5 CT2 STT; no model
  or decoder comparison, formatter training, or output integration.
- **Dataset/split:** 25 ES2002a AMI dialogue-act slices / 93.952 audio seconds
  from official manual annotation v1.6.2. Rows remain `needs_human_review`,
  `split=null`; challenge-exclusion validation passed.
- **Actual output:** `/tmp/vaani-v6-ami-pilot/real-derived.jsonl` contains 25
  schema-valid real-derived review candidates with 227 word-confidence values,
  27 segment records, derived pause fields, four speaker groups, and portable
  audio references. Manifest SHA-256:
  `15692308852b16c4c79da20372643220374d33ebb194268e59027ef07e91b8b6`.
- **Resource estimate:** input package plus selected audio must fit in 1 GiB;
  capped selected audio is 300 seconds. Using the recorded CPU V5 control RTF
  of 0.4107 gives an approximate 123-second decode lower-bound proxy before
  I/O; CUDA is not assumed faster. Budget is 10 minutes wall time, 2 GiB host
  RSS, and 1.5 GiB VRAM if CUDA is used.
- **Abort conditions:** missing authoritative license/revision or source
  attribution; any source row lacks a trusted transcript; package exceeds disk
  cap; target STT fails; measured RSS/VRAM exceeds budget; malformed metadata;
  output attempts to enter a split without review.
- **Decision rule:** retain only structurally valid `needs_human_review` rows;
  do not call source references formatter ground truth. Record actual resources
  and reviewed/rejected counts after the experiment.
- **Actual configuration and outcome:** AMI annotations SHA-256
  `b56e5babb2496b8795deeeda7e71178d7fbc9963f94276cf2a3f4b56ebbc9f9d`;
  ES2002a Mix-Headset SHA-256
  `9c76866990fcc8b84006dc32d273ad99df439090b748ebe72103bb78c3216ee7`.
  CUDA `int8_float16` stopped before decoding because `libcublas.so.12` was
  unavailable. CPU `int8` completed all 25 clips. Wall time and peak RSS were
  not captured, so no runtime or memory claim is made.
- **Critical semantic failures:** not assessed; all formatter targets are
  review proposals rather than ground truth.
- **Decision:** retain all 25 as `needs_human_review`; do not split or train.

## Planned: licensed real-derived pilot 002

- **Hypothesis:** a deterministic non-overlapping second AMI batch broadens
  real disfluency coverage without contaminating the first pilot.
- **Changed variable:** candidate offset only; source release, model, decoder,
  schema, and 25-clip cap remain unchanged.
- **Dataset/split:** AMI ES2002a ranked candidate offset 25, at most 25 clips;
  `needs_human_review`, `split=null` only.
- **Resource estimate:** at most the same 300 seconds / 1 GiB disk / 10-minute
  CPU budget as pilot 001. CPU `int8` is selected because CUDA failed before
  decoding in pilot 001.
- **Abort condition:** duplicate source ID with pilot 001, invalid source
  manifest, missing trusted reference, resource cap breach, or failed schema
  validation. No target approval or training is allowed.
- **Actual result:** 25 AMI ES2002a candidates at offset 25 / 105.498 seconds;
  zero source-record overlap with pilot 001. CPU `int8` generated a
  schema-valid non-Git manifest SHA-256
  `ca88dea99612342bfbc8e766796c2c24fd2afd1c9c19894d9ee8529750689b03`.
  Triage flags 12 rows as `reference_content_mismatch`; all 25 remain
  `needs_human_review`, unsplit, and untrained.

## Android V5 Whisper export sanity check

- **Hypothesis:** the fused `hf_public_indian_v2` Whisper checkpoint is
  structurally convertible by whisper.cpp because it declares
  `WhisperForConditionalGeneration` / `model_type: whisper`.
- **Changed variable:** artifact representation only: fused HF checkpoint to a
  float whisper.cpp `ggml` model. The CT2 directory is excluded as converter
  input.
- **Validation slice:** no Android replacement and no training. If export
  succeeds, only a fixed subset of already licensed AMI pilot audio may be
  decoded later for host-side output/timestamp sanity.
- **Resource estimate:** clone a shallow whisper.cpp checkout (<100 MiB);
  float model plus converter temporaries may require up to 2 GiB in `/tmp`.
  Budget is 15 minutes wall time, 4 GiB RSS, and no GPU requirement.
- **Abort condition:** no official converter in the selected checkout,
  architecture/tokenizer incompatibility, output larger than 2 GiB, converter
  failure, or any attempt to use the CT2 artifact. No Android claim is allowed
  without later real-device measurement.
- **Actual result:** whisper.cpp commit `a44e078` documents
  `models/convert-h5-to-ggml.py` for Hugging Face fine-tuned Whisper models.
  It exported the fused checkpoint to a 923 MiB float `ggml` artifact (SHA-256
  `3a959f804218338f07e5b28091fbfc596f38353a6ea3ffe6449b76173f5406a2`) in
  `/tmp`; the official CPU `whisper-cli` built from that checkout loaded it and
  decoded one fixed licensed AMI pilot slice successfully. This checks only
  host conversion/load/decode compatibility. It does not compare WER or
  timestamps, quantize the model, install Android assets, or measure Android
  memory, latency, or accuracy.

## Licensed real-derived pilot 003 (blocked before execution, 2026-09-24)

- **Hypothesis:** a deterministic non-overlapping third AMI batch (offset 50)
  broadens real disfluency coverage without contaminating pilots 001/002.
- **Changed variable:** candidate offset only; source release, model, decoder,
  schema, and 25-clip cap unchanged.
- **Dataset/split (planned):** AMI ES2002a ranked candidate offset 50, at most
  25 clips / 300 s; `needs_human_review`, `split=null` only.
- **Resource estimate:** same 300 s / 1 GiB disk / 10-minute CPU budget as
  pilots 001/002. CPU `int8` preselected (CUDA failed before decoding before).
- **Abort condition (triggered):** the authorized precondition — already-cached
  AMI manual-annotation v1.6.2 package plus ES2002a Mix-Headset audio under
  `/tmp/vaani-v6-ami-pilot/` — is not met. `/tmp` no longer contains the pilot
  directory, the combined review queue, or the challenge file, and a
  repository-wide search found no surviving AMI annotation/audio artifact
  (`dialogueActs`, `ES2002a`, `ami-*` all absent outside `node_modules`/`.git`).
  Re-acquiring the pinned AMI files would be a fresh download, which the
  bounded authorization forbids, so no STT ran and no manifest was produced.
- **Safe verifications completed instead (no downloads, no training):**
  deterministic 18-case challenge regenerated to `/tmp` (hard-coded cases,
  eval-only); surviving 48-row synthetic seed re-validated with challenge
  exclusion — 0 errors, 48 `needs_human_review`, 0 collisions; splitter still
  yields train 0 / dev 0 / test 0. Frozen CT2 model and faster-whisper 1.2.1
  (Cozy venvs) confirmed present, so the only missing input is the AMI source
  package. Wall time and peak RSS: not captured, none claimed.
- **Decision:** pilot 003 retained as planned-but-unexecuted; approved counts
  unchanged at 0/0/0. Next step needs an explicit re-acquisition authorization
  for the pinned AMI annotation/audio files (or a decision to source offset-50
  equivalents elsewhere) before any STT ingest is attempted.

## Synthetic control-candidate scale check (2026-09-25)

- **Status:** completed as a review-queue and schema-scale check only; no
  formatter training or promotion was run.
- **Hypothesis:** the deterministic source-grounded control generator can
  populate a 50,000-row synthetic queue without challenge contamination or
  cross-group template leakage.
- **Changed variable:** corpus size only: 50,001 control edit-plan rows were
  generated with seed `20260925`; one phrase colliding with the frozen
  18-case challenge was excluded before v2 conversion.
- **Actual result:** `tools/import_v6_control_candidates.py` produced 50,000
  `synthetic` rows in `/tmp/v6-foundation-synthetic-50000.jsonl`. The
  foundation validator reported 50,000 rows, 0 errors, 0 train/dev/test rows,
  and 50,000 `needs_human_review` rows. The source edit-plan input separately
  passed its validator with 50,001 rows and 0 errors.
- **Leakage control:** conversion derives `group_id` from the same token
  bucket used by the foundation validator, so source pairs that the validator
  compares for near-duplication cannot be assigned to distinct later splits.
  The importer accepts a frozen evaluation manifest and excludes matching raw
  sources before writing output.
- **Decision:** retain the queue outside Git as deterministic synthetic review
  proposals. It counts toward neither the 50,000 approved synthetic target
  nor any training split until risk-stratified human review accepts rows.

## AMI 50k source acquisition (started 2026-09-25)

- **Status:** source acquisition running; no real-derived formatter row is
  approved or eligible for training.
- **Source and terms:** fresh AMI public manual annotation v1.6.2 from the
  University of Edinburgh source, SHA-256
  `b56e5babb2496b8795deeeda7e71178d7fbc9963f94276cf2a3f4b56ebbc9f9d`.
  The official download page states CC BY 4.0 for the signals and
  transcription.
- **Inventory:** the locally extracted annotations have 139 meetings, 687
  word-transcript files, and 66,533 eligible dialogue-act spans after the
  existing 3--30 lexical-token / <=15-second source filter. A deterministic
  round-robin selector wrote a 50,000-slice source-only plan spanning all 139
  meetings, plus 139 official Mix-Headset WAV URLs.
- **Current boundary:** the plan is stored only under the non-Git V6 data
  workspace. Each planned row still needs source-audio slicing, frozen V5
  final-STT inference with real metadata, semantic target review, and
  leakage-safe splitting. Source transcript text is not formatter ground
  truth, and no training was started.

## Fresh AMI target-STT pilot (2026-09-25)

- **Status:** completed as a 25-row source/STT/review-pipeline verification;
  all rows remain `needs_human_review`, unsplit, and untrained.
- **Input:** fresh ES2002a Mix-Headset WAV from the new official acquisition,
  SHA-256 `9c76866990fcc8b84006dc32d273ad99df439090b748ebe72103bb78c3216ee7`.
  The bounded dialogue-act selector chose 25 priority-cue source spans.
- **Target STT:** deployed Cozy CT2 via faster-whisper 1.2.1 on CPU `int8`.
  The output has 25 schema-valid rows, 80.320 seconds of selected source
  audio, 229 genuine word records, and 27 actual segment metadata records.
- **Review triage:** 13/25 rows are `reference_content_mismatch` at the 0.85
  LCS risk threshold and are critical review priority; the remaining 12 are
  normal priority. This flags risk only and did not alter targets or approve
  any row.
- **Decision:** retain the review queue in the non-Git V6 workspace. The next
  audio batches must follow this same source → final-STT → triage → human
  review path; a source reference must not be copied into a formatter target.

## AMI scale-ingestion continuation (2026-09-25)

- **Current revalidated output:** 4,660 schema-valid `real_derived`
  candidates, with 49,019 genuine word records and 5,209 segment metadata
  records. The non-Git scale manifest, plan, 39 complete WAVs, and two
  resumable partial WAVs are present after the workspace-state refresh.
- **Validation:** the restored deterministic 18-case evaluation artifact and
  the 4,660-row manifest validate with zero structural or challenge-collision
  errors. No row entered a training split or received automated approval.
- **Review triage:** 2,579/4,660 rows meet the lexical
  `reference_content_mismatch` risk flag; the other 2,081 remain normal
  priority. This is a review priority, not a quality score.
- **Quality gate:** empty/no-speech hypotheses are excluded by
  `tools/ingest_v6_ami_scale.py`; duplicate raw-STT hypotheses keep only the
  first source instance.
- **GPU transition:** CUDA probing reported one RTX 3050 device, but the
  CTranslate2 wheel required CUDA 12's `libcublas.so.12`, while the default
  toolkit exposed CUDA 13. Using the local CUDA-12 compatibility runtime at
  `/usr/local/lib/ollama/cuda_v12` plus system cuDNN 9 passed a real Cozy
  smoke transcription. The first full `cuda` / `float16` batch retained 65
  rows (10 empty hypotheses excluded). Future rows record `device` and
  `compute_type` in STT metadata.
- **Offline guard:** the ingester now sets `HF_HUB_OFFLINE=1` and passes
  `local_files_only=True` to faster-whisper. A real CUDA batch passed under
  that guard, preventing remote revision substitution or Hub traffic.
- **Cross-group duplicate gate:** validator caught one near-duplicate across
  speakers. The later instance was removed from the non-Git review manifest;
  the ingester now filters cross-group raw-STT near-duplicates at the same
  0.90 token-similarity threshold before writing each subsequent manifest.

## Codex session 01a0d4ac continuation and reconciliation (2026-09-25)

- **Prior session:** Codex session `01a0d4ac-56d9-7e21-b411-8f461cbd228f`
  (`Train V6 LLM: 50k real + 50k synth`) ran 2026-09-24/25, ending at run 19/20
  of a serial decoder loop with a claimed 2,324 committed + 2,364 uncommitted
  rows. No training, approval, split, or push occurred — correctly, per the V6
  human-review gate.
- **Initial surviving evidence (revalidated 2026-09-25):** 48-row foundation
  seed; 50,000-row synthetic control queue; 50-row AMI pilot; one verified
  ES2002a WAV; and the AMI v1.6.2 annotation zip + CC BY 4.0 provenance.
  These were the files visible before the later workspace-state refresh.
- **Durability fix:** the volatile `/tmp/v6-foundation-synthetic-50000.jsonl`,
  control corpus, challenge, and seed-verified files were copied to
  `~/.cache/vaani-v6-training/synthetic/` (non-Git). The synthetic queue is
  also deterministically regenerable via
  `tools/build_v6_formatter_dataset.py --count 50000 --seed 20260925` plus
  `tools/import_v6_control_candidates.py`.
- **Later state refresh:** the scale plan, 39 complete WAVs, and a 4,660-row
  real-derived manifest became visible again and validate against the restored
  challenge artifact with zero errors. The current dataset-status record uses
  that stronger evidence. Approved counts and train/dev/test counts remain
  0/0/0.
- **Decision:** no model trained or pushed; training stays blocked on blinded
  human review (`V6_REVIEW_PROTOCOL.md` + `tools/apply_v6_reviews.py`). Next
  operations are bounded CPU `int8` ingestion from the retained source plan,
  human review before any split/training, and an MDC credential for Common
  Voice plus a legal decision for SLR104 before those sources are touched.
