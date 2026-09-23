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
