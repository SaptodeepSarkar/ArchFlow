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
- `tools/train_v5_formatter_contract.py`: contract-focused LoRA training with assistant-only loss masking and an explicit EOS boundary.

No PPO was used for STT. The useful STT “RLHF” signal was applied as reward-weighted supervised loss and error/hard-example mining. This avoids reinforcing bad transcripts as if they were correct. The formatter was SFT-only in this run; DPO is deferred until contract-valid outputs exist.

## STT held-out result

The evaluation uses 100 clips held out from the same 1,000-row feedback selection. Raw WER includes case and punctuation; normalized WER is the more useful word-recognition measure.

| System | Raw WER | Normalized WER | Protected-term accuracy | CPU RTF | Promotion |
|---|---:|---:|---:|---:|---|
| Existing v2/cozy control | 15.47% | 9.57% | 66.7% (4/6) | existing production path | pass/control |
| Moonshine Tiny, untouched | 51.38% | 22.99% | 66.7% (4/6) | not recorded in this table | reject |
| Moonshine V5 corrected fine-tune | 66.71% | 65.81% | 83.3% (5/6) | 0.04696 | reject |

The fine-tuned candidate is very fast on the development CPU and improved the six-term protected subset, but its overall word accuracy is unacceptable. The six-term subset is too small to override the WER result; it was not wired into Vaani and Vaani was not reloaded to use it.

The first attempted fine-tune was also rejected after a loss-alignment bug was found; it is not a release candidate. The corrected script compares the model logits to the model-provided labels without an extra shift.

## Formatter held-out result

The first mixed-template V5 adapter produced valid contract JSON for **0/3** examples. The corrected assistant-only/EOS adapter produced **3/3 schema-valid** outputs, but one output hallucinated content and missed list intent. A contract-heavy follow-up produced **2/3 schema-valid** outputs and still emitted an invalid list result. Readable prose or schema validity alone is not sufficient: the Vaani safety boundary also requires grounded content, correct operation selection, and exactly one JSON object.

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
```

The next useful V5 iteration is not “make it larger”: first expand the reviewed contract set, add groundedness and operation-accuracy gates, and require 100% valid contract output on a held-out safety set before any DPO or integration. For STT, retain a stronger teacher, freeze more of the tiny acoustic encoder initially, add contextual biasing for protected terms, and use hard-example mining rather than promoting this candidate.
