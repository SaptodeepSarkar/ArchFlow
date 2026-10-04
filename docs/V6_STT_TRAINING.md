# V6 STT training

## Current execution state — 2026-10-04

No V6 STT model-training process is running. Earlier STT training attempts
described below are historical: candidates that failed WER or protected-term
gates remain quarantined, and the deployed recognizer remains V5. The
synthetic-vocabulary audio builder that could supply a future experiment is
SIGSTOP-paused at the user's request while research and pipeline safeguards
are completed. Its output contains 682 WAVs plus the SQLite manifest (683
files total). The strengthened validator checked all 682 rows: zero audio
errors, zero untracked files, mono PCM16 at 24 kHz, durations 1.728–4.075 s.
This remains a partial build against a 1,896-clip target, not a complete
vocabulary set. Do not infer V6 STT readiness or training progress from these
files.

Status: the 1,500-step context-holdout candidate finished from the clean
Whisper-small base, failed its vocabulary and protected-term gates, and is
quarantined. Its paired full AMI-dev comparison is complete. Vaani remains on
V5. The
earlier 500-step candidate and its evaluation are quarantined, not promoted.
That pilot's fused V5 starting checkpoint was trained on 92 synthetic audio
rows generated with Deepgram Flux TTS; current Deepgram terms prohibit use of
its outputs for model training and benchmarking. Vaani is back on `v5` for
final STT, live preview remains on `v5`, and review-before-insertion remains
enabled. The `v6` selector is reserved for a clean-source artifact and will
reject selection until that artifact exists. No Android model has changed.

Historical note — the fresh-base 20% SQLite vocabulary-exposure follow-up was
training on the local GPU at
`~/.local/share/vaani/models/v6-stt-vocab-20pct-20261002/training/`. On
2026-10-03 its durable checkpoint advanced to step 1,300 of 1,500. That
experiment and its paired evaluations have since completed; the candidate
failed qualification and was quarantined, as detailed below. No V6 STT
training is currently active.

V6 STT is the acoustic recognizer, separate from the V6 text formatter.
Whisper's tokenizer stays unchanged. Vocabulary coverage must come from
admissible speech/transcript examples and carefully evaluated contextual
biasing, not by appending token IDs.

## Provenance finding and corrective action

The 500-step pilot started from the locally fused `hf_public_indian_v2`
checkpoint. Its recorded public-Indian training manifest has 1,517 rows,
including 92 rows labelled `flux_indian_hard`; the local manifest maps those to
Deepgram Flux TTS clips through OpenRouter. Deepgram's current Terms §2.4(9)
bar using its services or outputs for competitive use, including model
training and benchmarking, while OpenRouter makes the provider's terms
applicable. The source audit now rejects the Flux set for V6 use. Consequently,
the V6-500 adapter, merged checkpoint, and metrics are retained for traceability
only; they are not a qualified candidate and must not be used as a training
base or promoted.

A planned 1,000-step continuation from that adapter was interrupted at about
50 steps as soon as the lineage issue was found. It did not finish or produce a
final adapter. Its scratch output is kept locally. The live Vaani setting was
reverted to V5, with review-before-insertion confirmed true and no pending
utterance.

## Known-term context experiment — completed; vocabulary gate failed (2026-10-01)

The next run started at approximately 02:37 IST, under
`~/.local/share/vaani/models/v6-stt-vocab-context-automated-20261001/`.
Hypothesis: retaining all configured terms in training while holding out a
sentence frame for each term measures learned vocabulary recognition in new
contexts. The changed training variable is the synthetic split; the clean
Whisper-small initialization, 22,445 AMI training rows, 1,500 steps, batch 2,
accumulation 8, learning rate 1e-5, and disabled augmentation are retained.
There are 316 synthetic training clips and 158 held-out clips, each partition
covering the same 79 terms. Both Kokoro voices occur in both partitions, so
this is a context test and does not prove generalization to new speakers or
Indian-English accents. Synthetic audio remains labeled synthetic.

Training completed all 1,500 steps, saved the adapter, and reported 7,318 s
runtime and 12.8 aggregate training loss; neither training loss nor step count
is an accuracy result. The wrapper then hit a shell syntax error before
evaluation. Evaluation was resumed from the saved adapter, without retraining.
On all 158 context-held-out clips (162 protected-term occurrences), base
Whisper-small scored 11.8644% normalized WER and 74.0741% protected-term
accuracy; the candidate scored 15.5367% WER and 66.0494% protected-term
accuracy. That is a 3.6723-point WER regression and an 8.0247-point
protected-term drop. Both promotion gates fail, so the adapter is quarantined.
The paired full AMI-dev evaluation against the matching clean-base report
completed on all 3,121 clips. Base WER was 34.6903% with 33.33% protected-term
accuracy; candidate WER was 26.9172% with 11.11% protected-term accuracy
(support 9). AMI WER improved 7.7731 points, but protected-term accuracy fell
22.2222 points, so that gate also fails. The adapter remains quarantined.
The AMI manifest
contract contains meeting IDs but no speaker IDs. Its split prevents meeting
leakage; it is **not verified speaker-disjoint**, because speakers may recur
across meetings. Do not make speaker-generalization claims from this run.

The run used no SQLite oversampling: 316 synthetic rows were 1.39% of the
22,761-row stream, while 1,500 steps at batch 2 / accumulation 8 consume about
24,000 examples. That is roughly one draw per unique synthetic row on average.
Underexposure is therefore a plausible explanation for the weak term result,
not a demonstrated cause. The next controlled recipe starts again from clean
Whisper-small, preserves the same split and optimizer settings, and gives the
vocabulary SQLite source a 5% draw rate. ICSI remains evaluation-only in this
experiment so the vocabulary-sampling hypothesis is tested independently. Its
full selected-subset participant-held-out dev split is an additional regression
check; the ICSI test split stays untouched.

The follow-up candidate uses the same clean base, split, and training recipe,
with a 5% vocabulary-source draw; the full selected-subset ICSI dev split is
evaluation-only. The original process stopped after saving checkpoint 200 of
1,500. On 2026-10-01 it was resumed from that checkpoint, preserving the
existing split and output directory; the resume path accepts only a complete
checkpoint inside this experiment and refuses to overwrite evaluation
artifacts. The 16 focused preflight tests passed before the resumed trainer
started. It targets the original 1,500 steps and runs the paired
vocabulary-heldout, AMI-dev, and ICSI-dev evaluations afterward; no result
should be inferred from training loss.

That resumed process later received SIGTERM between checkpoints 300 and 400;
the only durable state remained checkpoint 300. On 2026-10-02 the same run was
restarted from checkpoint 300, again retaining the original split, 1,500-step
ceiling, and evaluation gates. The paired evaluations were completed on
2026-10-02 after recovering from the wrapper's premature exit; the
context-held-out vocabulary suite missed the 99% protected-term gate and
AMI/ICSI showed protected-term regressions. The candidate is rejected and is
not a qualified V6 artifact. Detailed aggregate metrics are recorded in the
sampling-exposure section below.

