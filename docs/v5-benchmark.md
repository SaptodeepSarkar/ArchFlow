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

Using the corrected native-template adapter plus `tools/v5_contract_guard.py`, the same held-out set now scores **12/12 schema-valid** and **12/12 exact**. The guard prevents action-like operation names, handles explicit lists/emojis/backtracking/path normalization, and keeps unsafe or weakly grounded output as formatted transcript data. This passes the formatter contract gate, but V5 remains offline because the STT and Android-device gates still fail.

V5 formatter therefore remains an offline research adapter. The existing v4 formatter remains active. The next iteration should use a larger reviewed contract set, explicit list/emoji positives and negatives, token-level groundedness checks, and a stop-sequence-aware runtime.

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
