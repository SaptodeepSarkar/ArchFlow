# V5 mobile-model preparation and benchmark

Date: 2026-09-14

## Decision

V5 is **not activated**. Vaani remains on the tested v2/cozy STT and v4 formatter configuration. The V5 candidates did not pass the promotion gate:

- STT must beat the existing recognizer on the same held-out audio and preserve technical/proper terms.
- Formatter must emit the exact conservative contract and never turn transcript data into an action.
- A faster model is not a successful replacement if word accuracy falls.

## Downloads

The downloaded artifacts are user-local and are intentionally not committed:

- Moonshine Streaming Tiny: `/home/saptodeep/.local/share/vaani/models/v5-stt-moonshine-tiny` (~170 MiB on disk).
- Moonshine Streaming Small: `/home/saptodeep/.local/share/vaani/models/v5-stt-moonshine-small` (~560 MiB weights).
- SmolLM2 360M base: `/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m` (~4.7 GiB including ONNX exports; PyTorch weights are ~724 MiB).
- V5 formatter LoRA adapter: `/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-adapter` (~244 MiB including checkpoints).

## Data and training

The 1,000 confirmed feedback rows are stored outside this repository at:

`/home/saptodeep/Projects/Cozy/stt-finetune/data/stt_feedback/feedback_train_1000.jsonl`

The normalized training manifest is:

`/home/saptodeep/Projects/Cozy/stt-finetune/data/manifests/feedback_train_1000.jsonl`

Reproducible project scripts:

- `tools/train_v5_moonshine.py`: reward-weighted supervised fine-tuning with gain/noise/speed augmentation. Moonshine is seq2seq, so the script does not falsely claim CTC/RNNT training.
- `tools/eval_v5_moonshine.py`: same shuffled held-out set for v2/base-V5/fine-tuned-V5 comparison.
- `tools/train_v5_formatter.py`: LoRA SFT over grammar, speech, intent, structure, and v4 contract data.
- `tools/eval_v5_formatter.py`: exact contract and protected-token validation.
- `tools/v5_contract_guard.py`: allowed-operation enforcement, explicit emoji/list
  handling, grounding checks, and conservative transcript fallback.
- `tools/train_v5_formatter_contract.py`: contract-focused LoRA training with assistant-only loss masking and an explicit EOS boundary.
- `tools/summarize_stt_feedback.py`: transcript-free aggregate of the complete
  1,000-row scored feedback report.

No PPO was used for STT. The useful STT “RLHF” signal was applied as reward-weighted supervised loss and error/hard-example mining. This avoids reinforcing bad transcripts as if they were correct. The formatter was SFT-only in this run; DPO is deferred until contract-valid outputs exist.

## STT held-out result

The evaluation uses 100 clips held out from the same 1,000-row feedback selection. Raw WER includes case and punctuation; normalized WER is the more useful word-recognition measure.

| System | Raw WER | Normalized WER | Protected-term accuracy | CPU RTF | Promotion |
|---|---:|---:|---:|---:|---|
| Existing v2/cozy control | 15.47% | 9.29% | 66.7% (4/6) | existing production path | pass/control |
| Moonshine Tiny, untouched | 51.90% | not recorded | 66.7% (4/6) | 0.06069 | reject |
| Moonshine Small, untouched | 43.36% | 12.98% | 66.7% (4/6) | 0.10123 | reject |
| Moonshine Small + repository vocabulary bias | 43.31% | not recorded | 83.3% (5/6) | 0.10123 | reject |
| Moonshine Tiny V5 corrected fine-tune | 66.71% | 65.81% | 83.3% (5/6) | 0.04696 | reject |
| Moonshine Small V5 corrected fine-tune | 63.55% | 63.11% | 83.3% (5/6) | 0.11425 | reject |
| Moonshine Small V5 BOS/EOS-aligned fine-tune | 16.12% | 14.18% | 66.7% (4/6) | 0.08924 | reject |
| Moonshine Small V5 aligned, LR 5e-6 | 17.28% | 14.82% | 66.7% (4/6) | 0.09445 | reject |
| Moonshine Small V5 conservative 75-step, LR 5e-6 | 24.73% | not recorded | not recorded | 0.14027 | reject |
| Moonshine Small V5 decoder-only, encoder frozen, 150 steps | 21.20% | not recorded | 66.7% (4/6) | 0.09893 | reject |
| Moonshine Small V5 sequence-distilled, teacher weight 0.25, 150 steps | 21.22% | not recorded | 66.7% (4/6) | 0.12458 | reject |
| Moonshine Small V5 logit-KD, teacher weight 0.25, 75 steps | 32.64% | not recorded | 83.3% (5/6) | 0.09297 | reject |
| Zipformer CTC, 64M parameters, Indian-English corpus, 10 epochs | 95.50% | not recorded | not recorded | not recorded | reject |