The original fresh-run command is:

```sh
pipelines/stt/train-evaluate-v6-vocab.sh \
  --train-manifest /home/saptodeep/.local/share/vaani/v6-data/stt-training/ami-v1.6.2-clean/train.jsonl \
  --dev-manifest /home/saptodeep/.local/share/vaani/v6-data/stt-training/ami-v1.6.2-clean/dev.jsonl \
  --synthetic-manifest /home/saptodeep/.local/share/vaani/v6-data/synthetic-vocab-v1-20260928/manifest.sqlite3 \
  --sqlite-source-fraction 0.05 \
  --supplemental-sqlite-dev-manifest /home/saptodeep/.local/share/vaani/v6-data/icsi-nxt-v1.0/import-3h-12meeting-20261001/dev.sqlite3 \
  --model /home/saptodeep/.cache/huggingface/hub/models--openai--whisper-small/snapshots/973afd24965f72e36ca33b3055d56a652f456b4d \
  --out /home/saptodeep/.local/share/vaani/models/v6-stt-vocab-5pct-20261001
```

To resume this experiment from its latest complete checkpoint, add:

```sh
--resume-training-checkpoint /home/saptodeep/.local/share/vaani/models/v6-stt-vocab-5pct-20261001/training/checkpoint-200
```

Resume continues the saved Trainer state; it does not rebuild the vocabulary
split or initialize from the prior rejected candidate. The ICSI test split
remains untouched.

## ICSI spontaneous-speech source — selected 12-meeting subset imported

The official ICSI core annotation release is CC BY 4.0 and contains about 70
hours of spontaneous English meetings. Its 19.5-MB v1.0 NXT archive has been
downloaded outside Git and integrity-checked. An aggregate-only XML audit found
75 meetings, 494 speaker-channel word streams, 465 dialogue-act streams,
1,003,968 word elements, and 41,187 explicit `<disfmarker>` events; 1,003,940
word elements have both start and end times. The archive also contains 61
participant records, so the importer must use participant IDs transiently for
speaker-disjoint splits and discard age, gender, country, language, and other
profile fields.

`tools/build_v6_icsi_stt_sqlite.py` now converts official meeting audio plus
these NXT annotations into bounded, speaker-disjoint SQLite train/dev/test
manifests. The shared trainer and V6 wrapper now accept repeated SQLite
manifests, each optionally carrying its own loss weight, and the paired
evaluator reads SQLite targets directly while emitting aggregate-only JSON
reports. It drops nonlexical
`<disfmarker>` placeholders, requires valid word timings, excludes spans
overlapped by another annotated speaker, allows a bounded caller-selected cap
(up to 70 hours), writes no transcript-bearing JSON, and refuses output inside
the Git worktree or over an existing destination. It does not download audio
or accept terms. Parse-only validation found 26,703 eligible timed, non-overlapping
utterances, covering 52 participant groups / 21.7 hours before audio is staged.
The official download page's generated request for a chosen 12-meeting subset
estimates 1 GB and names each mixed WAV as `{meeting}.interaction.wav`. That
subset has 4,063 eligible spans / 3.07 transcript hours across 25 speaker
groups before the import cap; the speaker-disjoint partition is 2,221 train /
886 dev / 956 test rows across 18 / 3 / 4 participant groups. All 12 WAVs are
now acquired and readable. A clearly labeled two-hour pilot, imported before
the final two WAVs arrived, remains at
`~/.local/share/vaani/v6-data/icsi-nxt-v1.0/import-2h-pilot-20261001/`:
1,422 train / 577 dev / 618 test clips across 16 / 3 / 4 participant groups.
All 2,617 extracted mono PCM16 clips open and have valid nonempty frames; all
three SQLite databases pass `PRAGMA quick_check`, with zero example-ID overlap
between splits. Their schema stores only row ID, audio path, target text, and
sample weight (no speaker IDs or demographics). The full 3-hour subset is
imported at
`~/.local/share/vaani/v6-data/icsi-nxt-v1.0/import-3h-12meeting-20261001/`:
2,169 train / 861 dev / 936 test clips across 18 / 3 / 4 participant groups.
All 3,966 clips are readable mono PCM16; SQLite integrity checks pass and
train/dev/test example IDs are disjoint. Neither ICSI import has entered STT
training or evaluation.

The full selected subset is now available for a separate fresh-base training
candidate. Compare it against held-out ICSI speakers, AMI dev/test, protected
vocabulary, and V5 control; keep ICSI test untouched until recipe selection.
ICSI meetings are not Indian-English evidence, so this source supplements but
does not replace the accent-focused evaluation path.

For iterative model selection, combine `ICSI/train.sqlite3` with the existing
vocabulary SQLite set, and use only `ICSI/dev.sqlite3` as the supplemental
development suite. Keep `ICSI/test.sqlite3` out of repeated runs; after recipe
selection, perform one paired V5/V6 evaluation on that speaker-held-out test
database with `tools/eval_v5_whisper_adapter.py` and compare its aggregate
reports. The imported speaker IDs are hashed for split assignment and then
discarded; test records are not converted to row-addressable JSON.

## Official South Asian English data path — prepared, not ingested

The audited Mozilla Data Collective release is pinned to its official
artifact, `common-voice-scripted-speech-26-0-south-9d6029b6.tar.gz` (CV 26.0,
CC0-1.0). Its official train/dev/test split has 101,702 / 6,533 / 3,864 clips
from 2,270 / 102 / 81 disjoint speakers. The archive is 3.83 GB; one speaker
has 5,019 clips, so evaluate whether row-uniform training overweights that
voice. The release is a combined India/Pakistan/Sri Lanka self-declared accent
slice, not India-only. See `docs/V6_DATASET_AUDIT.md` for the license and
source limitations.

`tools/import_v6_mdc_common_voice.py` is an offline, automatic importer. It
requires the exact archive and an explicit `--terms-accepted` confirmation; it
does not accept terms or download anything. It rejects unexpected row/speaker
counts, overlap between official speaker splits, bad audio, duplicate audio,
and archive traversal/links; it strips source speaker IDs and demographics,
converts audio to 16-kHz mono PCM16, and writes only outside Git. No manual
row review is required. The importer emits both uniform `train.jsonl` and an
alternative `train-speaker-capped.jsonl` using
`min(1, sqrt(500 / speaker_clip_count))` loss weights. Train these as separate
fresh-base candidates with the same AMI/vocabulary recipe, then compare both
against the same `dev.jsonl` and AMI dev. The resulting manifests can be passed
to the existing wrapper as supplemental training/development inputs. Keep
`test.jsonl` isolated for one final qualification after model/decoder
selection; never use it for tuning.

