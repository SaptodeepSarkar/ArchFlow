# V6 short filler replay experiment

## Hypothesis and controlled change

The completed corrected-control formatter failed short filler examples despite
improving the real-derived exact score. Its contract training fillers were
9–12 tokens long, whereas the inspected hard suite contains 5–6-token sources.
This suggests a coverage gap; it does not prove a causal explanation.

Change only the replay data: add short incidental fillers at varied positions
and cue-preservation controls to the same mixed training corpus. Retain the
360M base, seed 42, 3,000 steps, LoRA configuration and existing replay files.
These new labels are deterministic synthetic proposals, not human gold.

## Data and preflight evidence

`tools/build_v6_hard_examples.py` now supports category selection before its
quota. Its exclusion reader accepts edit-plan sources and foundation
`utterance.raw_stt`, and rejects missing source fields rather than silently
ignoring them. This fixes a leakage risk in replay generation.

The replay lives outside Git at
`~/.local/share/vaani/v6-data/formatter-filler-replay-20261004/train.jsonl`:
1,139 unique rows, zero schema errors. Generation excluded challenge, hard
evaluation, and both synthetic and real dev/test source sets; 128 proposed
sources overlapped the exclusion set and were omitted. Source exclusion is
case-insensitive exact matching, not a claim of template independence.

Pipeline preflight passed 34 tests and encoded 47,484 weighted training rows
and 5,524 dev rows. The previous run encoded 44,067 training rows; the increase
is exactly 1,139 rows replayed three times. No new model quality result is
available at preflight.

## Evaluation and limits

Compare the completed candidate with V5 and corrected-control on unchanged
diagnostic suites, reporting raw learned output separately from guard output.
Reject unsupported additions, meaning-changing omissions, and regressions in
quotation/hesitation preservation. Existing hard and real test results have
already been inspected during development; they cannot alone establish final
promotion. An independently reserved final suite and real Android memory and
latency measurements remain necessary.

Expected improvement: short filler removal without broader deletion. Budget:
45 minutes maximum training wall time, 5 GiB host memory and no swap within
the training scope, and the 6 GiB GPU's capacity. Abort on timeout, memory
limit, CUDA OOM, or invalid data. Do not run concurrent STT/TTS training.
The GPU run was launched in `vaani-v6-filler-train-20261004.scope` with these
limits and verified active, with optimizer steps advancing beyond 40/3,000.
Early speed is about 1.7 seconds/step, so the fixed 3,000-step run will require
more than one 45-minute segment. Resume only after verifying the segment has
terminated and identifying its last complete checkpoint. Preserve the original
inputs/settings and final-step selection; no quality gain is established yet.

Independent STT data check during the run: the expanded synthetic vocabulary
audio manifest contains 971 valid clips, zero integrity errors and zero
untracked files. Only 41/79 planned terms are represented (40 have all 24
clips; one has 11); 38 terms are missing. This partial pack must not be treated
as completed balanced training data. Acoustic diversity remains an STT task.