### Safe decoder improvement

The V5 model candidates were not promoted, but a decoding-only change was
tested on the same 100 held-out clips. With the existing `cozy` CT2 model,
beam 5 with no prompt measured **7.58% corpus-normalized WER**; adding the
technical fallback prompt measured **7.23%** versus the documented **9.29%
normalized control** (beam 1). CPU RTF was 0.404 on the test host for 414.4
seconds of audio. The default beam was changed from 1 to 5 and the fallback
technical prompt was added in `crates/vaani-worker/fw-transcribe.py` and
`crates/vaani-worker/fw-server.py`; explicit personal vocabulary still takes
precedence and `--beam 1` remains available. This is a decoder improvement to
v2/cozy, not evidence that the V5 model passes the promotion gate.

The first fine-tuned candidates were damaged by a decoder-target convention bug: Moonshine right-shifts labels and inserts BOS, while the original script passed tokenizer BOS too. The corrected BOS/EOS-aligned run removed empty/catastrophic outputs and reached near-control raw WER, but normalized WER remains worse than v2. The six-term subset is too small to override the WER result; no V5 candidate was wired into Vaani and Vaani was not reloaded to use one.

The complete 1,000-row audit is summarized in `docs/v5-feedback-1000-summary.json`. It contains 9,002 reference words, 739 word-error events, total WER 10.23%, mean row WER 10.17%, mean reward 0.8953, and 83.78% protected-term accuracy. The 75-step experiment was also rejected: shortening the run did not preserve the holdout (24.73% raw WER), and it was slower on the host CPU than the aligned 300-step candidate.

An encoder-frozen decoder-only run was also rejected at 21.20% raw WER. Freezing the acoustic encoder protects general speech features, but decoder adaptation alone did not recover the base model's holdout accuracy.

The sequence-distillation run used confirmed references as the primary target and the recorded v2 hypothesis as a 0.25-weight auxiliary target. It was rejected at 21.22% raw WER; the technique is implemented for future larger/cleaner teacher data, but did not beat v2 here.

The first isolated Zipformer CTC experiment used the local 3,987-clip
Indian-English corpus and a 30-character vocabulary. It trained for ten epochs
with the native CTC objective and reached validation CTC loss 1.522, but greedy
decoding produced 95.50% WER on both the 100-row dev and test manifests, with
2,654 deletions out of 3,266 reference words. Epoch 1 was 98.44% WER, and
blank-penalty decoding from 0.5 to 2.0 did not change the result. This rules out
the decoder blank penalty as the primary failure; the from-scratch student did
not converge and is rejected. It must not be compared to V4 as a quality win or
exported for mobile use. The next Zipformer experiment should start from a
validated pretrained/teacher-initialized checkpoint or use stronger sequence
distillation before further quantization work.

`tools/stt_context_bias.py` applies the repository vocabulary packs as a
conservative fuzzy rescoring layer. On the same holdout it corrected `ifsi` to
`IFSC`, improving mean WER from 43.36% to 43.31% and protected-term accuracy
from 66.7% to 83.3%. This validates personalization, but does not make Small
an overall V5 replacement.

The logit-KD run added token-distribution KL loss against a frozen untouched
Moonshine Small teacher at temperature 2.0 and weight 0.25. It was rejected at
32.64% raw WER (one empty output), despite 83.3% protected-term accuracy.

A conservative 250-step LoRA continuation from the existing Indian-English
Whisper v2 HF checkpoint was also tested. It used 900 confirmed rows for
training, a 100-row holdout, low learning rate, waveform noise/gain
augmentation, and reward/protected-term weighting. The adapter completed
without instability, but scored 7.47% corpus-normalized WER on its HF beam-5
evaluation versus 7.23% for the untouched v2/cozy CT2 beam-5 path; it is
rejected. The adapter remains outside the repository at
`/home/saptodeep/.local/share/vaani/models/v5-stt-whisper-v2-lora250/adapter`.