After authorized acquisition/import, the speaker-capped candidate uses the
existing fully automated trainer/evaluator (with a separate fresh output dir):

```sh
pipelines/stt/train-evaluate-v6-vocab.sh \
  --train-manifest "$AMI_DATA/train.jsonl" \
  --supplemental-train-manifest "$CV_DATA/train-speaker-capped.jsonl" \
  --dev-manifest "$AMI_DATA/dev.jsonl" \
  --supplemental-dev-manifest "$CV_DATA/dev.jsonl" \
  --synthetic-manifest "$VOCAB_DATA/manifest.sqlite3" \
  --model "$CLEAN_WHISPER_SMALL" \
  --out "$PRIVATE_RUN_DIR/v6-cv-speaker-capped" \
  --sqlite-sample-fraction 0.02
```

Run the uniform `train.jsonl` as a separate control with the same recipe and
another fresh output directory. The 2% synthetic draw is an explicit sampling
mixture; `--sample-weight` remains a separate loss-weight variable.

This path has **not** been run: no authorized MDC archive is staged locally and
the account owner's terms acceptance is not established. The partial
Hugging Face mirror cache is explicitly not an input.

The shared trainer now accepts repeated private `--sqlite-manifest` sources.
`--sqlite-sample-fraction` draws one requested share from their combined pool;
`--sqlite-source-fraction` can instead assign a separate target share to each
manifest in argument order, with the shares summing below 1. Without either
option, the previous uniform-over-rows stream is unchanged. Per-row
`sample_weight` columns take precedence; `--sqlite-sample-weight` is the
fallback for older manifests. Separate source rates matter when mixing the
316 vocabulary clips with thousands of ICSI utterances: a combined pool would
otherwise allocate samples proportional to row count and further dilute the
vocabulary examples. Keep rates controlled and record them per experiment.

An independent aggregate audit confirmed zero overlapping example IDs, audio
checksums, or complete target sentences. The train SQLite SHA-256 is
`c428b55c8f728a2db7e9db1204aa04b03582798911673fa3f30001624a1cccb8`;
the held-out manifest SHA-256 is
`627ca802f15bf725f4330a343f8411d3fce66db419642b920aa70c348c365eb9`.
The splitter reports `strategy: seen-term-context`; this run inherited the
older protocol salt `v6-vocab-term-disjoint-v1`, which must not be confused
with its actual strategy. New splits now select a strategy-specific salt by
default. Fifteen preflight tests passed. The running trainer was
verified after the interrupted tool call; it must not be restarted merely
because its observation session was interrupted.

Expected improvement: retain the earlier AMI WER gain while improving term
recognition. Synthetic sample weight 8 is a loss weight normalized within
each microbatch; it is **not** eightfold sampling or eightfold total influence.
The 316 synthetic rows make up about 1.39% of the unweighted training stream.
This run isolates the split change; an explicit sampling mixture would be a
separate recipe change requiring its own controlled experiment.

Exploration budget: at most approximately 3 hours of training plus 1 hour of
evaluation, 4 GiB trainer RSS, and 4 GiB GPU memory. A startup measurement was
about 2.33 GiB trainer RSS and under 1 GiB GPU allocation; these are laptop
measurements, not Android measurements. Abort/investigate on OOM, nonfinite
loss, failure to advance, or exceeding the exploration budget. Final admission
still requires vocabulary accuracy at least 99% with no WER or term regression,
AMI-dev non-regression, and later comparison with the pinned V5 product model.
No evaluation result exists yet for this run.

## Automated vocabulary-clean experiment — completed, rejected

The new run was launched at 23:21 IST on 2026-09-30 from the pristine cached
OpenAI Whisper-small base. It uses the meeting-isolated, uniform-weight AMI
train/dev manifests and audited synthetic vocabulary audio, with held-out
terms separated by term identity. The optimizer receives all 22,445 AMI train
rows and only 378 synthetic vocabulary rows from 63 training terms; 96
synthetic rows covering 16 terms are held out. AMI dev and the vocabulary
holdout are never training inputs. The recipe is 1,500 steps, batch 2,
gradient accumulation 8, learning rate 1e-5, and no augmentation. Twelve
focused preflight tests passed.

Training reached 1,500 steps and saved its adapter at
`~/.local/share/vaani/models/v6-stt-vocab-automated-20260930/training/adapter/`.
The original wrapper did not leave evaluation reports after the run was
interrupted, so the paired evaluations were resumed directly from that exact
adapter. Both base and candidate used beam 5, identical manifests, and CUDA.

On the 96-row term-disjoint synthetic holdout, base Whisper-small scored
5.4878% normalized WER and 97.92% protected-term accuracy; the candidate
scored 5.6402% WER and 93.75% protected-term accuracy. That is a 0.1524-point
WER regression and a 4.17-point protected-term drop. The 96 protected-term
occurrences meet the support minimum, but both quality gates fail. This suite
tests generalization to words absent from training; it does not establish
whether fine-tuning teaches the configured vocabulary.

On all 3,121 AMI dev rows, base scored 34.6903% normalized WER and 33.33%
protected-term accuracy across 9 occurrences; the candidate scored 26.0341%
WER and 22.22% protected-term accuracy. WER improved by 8.6562 points, but
protected-term accuracy dropped 11.11 points, so the AMI gate also fails.
The candidate is rejected and cannot be exported, installed, or promoted.
Aggregate-only reports are in the same private run directory; no hypotheses
or transcripts are included in the reports. No row-by-row human review was
used or requested.

The experiment also exposed a benchmark mismatch: a term-disjoint holdout
grades vocabulary recognition on words intentionally excluded from training.
That remains useful as a transfer diagnostic, but the next candidate is
measured on known vocabulary terms in held-out sentence contexts. The splitter
and training wrapper now support `seen-term-context`; it deterministically
holds out one sentence frame for each term while keeping every term in train.
The original `term-disjoint` strategy remains available. The promotion gate
was corrected too: a fixed +5-point accuracy gain is not a valid target when
the base already scores 97.92%. Vocabulary promotion now requires at least
99% protected-term accuracy, no WER or protected-term regression, and at least
50 term occurrences. This fixes the evaluation design, not the rejected model;
a new run still has to pass these gates, full AMI dev, and eventual paired V5
qualification.

## Clean-source AMI experiment — diagnostic only

The fresh-base run completed 1,000 steps on 2026-09-28 and saved its adapter
under `~/.local/share/vaani/models/v6-stt-whisper-ami-clean-1000-20260927/`.
Keep it as a diagnostic experiment and do not promote it: the process loaded
the former collator before the end-token masking fix described below. Final
logged training loss was 17.54; loss is not an accuracy result.

