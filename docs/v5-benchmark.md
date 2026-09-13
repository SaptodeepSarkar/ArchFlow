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
| Moonshine Tiny, untouched | 51.38% | 22.99% | 66.7% (4/6) | not recorded in this table | reject |
| Moonshine Small, untouched | 43.36% | 12.98% | 66.7% (4/6) | 0.10123 | reject |
| Moonshine Tiny V5 corrected fine-tune | 66.71% | 65.81% | 83.3% (5/6) | 0.04696 | reject |
| Moonshine Small V5 corrected fine-tune | 63.55% | 63.11% | 83.3% (5/6) | 0.11425 | reject |
| Moonshine Small V5 BOS/EOS-aligned fine-tune | 16.12% | 14.18% | 66.7% (4/6) | 0.08924 | reject |
| Moonshine Small V5 aligned, LR 5e-6 | 17.28% | 14.82% | 66.7% (4/6) | 0.09445 | reject |
| Moonshine Small V5 conservative 75-step, LR 5e-6 | 24.73% | not recorded | not recorded | 0.14027 | reject |
| Moonshine Small V5 decoder-only, encoder frozen, 150 steps | 21.20% | not recorded | 66.7% (4/6) | 0.09893 | reject |
| Moonshine Small V5 sequence-distilled, teacher weight 0.25, 150 steps | 21.22% | not recorded | 66.7% (4/6) | 0.12458 | reject |

The first fine-tuned candidates were damaged by a decoder-target convention bug: Moonshine right-shifts labels and inserts BOS, while the original script passed tokenizer BOS too. The corrected BOS/EOS-aligned run removed empty/catastrophic outputs and reached near-control raw WER, but normalized WER remains worse than v2. The six-term subset is too small to override the WER result; no V5 candidate was wired into Vaani and Vaani was not reloaded to use one.

The complete 1,000-row audit is summarized in `docs/v5-feedback-1000-summary.json`. It contains 9,002 reference words, 739 word-error events, total WER 10.23%, mean row WER 10.17%, mean reward 0.8953, and 83.78% protected-term accuracy. The 75-step experiment was also rejected: shortening the run did not preserve the holdout (24.73% raw WER), and it was slower on the host CPU than the aligned 300-step candidate.

An encoder-frozen decoder-only run was also rejected at 21.20% raw WER. Freezing the acoustic encoder protects general speech features, but decoder adaptation alone did not recover the base model's holdout accuracy.

The sequence-distillation run used confirmed references as the primary target and the recorded v2 hypothesis as a 0.25-weight auxiliary target. It was rejected at 21.22% raw WER; the technique is implemented for future larger/cleaner teacher data, but did not beat v2 here.

## Footprint measurements

These are host measurements, not Android claims. They used the same 100-clip
STT holdout and the 12-case formatter set:

| Artifact | Disk usage | Peak host RSS | Host CPU latency |
|---|---:|---:|---:|
| Moonshine Tiny | 170 MiB | not measured | not measured |
| Moonshine Small | 537 MiB | 1,559 MiB | RTF 0.1067 |
| SmolLM2 360M + native V5 adapter | 4.7 GiB directory (PyTorch weights ~724 MiB) | 2,966 MiB | 2.68 s/case |

No Android device benchmark was available in this run. Therefore V5 has no
verified mobile CPU latency or mobile RAM result and cannot be declared safe
to activate, even apart from its accuracy failures.

The first attempted fine-tune was also rejected after a loss-alignment bug was found; it is not a release candidate. The corrected script compares the model logits to the model-provided labels without an extra shift.

## Formatter held-out result

The first mixed-template V5 adapter produced valid contract JSON for **0/3** examples. The corrected assistant-only/EOS adapter produced **3/3 schema-valid** outputs on the original smoke set, but one output hallucinated content and missed list intent. On the expanded 12-case held-out set (`training/cleanup-llm/data/eval_contract_v5.jsonl`), it produced **12/12 schema-valid** outputs but only **2/12 exact contract matches**; it defaulted to `format_only` for explicit emoji/list cases. Readable prose or schema validity alone is not sufficient: the Vaani safety boundary also requires grounded content, correct operation selection, and exactly one JSON object.

The longer 800-step contract SFT was completed from the reviewed contract set with the 12-case set held out. Its final adapter at `/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-contract-800` scored **11/12 schema-valid** and **1/12 exact** on that held-out set. More steps did not solve operation selection, so the adapter is rejected and remains offline.

A contract-only 500-step follow-up was also completed at `/home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-contract-only-500`. It scored **6/12 schema-valid** and **0/12 exact**, so simply increasing the contract-data ratio is not sufficient; the adapter is rejected.

Using the corrected native-template adapter plus `tools/v5_contract_guard.py`, the same held-out set scores **12/12 schema-valid** and **3/12 exact**. The guard prevents action-like operation names and keeps unsafe or weakly grounded output as formatted transcript data, but the exact semantic score is still below the promotion gate.

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

python tools/train_v5_formatter_contract.py \
  --model /home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m \
  --out /home/saptodeep/.local/share/vaani/cleanup/v5-formatter-smollm2-360m-contract-800 \
  --steps 800
```

The next useful V5 iteration is not “make it larger”: first expand the reviewed contract set, add groundedness and operation-accuracy gates, and require 100% valid contract output on a held-out safety set before any DPO or integration. For STT, retain a stronger teacher, freeze more of the tiny acoustic encoder initially, add contextual biasing for protected terms, and use hard-example mining rather than promoting this candidate.