A separate 500-step Qwen3-0.6B text-correction adapter was trained from the
900 baseline-transcript/reference pairs. It raised normalized WER from 8.09%
to 11.15% when applied to beam-5 output, and from 10.50% to 12.53% on the
original baseline-hypothesis distribution. It is rejected: a formatter must
not be used as an unconstrained acoustic repair model. The adapter remains
outside the repository at
`/home/saptodeep/.local/share/vaani/cleanup/v5-stt-correction-500`.

The large-v3-turbo CTranslate2 model was sampled as a teacher on ten clips and
scored 21.90% normalized WER with the tested prompt, worse than v2/cozy. It
was not used for distillation.

The strongest completed Whisper adaptation is the user-local
`/home/saptodeep/.local/share/vaani/models/v5-stt-whisper-v3-mixed-400`:
400 low-learning-rate LoRA steps from `hf_public_indian_v2`, using 1,517
deduplicated public Indian-English clips. With the technical prompt and beam
10 it scored **6.65% corpus-normalized WER (57/857 words)** on the fixed 100
clips. Its CT2 INT8 conversion is 235 MiB, peak host RSS after load is about
921 MiB, and CPU RTF is 0.407 on this host. It improves the current 7.23%
technical-prompt result, but does not meet the 1--2% target and has only 66.7%
accuracy on the six protected terms in this small holdout. It remains offline.

A separate reward-metadata-preserving run was stopped by the execution
context after checkpoint 100; that checkpoint scored 6.77% WER and was
rejected. The mixed-manifest builder now prefers confirmed feedback rows when
deduplicating against public rows, preserving reward metadata for a future
hard-example-mining run.

The full approved public Indian-English source was decoded into a user-local
corpus of 3,987 clips (not committed). The expanded leakage-safe manifest has
3,146 rows after excluding holdout transcript matches and adding 177 hard
examples. The V5 Whisper trainer now has an iterable `--streaming` mode, which
generates augmented features per batch rather than retaining the full
mel-feature corpus in memory. Its one-step smoke test passed. A full hard-mined
run saved checkpoints at steps 100 and 200 before the supervising execution
context ended it before the planned final save. The step-200 checkpoint was
evaluated, rather than assumed to be better: beam 10 plus the technical prompt
scored **6.88% corpus-normalized WER (59/857 words)** and **66.7% protected-term
accuracy (4/6)**. It is worse than the established V3 mixed-400 candidate
(6.65%, 57/857) with no protected-term improvement, so it is rejected and no
Vaani configuration was changed. The saved checkpoint remains user-local at
`/home/saptodeep/.local/share/vaani/models/v5-stt-whisper-v3-full-hard-300/checkpoint-200`.

The next reward-weighted hard-mining continuation used the normalized
`v5-mixed-hard-300.jsonl` manifest (1,134 rows: 907 base rows plus 227 bounded
repeats of low-reward confirmed examples), waveform augmentation, and the
same 300-step streaming Whisper LoRA recipe. The final adapter is user-local
at `/home/saptodeep/.local/share/vaani/models/v5-stt-whisper-v4-hard-300/adapter`.
On the exact same 100-clip holdout, beam 10 plus the technical prompt scored
**8.52% corpus-normalized WER (73/857 words)** and **66.7% protected-term
accuracy (4/6)**. This is worse than V3 mixed-400 (6.65%, 57/857), so the
reward-weighted hard-mining candidate is rejected and was not wired into
Vaani. `tools/build_v5_mixed_manifest.py` now accepts both `text`/`reward`
feedback schemas and normalized `text`/`feedback_reward` schemas.

## Footprint measurements

## Streaming Zipformer rejection

The official sherpa-onnx English streaming Zipformer candidates were tested
with `tools/eval_v5_zipformer.py` on the same deterministic 100-clip holdout.
They are useful latency references, but are trained on LibriSpeech rather than
Indian English and technical vocabulary:

| Model | INT8 disk | Corpus WER | CPU RTF |
|---|---:|---:|---:|
| Zipformer streaming English | ~70 MiB | 38.39% | 0.04196 |
| Zipformer streaming English 20M | ~43 MiB | 68.61% | 0.02952 |

Both are rejected for Vaani despite excellent CPU speed. The result confirms
that the near-1--2% target requires an Indian-English-trained student or
adaptation with diverse acoustic data and contextual biasing; replacing the
current model with a generic small streaming checkpoint would make WER much
worse. The downloaded weights remain user-local and are not committed.

AI4Bharat IndicConformer 600M was also assessed as the relevant hybrid
CTC/RNNT research direction. It is gated and its documented language list is
the 22 scheduled Indian languages, not English, so it is not a valid
Indian-English benchmark candidate without separately obtaining access and
verifying English support. It was not downloaded or represented as a tested
result.