The admissible fallback is a new LoRA adapter initialized from the cached
OpenAI Whisper-small checkpoint, not the V5 or V6 fused checkpoint, trained on
the approved AMI v1.6.2 CC BY 4.0 audio/reference pairs. The split is by whole
meeting (108 train / 15 dev / 16 test groups; 22,445 / 3,121 / 3,526 rows).
All 29,092 source WAV checksums were verified again. The clean training
manifest sets every sample weight to 1.0; it does not use V5 hypotheses to
select, weight, or label examples. The deterministic builder records this as
`weighting: uniform`.

This is a controlled acoustic-domain experiment, not yet the needed
Indian-English technical-vocabulary solution. A manifest-level scan against
the combined 79-term `acronyms` + `mobile-stt` packs found only three matching
clips (`URL`, `WER`, `CER`) in the 22,445 AMI training rows and none in the
3,121 dev or 3,526 test rows.
Re-run this aggregate-only audit on each corpus split with
`python3 tools/measure_v6_vocab_coverage.py --manifest PATH --packs acronyms mobile-stt`;
it records the manifest hash and term counts, never transcript text.
Do not claim it solved the user's LLM/“ants” case. The configured term list has
not yet been validated against an uncontaminated candidate. The CT2 runtime is
being changed to pass configured terms through faster-whisper's
`hotwords` decoder option rather than as transcript-like `initial_prompt`
text; its WER impact still needs measurement on the clean candidate.

An initial same-100-clips Hugging Face/Transformers diagnostic on the
meeting-isolated AMI test split (beam 5, no prompt) measured corpus-normalized
WER 16.9828% for untouched Whisper-small and 15.5375% for the adapter. The
adapter improved 27 clips, worsened 8, tied 65, and had higher mean per-clip
WER (51.70% vs 32.15%); 4 adapter rows versus 3 baseline rows exceeded 100%
row WER. This mixed, small-slice result is not a qualification gate and the
collator defect invalidates the adapter for promotion. Full held-out evaluation
must use a freshly trained corrected candidate. Do not use the old V5
checkpoint, Flux TTS examples, or models derived from them for comparisons.
Keep recognized text, user audio, and raw transcripts out of logs/reports.
Training loss is not an accuracy gate.

A corrected-collator AMI control was started from the original cached
Whisper-small base on 2026-09-28 at
`~/.local/share/vaani/models/v6-stt-whisper-ami-clean-eosfix-1000-20260928/`.
It used the same pre-split, uniform-weight AMI train set and 1,000-step recipe;
it completed all steps in about 48 minutes on 2026-09-28. The final logged
training loss was 16.7611; this is not an accuracy result. Its adapter is
saved at `~/.local/share/vaani/models/v6-stt-whisper-ami-clean-eosfix-1000-20260928/adapter/`.
The merged Linux CT2 export is at
`~/.local/share/vaani/models/v6-stt-whisper-ami-clean-eosfix-1000-20260928-export/`;
its `model.bin` SHA-256 is
`83613e000a4413fab1a41fda481bf8cd1d67b7ef4408f56fc8cb5df0aa621e15`.
This EOS-corrected, fresh-base AMI run is still diagnostic and cannot qualify
Indian-English technical vocabulary. Vaani remains on its existing model.

A preliminary same-row comparison has since completed on the first 100 rows
of the frozen AMI dev manifest (not a representative or qualification slice),
with Linux CT2 int8 CPU decoding, English, beam 5, and no hotwords. Untouched
Whisper-small scored 19.4005% normalized WER; the corrected candidate scored
17.4854% on the identical rows, a 1.9151-point reduction. Candidate/base RTF
was 0.352 / 0.323. Both decoded all 100 rows; this slice contains zero
protected vocabulary terms, so it says nothing about technical-term recall.
The local CT2 CUDA attempt failed at runtime because the host lacks the
`libcublas.so.12` dependency; the CPU comparison is valid but preliminary.
The aggregate evaluator now aborts if every row fails to decode instead of
writing a misleading 0% WER report; a regression test covers this case.
Full dev qualification and the single frozen Monsoon evaluation remain undone.
The aggregate-only reports are retained outside Git as
`~/.local/share/vaani/models/v6-stt-whisper-clean-base-ct2-int8/ami-dev-first100-cpu.json`
and
`~/.local/share/vaani/models/v6-stt-whisper-ami-clean-eosfix-1000-20260928-export/ami-dev-first100-cpu.json`.

The VoiceArena Monsoon public test split is staged separately at
`~/.local/share/vaani/v6-data/eval/monsoon-public-test-20260928/` from its
fixed CC BY 4.0 revision. It contains 2,102 audio/reference rows (5.624 h);
the aggregate manifest SHA-256 is
`27532276684372c79febcc1c1ba7a7bca84eda9ae6e31d93804c194522b9a0ca`. All
audio hashes and container metadata validated, the staged row schema contains
no speaker/demographic/device fields, and the temporary Hub cache was removed.
No model has been scored against this set yet; reserve it for one evaluation
after candidate and decoder settings are frozen.

The automatic post-qualification entry point is
`pipelines/stt/qualify-v6-monsoon.sh`. It verifies the frozen manifest and
provenance hashes, runs base and candidate with the same CT2 decoder settings,
compares aggregate-only WER, and records an immutable one-shot claim/receipt
beside the local manifest. Once a candidate is scored, a different checkpoint
cannot consume the same public test. The comparer requires an explicit
`--allow-model-mismatch` for this V5-vs-V6 use while still enforcing identical
manifest, selected rows, and decoder settings.

The following is a post-qualification recipe for a future candidate. Do not run
it with the rejected 2026-09-30 adapter. Only after a candidate passes the
known-term/context, AMI-dev, and V5 comparison gates should it be merged/exported
and evaluated exactly once:

```sh
python3 tools/export_v6_stt_ct2.py \
  --model /home/saptodeep/.cache/huggingface/hub/models--openai--whisper-small/snapshots/973afd24965f72e36ca33b3055d56a652f456b4d \
  --adapter /home/saptodeep/.local/share/vaani/models/v6-stt-vocab-automated-20260930/training/adapter \
  --out-root /home/saptodeep/.local/share/vaani/models/v6-stt-vocab-automated-20260930/ct2-export
pipelines/stt/qualify-v6-monsoon.sh \
  --base-ct2 /home/saptodeep/.local/share/vaani/models/v5-stt-whisper-v5-supervised-200-ct2 \
  --candidate-ct2 /home/saptodeep/.local/share/vaani/models/v6-stt-vocab-automated-20260930/ct2-export/ct2-int8-float16 \
  --manifest /home/saptodeep/.local/share/vaani/v6-data/eval/monsoon-public-test-20260928/manifest.jsonl \
  --out /home/saptodeep/.local/share/vaani/models/v6-stt-vocab-automated-20260930/monsoon-once \
  --device cpu --beam-size 5
```