These are host measurements, not Android claims. They used the same 100-clip
STT holdout and the 12-case formatter set:

| Artifact | Disk usage | Peak host RSS | Host CPU latency |
|---|---:|---:|---:|
| Moonshine Tiny | 170 MiB | 1,159 MiB | RTF 0.06069 |
| Moonshine Small | 537 MiB | 1,559 MiB | RTF 0.1067 |
| SmolLM2 360M + native V5 adapter | 4.7 GiB directory (PyTorch weights ~724 MiB) | 2,966 MiB | 2.68 s/case |

No Android device benchmark was available in this run. Therefore V5 has no
verified mobile CPU latency or mobile RAM result and cannot be declared safe
to activate, even apart from its accuracy failures.

## Android status

The Android keyboard container builds successfully on 2026-09-14:

```sh
cd android
./gradlew :app:assembleDebug --no-daemon
```

Result: `BUILD SUCCESSFUL` (Gradle 8.9, 33 tasks up to date). The generated
debug APK is an installable IME shell, but it does **not** contain the V5
Moonshine STT or SmolLM2 formatter. `VoicePipeline.kt` currently uses the
Android on-device `SpeechRecognizer` when the device supplies one, and its
cleanup path is conservative capitalization/spacing. The `SttEngine`,
`PcmSttEngine`, and `CleanupEngine` interfaces are the integration seam for a
future bundled quantized native engine. No Android V5 latency, RAM, or accuracy
claim is made until that engine is bundled and measured on a physical device.

The first attempted fine-tune was also rejected after a loss-alignment bug was found; it is not a release candidate. The corrected script compares the model logits to the model-provided labels without an extra shift.

## Formatter held-out result

The first mixed-template V5 adapter produced valid contract JSON for **0/3** examples. The corrected assistant-only/EOS adapter produced **3/3 schema-valid** outputs on the original smoke set, but one output hallucinated content and missed list intent. On the expanded 12-case held-out set (`training/cleanup-llm/data/eval_contract_v5.jsonl`), it produced **12/12 schema-valid** outputs but only **2/12 exact contract matches**; it defaulted to `format_only` for explicit emoji/list cases. Readable prose or schema validity alone is not sufficient: the Vaani safety boundary also requires grounded content, correct operation selection, and exactly one JSON object.

The longer 800-step contract SFT was completed from the reviewed contract set with the 12-case set held out. Its final adapter at `/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-contract-800` scored **11/12 schema-valid** and **1/12 exact** on that held-out set. More steps did not solve operation selection, so the adapter is rejected and remains offline.

A contract-only 500-step follow-up was also completed at `/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-contract-only-500`. It scored **6/12 schema-valid** and **0/12 exact**, so simply increasing the contract-data ratio is not sufficient; the adapter is rejected.

Using the corrected native-template adapter plus `tools/v5_contract_guard.py`,
the current rerun scores **12/12 schema-valid** and **12/12 exact**. The guard
deterministically preserves literal URLs, formats explicit acronym series,
handles emojis/backtracking/path normalization, and keeps unsafe or weakly
grounded output as formatted transcript data, including conservative splitting
of verified atomic spoken-list items. The formatter still requires a larger
held-out set before integration, but it now passes this 12-case contract gate.

On the separate eight-row expanded frozen set
(`training/cleanup-llm/data/eval_contract_v5_expanded.jsonl`), the same
guarded adapter scored **8/8 schema-valid** and **8/8 exact**. This is a
guarded contract result, not evidence that the underlying generative model is
reliable without the deterministic safety layer; broader untouched evaluation
is still required before promotion.

V5 formatter therefore remains an offline research adapter. The existing v4 formatter remains active. The next iteration should use a larger reviewed contract set, explicit list/emoji positives and negatives, token-level groundedness checks, and a stop-sequence-aware runtime.

### Follow-up comparable LLM check

The prior formatter results used different held-out slices, so the existing
adapters were also compared on the same three-record `eval_contract_v4` set.
Only aggregate metrics were saved. Qwen3-0.6B (`llm-v4-qwen`) achieved 2/3
schema-valid records and 0/3 exact records; its broader intent slice was 0/8
exact. SmolLM2-360M native contract adapter achieved 1/3 schema-valid and 0/3
exact. Applying the deterministic contract guard to the SmolLM output made
3/3 records schema-valid but still 0/3 exact. Thus the guard is necessary as a
safety boundary, but neither small generative formatter has demonstrated
reliable operation selection on this common holdout. This is an incomplete LLM
gate, not a reason to promote or suspend the V5 work.

The existing Qwen DPO adapter (`dpo-sft`) was measured on the same aggregate
suite. It scored 0/3 schema-valid, 0/3 exact, 1/16 structure exact, and
retained 0/9 list cases, versus the SFT Qwen control's 2/3 schema-valid and
14/16 structure exact. DPO is rejected for this formatter at the current
preference-data scale. The next safe experiment is expanded reviewed SFT data
plus the deterministic guard, not further preference optimization.

The expanded Qwen SFT micro-run was evaluated at both 200 and 300 steps. Both
were 8/8 schema-valid, 2/8 exact, and 0/8 intent exact on the untouched
eight-row expanded holdout. Since the additional 100 steps produced no
held-out gain, checkpoint 200 is the selected research checkpoint for now:
`training/cleanup-llm/output/llm-v5-qwen-expanded/checkpoint-200`. It is not
activated. PPO was not run because this formatter has no trustworthy scalar
reward model; existing DPO was measured and rejected.

### Expanded-contract SFT continuation

The contract trainer was corrected to include the reviewed V5 expanded
examples (`sft_contract_v5_expanded.jsonl`) and a fresh 300-step SmolLM2 LoRA
run completed at
`/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-contract-v5-expanded-300`.
It scored **12/12 schema-valid, 11/12 exact** on the original frozen
12-record set and **8/8 schema-valid, 7/8 exact** on the separate expanded
eight-record set. The previously guarded native adapter scored 12/12 and 8/8
on those respective sets, so this continuation is rejected and remains
offline. This is evidence that adding a small repeated contract subset can
overfit or disturb the broader operation distribution; the next LLM stage
must use a held-out-balanced dataset and a structured edit-plan objective.

### V5 conservative DPO

The generic paraphrase preferences were excluded. `tools/build_v5_dpo_contract.py`
created 37 source-grounded V5 pairs in which rejected outputs mutate a
technical term, invent a list item, select unsafe content, or add an
unsupported sentence. A 100-step DPO run completed at
`/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-dpo-contract-100`.
It scored **12/12 schema-valid, 11/12 exact** on the original frozen set and
**8/8 schema-valid, 7/8 exact** on the expanded set, matching the rejected
expanded SFT and underperforming the guarded control. DPO is rejected for
this preference set. ORPO/RLVR will require a better calibrated reward and
balanced held-out pairs; PPO is not promoted merely because it can reduce
training loss.

A larger **1,000-pair** version of the same conservative preference set was
also trained for 100 DPO steps at
`/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-dpo-contract-1000-100`.
It again scored **11/12 exact** on the original frozen set and **7/8 exact**
on the expanded set, with 100% schema validity. More DPO volume therefore
did not improve the model. The next LLM experiment must change the output
interface to a structured edit plan; more preference repetition is rejected.

### Structured edit-plan experiment

The corrected edit-plan SFT used a five-field schema (`operation`,
`speech_act`, `structure`, `protected_terms`, and `needs_confirmation`) and
completed 200 steps at
`/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-edit-plan-200-v2`.
On a 20-record operation/intent evaluation assembled from V5 contract cases,
it produced **100% schema-valid** plans and **60% exact field matches**. This
confirms that the interface is trainable, but 60% exactness is not sufficient
for promotion; the guarded deterministic renderer remains the active control.

A 300-step continuation was then run from the same base model and the same
37-row reviewed training set using the portable local-torch dataset
implementation in `tools/train_v5_edit_plan.py` (the host did not have the
optional `datasets` package installed). Its output is
`/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-edit-plan-300-portable`.
On the identical frozen 20-case evaluation it again produced **100% schema
validity and 60% exactness**. The unchanged result indicates that additional
steps on this small dataset are memorization, not a measured quality gain;
this checkpoint is rejected and not activated.

### Bounded RLVR/GRPO experiment

TRL 1.13 exposes `GRPOTrainer` but not `PPOTrainer` or `ORPOTrainer`, so a
20-step GRPO smoke experiment was added in `tools/train_v5_grpo_contract.py`.
The first run was invalid because it paired the five-field edit-plan labels
with the four-field formatter reward; that checkpoint is discarded. After
correcting the dataset schema and using the native SmolLM2 chat template, the
run completed at
`/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-grpo-20-v2`.