The CPU setting is deliberate: the local CTranslate2 CUDA path previously
failed because `libcublas.so.12` was unavailable. This test is not run on an
unqualified candidate and its public-set result is never fed back into tuning.
The one-shot base is the configured V5 supervised-200 CTranslate2 model, not untouched
Whisper-small; that makes this the required paired V5-versus-V6 product
comparison. Earlier clean-base comparisons remain training diagnostics only.
The qualification script pins the current deployed V5 directory hash
`73f73065f95036f184910da576d0ca66ab5a1ef62f077d8dfbe8a029c59d5427` and
refuses to spend the one-shot public test on a different base artifact.
This pin was corrected on 2026-10-04 after checking the actual `v5` resolver
and the configured recognition model: the earlier Cozy pin was stale. No
public-test decode or claim was performed during this correction.

The Android path remains a separate follow-up: export the clean merged HF
checkpoint to a whisper.cpp-compatible model, quantize, and verify conversion
sane-ness, WER, Indian-English/Hinglish behavior, timestamps, memory, and
latency on actual Android hardware. Do not replace Android's existing base
model until those gates pass. On 2026-09-30, `adb devices -l` showed an
x86_64 emulator (`emulator-5554`), but no physical arm64 phone; JVM unit tests
do not establish native-model accuracy or phone resource use. The official
whisper.cpp model guide documents
`models/convert-h5-to-ggml.py` for Hugging Face fine-tuned Whisper checkpoints,
and its Android example consumes whisper.cpp model artifacts; this is the
appropriate portability route after merging the HF/PEFT checkpoint, not
passing a CTranslate2 directory to whisper.cpp. Sources checked 2026-09-29:
[fine-tuned model conversion guide](https://github.com/ggml-org/whisper.cpp/blob/master/models/README.md)
and [Android example](https://github.com/ggml-org/whisper.cpp/tree/master/examples/whisper.android).
Real-phone memory, latency, and behavior remain unverified.

#### Automated Vaani English corpus intake (prepared, gated)

The official Vaani transcription-part English configuration is a promising
Indian-English supplement: 15,075 train, 1,787 validation, and 1,519 test
clips (18,381 total; about 22.85 hours), CC BY 4.0, pinned upstream revision
`d2acadff1ccce766d127c11b1a157251460dd68a`. Its access requires the user to
accept upstream terms; this workflow does not accept terms or download data
automatically. No Vaani clips have been acquired or included in the active
run. The importer `tools/import_v6_vaani_english.py` is ready for after
authorized access and writes a minimized, hashed local manifest while
automatically rejecting malformed/duplicate rows; five offline tests pass.
It requires an explicit local `--terms-accepted` acknowledgment and existing
Hub authorization, and stores all artifacts outside Git. No per-row review
or approval queue is part of the intended pipeline.

The trainer and `pipelines/stt/train-evaluate-v6-vocab.sh` now accept repeated
`--manifest` / `--supplemental-train-manifest` arguments while preserving the
existing single-manifest invocation. This only makes separately audited
training sources composable; the Vaani corpus is not yet in any run. Repeated
`--supplemental-dev-manifest` arguments add paired base/candidate decoding and
an aggregate WER non-regression gate for each additional domain, without
making its samples training inputs. Keep the official validation split for
that aggregate gate and its test split sealed for a one-time final check. The
corpus does not expose a speaker ID or word-level timestamps, so
speaker-disjoint claims and word timing metadata must not be inferred from it. See
[`V6_DATASET_AUDIT.md`](V6_DATASET_AUDIT.md) for the source assessment.

#### Host-only export smoke (2026-09-29)

The official converter and whisper.cpp CPU tools were built from a temporary
upstream checkout. The corrected-collator AMI EOS-fix merged HF checkpoint
(already rejected by its full AMI dev gate) converted to a 466 MiB GGML model
and a 168 MiB Q5_0 model. Untouched Whisper-small converted and quantized to
the same sizes. Both Q5_0 files loaded and decoded the same first frozen
Monsoon clip through whisper.cpp with zero decode failures; the one-clip WER
was 0% for both. This is only a format/load smoke, not a numerical-equivalence
or accuracy qualification. Host CPU RTF was about 2.2 for that 1.5-second clip;
it is not an Android latency measurement. Models and aggregate reports are
kept outside Git under `~/.local/share/vaani/models/` in
`v6-whispercpp-ami-eosfix-research-20260929/` and
`v6-whispercpp-base-research-20260929/`. The EOS-fix adapter remains rejected,
no Android artifact was installed, and the current 1,500-step vocab-clean
adapter still needs its own export plus a full matched mobile-format test.

The installed Android dependency (`dev.ffmpegkit-maintained:whisper-android:1.0.0`)
was checked from its cached AAR: `WhisperConfig` exposes language, translate,
threads, maximum segment length, and timestamp printing, but no initial prompt
or hotword field. Android's `PersonalizationStore` currently renders explicit
user aliases after recognition/formatting; it does not bias Whisper decoding.
Do not report Android vocabulary as decoder-biased until the runtime is changed
and measured. A prompt-capable wrapper or a verified native whisper.cpp API is
needed for equivalent contextual biasing.

The host whisper.cpp export evaluator accepts optional per-row
`challenge_terms` and `challenge_tags`; it reports aggregate protected-term
recall and normalized WER by challenge tag without serializing the term
strings, references, hypotheses, or per-row errors. Use these for the
technical-token and edge-case suites; keep both speaker-separated from
training and record their provenance and audio source.

For the Linux production decoder, `tools/eval_v6_linux_ct2.py` evaluates a
faster-whisper/CT2 artifact on the same frozen JSONL shape (AMI rows may use
`audio_path`/`reference`; challenge rows may use `audio.ref` and
`utterance.reference_transcript`). It reports corpus/tag WER, protected-term
recall, latency, and hashes only; it does not write per-row metrics or any
transcript/hypothesis. Run after training, once with decoder hotwords disabled
and once with a frozen vocabulary file, using the same manifest and beam:

```sh
python3 tools/eval_v6_linux_ct2.py \
  --manifest /path/to/frozen-heldout.jsonl \
  --model /path/to/ct2-model \
  --report /path/to/aggregate.json \
  --limit 0 --device cuda --beam-size 5
python3 tools/eval_v6_linux_ct2.py \
  --manifest /path/to/frozen-heldout.jsonl \
  --model /path/to/ct2-model \
  --hotwords-file models/vocabulary/mobile-stt.txt \
  --report /path/to/aggregate-hotwords.json \
  --limit 0 --device cuda --beam-size 5
```

Keep report files and all dataset/audio artifacts in the ignored user-local
workspace. The hotword comparison is decoder evidence, not evidence that
training improved the vocabulary.

### Real-speech hotword diagnostic — 2026-10-04

The first human-speech decoder-context check used the same first 32 rows of
the frozen AMI dev manifest and the exact local V5 CT2 artifact, English,
beam 5, CPU int8. With no hotwords, normalized WER was 17.9028% (0 decode
failures, CPU RTF 0.3266). With the global `mobile-stt.txt` pack enabled, WER
was 25.5754% (0 failures, CPU RTF 0.4620), a 7.6726-point regression. None of
the 41 vocabulary entries occurred in the 32 references, so this measured the
irrelevant-hints case, not the pack's ability to fix a relevant name. It does
show that blindly applying the whole technical pack can hurt ordinary speech.
Keep vocabulary prompting opt-in or
relevance-bounded, and evaluate relevant-term hits plus false substitutions
on human speech before adopting it. This is a 32-row diagnostic, not a
promotion gate; the paired aggregate reports, including identical row-set and
model hashes, remain outside Git under
`~/.local/share/vaani/v6-data/hotword-ami-dev-20261004/`.

The initial CUDA run could not decode because the evaluation environment's
CTranslate2 backend requires `libcublas.so.12` while the default host search
path exposes CUDA 13's `libcublas.so.13`; the diagnostic was therefore run on CPU. The evaluator
now records aggregate exception-class counts (not exception messages) so
backend failures remain diagnosable without risking content disclosure.

A later check found an existing compatible CUDA 12 library directory at
`/usr/local/lib/ollama/cuda_v12`. Setting `LD_LIBRARY_PATH` for the evaluator
process only enabled a successful real-audio GPU smoke test; no system
libraries were installed or changed. A full paired ICSI-dev GPU comparison
is running with English, beam 5, `int8_float16`, identical model/row/scoring
vocabulary hashes, and the engineering pack off/on. Training remains paused.
The completed CPU baseline covered all 861 rows (34 minutes of human speech),
with 13.1569% WER, no failures, and 2/5 relevant term-row hits. Five supported
term-row pairs are too few for a broad vocabulary-quality claim. The GPU
result must be compared only with the matching GPU baseline, not this CPU run.

The paired GPU run subsequently completed all 861 rows with zero failures.
No-hint WER was 13.1820%; broad engineering hints gave 13.9596%, a 0.7776-point
regression. Relevant term-row hits increased from 2/5 to 3/5, which does not
offset the ordinary-speech cost and is far too little support for a vocabulary
claim. Decode time was 172.862 seconds without hints and 190.220 seconds with
hints (RTF 0.08482 and 0.09334). The paired comparator rejected promotion.
The hinted report recorded four false vocabulary term-row hits across 856
ordinary-speech rows; the earlier baseline did not yet emit that new metric,
so no causal false-hit increase can be claimed from this pair. Reports remain
outside Git under `~/.local/share/vaani/v6-data/hotword-icsi-dev-20261004/`.

The evaluator now reports separate relevant-term and ordinary-speech WER
slices, plus counts of vocabulary terms present in hypotheses but absent in
their references. These are term-row presence counts, not repeated acoustic
occurrence counts, and are diagnostics rather than proof of hallucination.
All output remains aggregate-only. Any partial decode failure writes a
diagnostic report but exits nonzero; paired comparisons reject it. Scoring
vocabulary hashes must match even when decoder-hotword differences are allowed.

## Self-authored vocabulary-audio pipeline

To close the AMI vocabulary gap without importing a source with uncertain
training terms, V6 has a local-only synthetic-audio path. It reads the curated
`acronyms` and `mobile-stt` packs, places each term in several
organization-authored spoken contexts, and synthesizes WAVs through the local
Kokoro artifact using multiple local voices. Each clip is recorded in an
ignored SQLite manifest with its audio checksum, term hash, voice, template
index, and synthetic provenance. The builder never prints target text or
writes it to a JSON report; it commits each completed clip so interruption is
safe. `tools/validate_v6_synthetic_vocab_audio.py` verifies WAV format,
duration, sample rate, checksum, and aggregate pack counts without exposing
the target strings.

The Whisper trainer accepts this SQLite source through `--sqlite-manifest` and
assigns its rows only the explicit `--sqlite-sample-weight`. A vocabulary
candidate must still be compared with the same clean AMI holdout and a
separate frozen technical-token benchmark; synthetic coverage is not evidence
of real-speaker accuracy or Indian-English generalization.

The current clean experiment starts from the original `openai/whisper-small`
checkpoint, not from a V5, Flux-derived, or previously rejected adapter. It
uses the meeting-isolated 22,445-row AMI train split plus 474 validated local
synthetic vocabulary clips at an explicit weight of 2, with streaming features,
no waveform augmentation, and the corrected EOS-preserving collator. It is an
experiment only: promotion requires the matched 3,121-row AMI comparison and
the frozen technical-token challenge after the artifact is complete.

The initial AMI diagnostic run and the corrected-collator control are complete.
A full 3,121-row Transformers evaluation of the corrected candidate completed
with 37.7591% corpus-normalized WER and 20.0% protected-term accuracy (2 of
10 reference term occurrences). The exact matched base evaluation completed
on the same 3,121 hashed rows with 34.6397% normalized WER and 30.0%
protected-term accuracy (3 of 10). The candidate regressed by 3.1194 WER
points and 10 protected-term-accuracy points, so the decision gate rejected
promotion. This resolves the conflict with the favorable 100-row CPU smoke
test: the larger, matched heldout set wins. Retain this adapter only as a
negative experiment; do not connect it to Vaani or use it as an initialization
base. The comparison gate proves matching row identities through a sorted
row-ID digest rather than comparing different model-output file checksums.

## Trainer correctness fix and next data phase

Whisper's tokenizer uses the end-of-transcript token as its pad token. The old
shared V5/V6 collator replaced every matching label ID with `-100`, so genuine
end-of-transcript targets were masked along with batch padding. The collator
now pads by sequence length and masks only newly-added positions. A focused
test confirms that a real EOS label is retained and only the shorter row's
extra batch position becomes `-100`. The active process cannot pick up this
source change; its checkpoint is exploratory and a promotion candidate must
be freshly trained with the corrected collator. Earlier Whisper LoRA
experiments that used this collator retain their measured artifacts and
metrics for traceability, but their adaptation did not explicitly train EOS;
do not treat the metric history as proof that the corrected trainer's model
will behave the same.

### Corrected 1,500-step vocabulary-clean candidate (2026-09-28)

A new fresh-base adapter completed 1,500 steps with the corrected
EOS-preserving collator, the 22,445 meeting-isolated AMI training rows, and
474 validated synthetic vocabulary clips at weight 2. It used streaming
features and no waveform augmentation. The saved adapter is outside Git at
`~/.local/share/vaani/models/v6-stt-whisper-ami-vocab-clean-20260928/checkpoint-1500/`.

On the full 3,121-row AMI dev split, same Transformers decoder settings
(English, beam 5, batch size 2), base Whisper-small measured 34.6903%
corpus-normalized WER and 30% protected-term accuracy; the adapter measured
32.9091% WER and 10% protected-term accuracy. The adapter improves aggregate
WER by 1.7812 percentage points but loses 20 points of protected-term
accuracy. The same-row aggregate gate therefore marks it ineligible. This is
development-set evidence only, not the final AMI test or an Indian-English
qualification; it does not prove V6 is better than production V5. Do not
promote or connect this adapter. Its final training loss (11.003) is not an
accuracy metric.

The comparison helper now reduces the evaluator's privacy-safe per-row JSONL
counts and verifies identical ordered row-ID digests and protected-term
denominators before computing a gate decision. It stores no transcript or
hypothesis. Each evaluator run also writes a small `.meta.json` sidecar with
hashes of its base checkpoint and optional adapter, plus the decoder settings
(the initial prompt is hashed, never stored). When those sidecars are present,
the comparator refuses to pair runs with different base weights or decoding
settings and records the candidate adapter hash in its aggregate result.
This closes the earlier gap where two reports could prove same-row pairing but
not model/decoder pairing. A regression test covers matching and mismatched
base provenance; old aggregate-only reports remain readable but explicitly
report model provenance as unverified.

The next corpus phase is the newly audited Mozilla Common Voice 26.0 South
Asian English release (112,099 validated clips, 166 hours, speaker-disjoint
train/dev/test) plus validated English Common Voice Spontaneous Speech 5.0
(2,474 clips, 8.39 validated hours) for disfluency exposure. Both are CC0 but
MDC requires the account owner to accept the release terms in its web UI before
API download; neither package is acquired yet. Preserve each official split,
exclude public test from training, record and verify archive SHA-256, and do
not re-host the source package. These sources still do not supply reliable
Indian-accent spontaneous-repair coverage or explicit rare technical-word
challenge labels, so the dedicated clean technical-token benchmark remains a
separate required gate.

Build the meeting-isolated manifests outside Git with:

```sh
python3 tools/build_v6_stt_manifest.py \
  --input ~/.local/share/vaani/v6-data/ami-v1.6.2/scale-50000/real-derived.approved.jsonl \
  --out-dir ~/.local/share/vaani/v6-data/stt-training/ami-v1.6.2-clean \
  --weighting uniform
```

Audio, transcripts, features, weights, and model caches stay outside Git.

## Automated unseen-term experiment update (2026-09-30)

The existing 474-row self-authored Kokoro vocabulary source was revalidated:
474 audio checksums passed, covering 79 terms, two voices, and three templates.
`tools/split_v6_synthetic_vocab.py` now deterministically holds out entire
terms before a fresh training run and writes only aggregate hashes/counts to
stdout. Its current local split contains 378 training clips over 63 terms and
96 evaluation clips over 16 entirely held-out terms. The transcript-bearing
split is local scratch only at
`/tmp/vaani-v6-vocab-term-split-20260930/`; it is not a model-quality result
for the prior 1,500-step adapter, which trained on all 79 terms.

An aggregate-only CPU diagnostic compared the untouched Whisper-small CT2
model on those same 96 synthetic clips, first without vocabulary context and
then with both `acronyms.txt` and `mobile-stt.txt` supplied as faster-whisper
hotwords. No decode failed, and both runs used the same model and ordered row
IDs:

| Decoder | WER | Held-out term accuracy | CPU RTF |
| --- | ---: | ---: | ---: |
| No hotwords | 9.5611% | 84.375% (81/96) | 1.9289 |
| Both vocabulary packs | 5.9561% | 96.875% (93/96) | 1.7693 |

This controlled result shows that decoder-side vocabulary context helped on
locally synthesized speech: WER fell by 3.6050 points and term accuracy rose
by 12.5 points. It is not human-speech, Indian-accent, V5, or Android evidence;
do not generalize these numbers beyond this TTS diagnostic. The evaluator now
accepts multiple vocabulary-pack files, deduplicates terms case-insensitively,
and can count explicitly annotated challenge terms without writing them to
the report. The aggregate comparator confirmed identical model hash, manifest,
and ordered row-ID digest and passed its diagnostic gate (minimum +5 protected-
term points with no WER regression). The comparison report is local-only at
`/tmp/vaani-v6-vocab-term-split-20260930/comparison-hotwords.json`.

Historical preflight note (superseded by the active run above): an earlier
invocation attempt on 2026-09-30 found CUDA unavailable and exited before
creating outputs. The later run started successfully after CUDA became
available. The documented
`/home/saptodeep/Projects/Cozy/stt-finetune/data/cv_indian_full/` corpus was
absent at the audit check and remains excluded pending exact license and
provenance evidence.

The wrapper now checks `torch.cuda.is_available()` before creating its output
directory or term split. A real invocation with the cached clean Whisper-small
base and the local AMI/SQLite manifests exited with code 69 and the message
that CUDA was unavailable; the requested output path remained absent. This
prevents a blocked run from leaving misleading partial artifacts. Its focused
split/comparison/CT2/collator regression suite passed 12 tests.

## Sampling-exposure audit and 2026-10-02 candidate

The V6 wrapper now runs `tools/audit_v6_stt_sampling.py` before optimization
whenever SQLite sampling fractions are configured. It reads only aggregate
SQLite counts and term hashes, stores an aggregate-only exposure report beside
the run, and warns when the expected draws per term are below three or fewer
than 80% of terms are expected to appear at least once. This is a budget
diagnostic, not an accuracy guarantee or a training blocker.

The 2026-10-02 1,500-step run used a 5% SQLite source fraction. Its split had
316 training clips over 79 terms (four clips per term). That budget implies 75
expected synthetic draws, 0.95 draws per term, and only about 48.4/79 terms
(61.3%) expected to appear at least once. The candidate's context-held-out
vocabulary suite improved corpus-normalized WER from 11.67% to 6.64%, but
protected-term accuracy was only 73.46% (119/162), far below the 99% gate.
This underexposure is a plausible training-data cause, not proof of causation.

For a controlled follow-up, keep the clean base, 1,500 steps, manifests,
decoder, and held-out suites fixed, and compare a 20% vocabulary source share
against the 5% run. At 20%, the current balanced 79-term split predicts about
3.8 draws per term and 97.8% term coverage before training; the aggregate WER,
protected-term, AMI, and ICSI gates must still decide whether the tradeoff is
acceptable. Do not promote based on the sampling estimate or the synthetic
challenge alone.

The 20% follow-up started on 2026-10-02 from clean Whisper-small at
`~/.local/share/vaani/models/v6-stt-vocab-20pct-20261002/`. It reuses the
same 316/158 vocabulary partition, AMI train/dev manifests, ICSI-dev regression
suite, 1,500-step recipe, and decoder as the 5% run. All 21 focused preflight
tests passed; the exposure audit predicts 300 SQLite draws and 97.77% term
coverage. Training has begun on the local RTX 3050 laptop GPU. These are
sampling expectations only; there are no accuracy results yet.

The paired evaluation of the 5% candidate completed on 2026-10-02. On the
158-clip / 162-occurrence vocabulary context holdout, normalized WER improved
from 11.6698% to 6.6414%, and protected-term accuracy moved from 72.22%
(117/162) to 73.46% (119/162); this remains below the required 99% accuracy
gate. On all 3,121 AMI-dev clips, normalized WER improved from 34.6903% to
23.7206%, while protected-term accuracy fell from 33.33% (3/9) to 22.22%
(2/9). On the speaker-held-out 861-row ICSI-dev subset, normalized WER
improved from 15.7783% to 8.4284%, while protected-term accuracy fell from
63.79% (37/58) to 55.17% (32/58). Thus the candidate lowers WER on all three
suites, but misses the vocabulary accuracy requirement and regresses protected
terms on both independent speech suites; it is not eligible for promotion.

The paired AMI/ICSI passes were completed from the saved candidate after the
original wrapper exited before its final summary. Their aggregate-only
comparisons are `comparison-ami-dev.json` and
`comparison-supplemental-sqlite-dev-1.json` in the private run directory.
The 20% exposure follow-up remains a fresh-base experiment; do not continue
from this rejected 5% adapter.

### 2026-10-03 20% run: preliminary held-out result

The 1,500-step training run completed and saved its adapter. On the paired
158-clip / 162-protected-term context holdout, normalized WER improved from
11.6698% to 3.5104% (+8.1594 points), and protected-term accuracy rose from
72.22% (117/162) to 83.33% (135/162). This is a substantial held-out gain, but
it still misses the binding 99% vocabulary-accuracy gate and is not promotable.
The relaxed interim comparison is diagnostic only. The strict paired
vocabulary comparator has now been saved as `comparison-vocab-heldout.json`:
it confirms the +8.1594-point WER improvement but fails promotion because
83.33% term accuracy is below 99%. The original wrapper session later ended
before saving the candidate AMI result. On 2026-10-04 the saved adapter was
verified and the missing full AMI-dev candidate decode was relaunched. Full AMI
and ICSI paired comparisons have since completed; both still fail the
protected-term non-regression gate, as recorded below.

### Full paired evaluation of the 20% candidate — 2026-10-04

The candidate adapter was decoded over all 3,121 AMI dev examples using the
same clean Whisper-small base, beam 5, English decoding, and CUDA settings as
the baseline. Corpus-normalized WER improved from 34.6903% to 25.6326%, but
protected-term accuracy fell from 33.33% (3/9) to 22.22% (2/9), a decline of
11.11 percentage points. This is a broad WER gain accompanied by a clear
technical-term regression; the paired AMI gate fails.

The paired 861-row speaker-held-out ICSI dev evaluation likewise improved
corpus-normalized WER from 15.7783% to 11.4888%, while protected-term accuracy
fell from 63.79% (37/58) to 58.62% (34/58), a decline of 5.17 points. It also
fails the protected-term gate. Aggregate-only reports are
`comparison-ami-dev.json` and `comparison-supplemental-sqlite-dev-1.json` in
the private candidate directory. Taken with the 83.33% context-held-out term
accuracy (below the required 99%), the 20% candidate is rejected; do not export,
integrate, or promote it. Its adapter remains useful only as a diagnostic for
the next data/training iteration. No per-row hypotheses or term strings are
included in these reports.

A privacy-safe per-term diagnostic joined the 158 held-out rows by hashed row
ID and reported only hashed term IDs/counts. It confirms coverage for 79 terms
with two contexts per term; at least 12 terms were missed on both held-out
contexts by the candidate, and one more was missed on one of two. There were
25 rows with at least one missing protected token. This failure shape suggests
the next data intervention should add acoustic/phonetic and sentence-context
diversity for hard terms, rather than only raising aggregate sampling exposure.
Term strings and transcripts were not emitted by the diagnostic.

An aggregate sampler audit of the same 316-row / 79-term SQLite train split
estimates that 3,000 steps at a 20% SQLite share would draw about 600 examples
(7.59 draws per term; 99.95% expected term exposure). A 35% share adds 450
draws while raising expected term exposure only to 99.9998%. This supports
testing additional optimization at the existing 20% share before increasing
the synthetic fraction, but the choice remains conditional on the outstanding
AMI/ICSI regression results. Exposure is not accuracy evidence.

The evaluator now accepts `--language auto` and preserves Unicode letters and
combining marks during WER normalization; the existing default remains forced
English for exact comparability with this and prior runs. A speaker-held-out
Hindi/Hinglish evaluation still needs to be run before drawing any code-switch
conclusion.

### Expanded synthetic context pack — 2026-10-04

The current local-Kokoro vocabulary pack has 474 clips for 79 terms: three
fixed sentence frames, two American-English voices, four training clips per
term, and two held-out clips per term. The candidate learned from that data
raises seen-term/new-context accuracy to 83.33%, but term-hash aggregation
shows a long tail that is still missed consistently. The generator and splitter
now support 12 self-authored sentence frames, with deterministic context-held-
out splits that adapt to the templates actually present. With 79 terms and the
two existing voices, the expanded manifest will contain 1,896 clips: 22 train
clips and two held-out clips per term. The splitter retains support for legacy
three-frame manifests; pass protocol `v6-vocab-seen-term-context-v1` to reproduce
their original deterministic holdout choice.

This remains synthetic American-English acoustics, not Indian-accent or
spontaneous speech, and its frames are controlled coverage rather than natural
speech prevalence. The upstream [Kokoro-82M model card](https://huggingface.co/hexgrad/Kokoro-82M)
declares Apache-2.0; the [ONNX conversion project](https://github.com/thewh1teagle/kokoro-onnx)
is MIT, and the upstream [voice catalog](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
identifies the selected `af_sarah` and `am_adam` presets. The generator and split
tests pass. New rows store hash-only provenance for the exact ONNX model and
voice asset, plus runtime/package versions, template index, sample rate, and
speed; tests verify no local path or transcript is serialized and the builder's
help works without loading optional audio dependencies. The expanded audio
build is now running at low CPU priority in the bundled `venv-kokoro` outside
Git at `~/.local/share/vaani/v6-data/synthetic-vocab-context-v2-20261004/raw/`;
the first 661 of the expected 1,896 clips have been committed to its local
manifest. A partial integrity pass reports zero errors; splitting and complete
audio validation remain pending. The builder
now supports `--execution-provider auto|cuda|cpu` and records the actual ONNX
Runtime provider in hash-only provenance. An isolated ONNX Runtime 1.30 CUDA 13
environment successfully generated a 24-clip smoke pack (`CUDAExecutionProvider`)
without disturbing the active CPU build; this is a functionality check, not a
claimed throughput win.