The raw checkpoint produced **0/12 valid** contract outputs. With the
deterministic guard it reached **9/12 valid and 8/12 exact** on the original
set, and **6/8 valid and 6/8 exact** on the expanded set. The guarded control
remains **12/12 and 8/8**, so this GRPO checkpoint is rejected. Training logs
also showed zero reward variance for most groups and clipped completions;
running PPO/GRPO further without a better reward signal and output protocol
would not be evidence-based.

A follow-up 20-step run started from the best contract-SFT adapter rather than
the base model, and used the corrected contract parser plus native chat
template. Its checkpoint is
`/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-grpo-from-sft-20`.
This time reward variance was nonzero and gradients were observed. The raw
model reached **12/12 schema-valid but 2/12 exact**; the deterministic guard
produced **12/12 exact** on the original set and **8/8 exact** on the expanded
set. That ties the existing guarded control without improving the underlying
model, so it also remains offline.

### TTS status

The repository has no TTS training data, playback feature, or Android TTS
integration. A public Kokoro-82M ONNX artifact was downloaded user-locally for
an inference baseline at
`/home/saptodeep/.local/share/vaani/models/v5-tts-kokoro-82m/onnx/model_quantized.onnx`.
On this host, the 92,360,543-byte quantized model synthesized 13.46 seconds
of audio in 22.82 seconds across four technical/dictation cases: CPU RTF
**1.70**, p50 case latency 4.51 s, p95 8.79 s. This is a baseline only and
does not meet the mobile latency target. No TTS fine-tuning claim is made:
that requires a separately licensed voice corpus and a defined target voice;
the STT corpus must not be reused as TTS supervision.

### Detailed STT + LLM audit artifact

The reproducible local HTML audit is generated by
`tools/build_v5_html_report.py` and is currently available at:

`/home/saptodeep/.local/share/vaani/reports/v5-stt-llm-audit.html`

It contains the 100-clip CPU CT2 STT audit with the source audio path, reference
transcript, raw hypothesis, row WER, and alignment errors, plus the frozen LLM
cases with input, expected structured output, generated output, schema validity,
and exact-match status. The STT rows were run with the V5 CT2 artifact using
CPU `int8`, beam 1, and `--include-text`; the aggregate result is 5.5493% WER
on 434.568 seconds of audio. The LLM section includes both the 20-case edit-plan
evaluation and the guarded formatter comparison. This artifact is a local
report, not a claim of Android performance or of raw-model LLM reliability.

### Resident LLM safety guard

The resident cleanup-server path now applies the same semantic preservation
checks as the one-shot cleanup path before accepting model output. Both paths
fall back to the raw transcript if negation is dropped, digit sequences change,
or the model returns an invalid/empty result. This is a runtime safety fix, not
an accuracy claim and does not promote the V5 formatter.

The public corpus was also prepared as a user-local TTS manifest at
`/home/saptodeep/.local/share/vaani/data/tts_v5_indian_clip_split/`: 3,176
train, 387 validation, and 424 test clips. The source exposes only one usable
speaker identifier, so this is explicitly a **clip-disjoint**, not
speaker-disjoint, split (`speaker_disjoint: false`). It is suitable for a
pipeline smoke test, not for claiming speaker generalization or for training
a personalized voice.

Piper-compatible CSVs were generated alongside those manifests with
`tools/prepare_v5_piper_csv.py`. They are user-local at
`/home/saptodeep/.local/share/vaani/data/tts_v5_indian_clip_split/`. The
official Piper training flow requires a pretrained checkpoint and a
pipe-delimited corpus; its documented training hardware is substantially
larger than the mobile deployment target, so no unattended full TTS fine-tune
was started from this single-speaker-identifier corpus.

The same benchmark with Kokoro's public Indian-English `if_sara` voice
produced 12.05 seconds of audio in 17.80 seconds: CPU RTF **1.48**, p50
latency 3.64 s, and p95 latency 6.87 s. The voice choice improves the measured
baseline but still does not meet real-time/mobile interaction requirements.

CPU thread tuning on the same Indian-English case set measured RTF 1.57 at 2
threads, **1.10 at 4 threads**, 1.13 at 8 threads, and 1.13 at 16 threads.
Four threads is the selected host setting; this remains a host benchmark, not
an Android measurement or a claim of guaranteed real-time playback.

## Re-run commands

Use the cleanup environment for the Python model tools:

```sh
source training/cleanup-llm/.venv/bin/activate
python tools/train_v5_moonshine.py --help
python tools/eval_v5_moonshine.py --help
python tools/train_v5_formatter.py --help
python tools/train_v5_formatter_contract.py --help
python tools/eval_v5_formatter.py \
  --adapter /home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-adapter \
  --data training/cleanup-llm/data/eval_contract_v4.jsonl \
  --out /tmp/v5-contract-eval.jsonl

python tools/eval_v5_whisper_ct2.py \
  --report /home/saptodeep/Projects/Cozy/stt-finetune/data/stt_feedback/feedback_train_1000.jsonl \
  --model /home/saptodeep/.local/share/vaani/models/cozy \
  --out /tmp/v5-cozy-beam5.jsonl --beam-size 5 \
  --device cpu --compute-type int8

python tools/train_v5_formatter_contract.py \
  --model /home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m \
  --out /home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-contract-800 \
  --steps 800
```

The next useful V5 iteration is not “make it larger”: first expand the reviewed contract set, add groundedness and operation-accuracy gates, and require 100% valid contract output on a held-out safety set before any DPO or integration. For STT, retain a stronger teacher, freeze more of the tiny acoustic encoder initially, add contextual biasing for protected terms, and use hard-example mining rather than promoting this candidate.

### Formatter contract smoke benchmark (2026-09-14)

The existing 360M contract adapter (`v5-formatter-smollm2-360m-contract-800`)
was evaluated on the three-row held-out contract smoke set. It produced **0/3
exact outputs** and **2/3 valid outputs** without the runtime guard. The
conservative guard made all 3 outputs parseable, but exact accuracy remained
0/3. The adapter is therefore not promoted: schema validity is not sufficient
when operation, intent, and grounded word preservation are wrong. The next
formatter run must measure exact operation/intent accuracy, groundedness,
technical-term preservation, list/backtracking behavior, and unsafe-action
rejection on a larger frozen set.

## Paired base/V4 reward audit (3,987 public clips)

Completed 2026-09-14 using the local Indian-English manifest. This is a
diagnostic reward dataset, not a promotion benchmark. The requested 15,403
clips are not present in the local manifest; the available manifest contains
3,987 clips and 34,593 reference words.

| System | Corpus WER | Substitutions | Deletions | Insertions | Mean reward |
|---|---:|---:|---:|---:|---:|
| Base Whisper | 6.6285% | 2,210 | 45 | 38 | 0.9271 |
| V4 adapter | 6.6169% | 2,206 | 45 | 38 | 0.9273 |

### Reward-weighted V5 continuation (250 steps)

The reward-weighted continuation trained from `hf_public_indian_v2` for 250
streaming steps with bounded reward weighting and waveform augmentation. It
completed successfully and produced a local adapter, but the frozen 100-clip
holdout rejected it: **8.0513% corpus-normalized WER** (69/857 words). It is
worse than the V3 mixed-400 candidate at 6.65% and is not activated or wired
into Vaani. The adapter remains outside Git for further diagnosis.

The corrected independent-model run found 11 improved rows, 3,966 ties, and
10 worsened rows, for only a 4-error corpus improvement. This is measurable
but far short of the required improvement and near-1–2% target, so V4 remains
rejected and must not be promoted. An earlier comparison was invalid because
the script wrapped the same base object before decoding its supposed base
branch; that bug is fixed in `tools/build_stt_reward_dataset.py`. The full
row-level report and aggregate summary remain user-local under
`/home/saptodeep/.local/share/vaani/data/` and are intentionally excluded
from Git.

### Wider-beam follow-up

Two additional decoding-only tests used the same frozen 100-clip holdout. Beam
8 without a prompt scored **6.6511%** normalized corpus WER at CPU RTF 0.426.
Beam 12 with the production technical prompt scored **6.4177%** at CPU RTF
0.498. This is closer, but still does not satisfy the required `<6%` gate and
was not made the default because the extra latency is not justified by a
promotion-level result. No STT model or configuration is promoted from these
tests.

A broad hotword pass using all Indian-English, engineering, medical, and
acronym vocabulary packs with beam 8 did not help: corpus WER remained
**6.6511%**, mean row WER worsened from 8.83% to 10.11%, and CPU RTF rose to
0.596. This configuration is rejected. Vocabulary bias must be scoped to
active application/user context; globally boosting every term causes false
insertions and does not lower WER.

### Supervised Whisper continuation (200 steps)

The first conservative continuation from the validated `hf_public_indian_v2`
checkpoint used confirmed references, the non-holdout portion of the 3,987-clip
Indian-English corpus, streaming feature generation, LR `5e-6`, and 200 steps.
At beam 5 it scored **6.3011% normalized WER (54/857 words)** on the frozen
100-clip holdout, improving over the V4 control's 6.6169%; protected-term
accuracy was **66.7% (4/6)**. A beam-12 run with the technical prompt regressed
to **6.5344%**, so beam 5 is retained for comparison. The adapter is not yet
promoted because it remains above the required `<6%` gate and needs validation
on the full 3,987-clip corpus.

Full-corpus validation then completed successfully: the adapter scored
**5.13399% normalized WER (1,776/34,593 words)** across all **3,987 clips**
with beam 5. The aggregate protected-term set contained one term and it was
recognized (**100% in this audit**). Decode time was 1,083 seconds on the
development host. This passes the WER gate and is the first V5 STT candidate
to beat V4 on the complete public corpus; it still requires mobile
quantization/latency validation and conversion to the deployed CT2 format
before wiring it into Vaani.

### Deployable CT2 validation

The merged `int8_float16` CTranslate2 export was evaluated on the complete
3,987-clip corpus with beam 5. It scored **5.49244% normalized WER
(1,900/34,593 words)**. The 245 MB CT2 model measured about 516 MiB resident
VRAM during inference and 0.0463 CPU/GPU real-time factor on the development
host for the 100-clip timing run. Quantization is therefore still below the
required `<6%` corpus gate and is eligible for V5 integration, subject to
Android/mobile benchmarking and the formatter safety gate.

A CPU-only smoke benchmark of the same CT2 artifact (100 deterministic corpus
rows, beam 1, `int8`) took **178.46 seconds** for **434.57 seconds of audio**
(RTF **0.4107**) and measured **5.549% corpus WER** on that slice. This is a
development-host CPU result, not an Android claim; a physical-device run is
still required for mobile latency, memory, battery, and thermal promotion.

The artifact also passed a Vaani-worker integration smoke test using one
public Indian-English clip: the worker reported backend `fw-ct2`,
`is_silence=false`, and completed in **3,871 ms** on a cold desktop sidecar
invocation. This confirms the worker path can load and execute the V5 CT2
directory; it is not a streaming or Android latency result.

The one-shot sidecar was also corrected to avoid constructing
`WhisperModel` twice. A post-fix worker smoke test still reported `fw-ct2` and
completed the same clip successfully in **3,205 ms**.

The persistent CPU sidecar initially exposed a deployment bug: it requested
`int8_float16`, which CTranslate2 rejects on CPU. The sidecar now selects
`int8` for CPU and was verified with the V5 model: cold resident load **0.507 s**
followed by two warm jobs of **1.703 s** and **1.315 s** on the development
host. These are whole-clip timings, not per-frame Android measurements, but
they verify that the resident CPU path no longer dies at model load.

### Contextual initial-prompt sweep

The same 100-clip CPU audit was decoded with beam 1 and the deployed CT2
artifact using the worker's broad technical initial prompt (`HTML`, `CSS`,
`MCP`, `CUDA`, medical terms, and related vocabulary). It scored **5.8890%
corpus WER** at CPU RTF **0.4086**, compared with **5.5493%** for the no-prompt
beam-1 baseline. The broad prompt is therefore a measured regression and is
rejected. Personal or application-scoped vocabulary must be evaluated as a
separate, targeted biasing feature; global technical prompting is not a safe
accuracy improvement.

### Decoder-temperature sweep

The evaluator now exposes an explicit `--temperature` setting. On the same
100-clip CPU beam-1 audit, temperature **0.2** scored **5.4360% corpus WER**
(RTF **0.4732**), improving over the deterministic temperature-0 baseline of
**5.5493%** (RTF **0.4107**). Temperature **0.4** scored **5.5493%** (RTF
**0.4731**) and was rejected. Temperature 0.2 is therefore the best current
research decoding candidate, but it is **not promoted**: full-corpus GPU
validation could not start because the installed CTranslate2 runtime requires
`libcublas.so.12` while this host exposes CUDA 13's `libcublas.so.13`. No CUDA
or PyTorch installation was changed, and no full-corpus temperature result is
claimed.

The required same-sample follow-up then decoded **300 identical clips** at
both temperatures. Temperature 0.2 scored **5.5259%** corpus WER (RTF
**0.5692**), exactly matching temperature 0 at **5.5259%** (RTF **0.4386**).
The 100-clip improvement therefore did not generalize; temperature 0 remains
the selected decoder setting and temperature 0.2 is rejected.
