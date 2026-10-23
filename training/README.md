# V8 training — one command on a free Colab T4

Full fine-tunes of `openai/whisper-large-v3-turbo` (STT) and
`Qwen/Qwen2.5-1.5B-Instruct` (formatter), then CT2 int8 / GGUF Q4_K_M exports,
evals and `report.md`. Contract: `.research/full-finetune-small-models/03-run-contract.md`.

## Exact Colab sequence

```python
# 0. Runtime > Change runtime type > T4 GPU. One session, one GPU, nothing else.
!git clone https://github.com/SaptodeepSarkar/ArchFlow /content/Vaani
%cd /content/Vaani
```

```bash
# 1. deps + data (VAANI_DATA_URL = Drive id or https; sha256 verified when set)
export VAANI_DATA_URL='<drive-id-or-url>'
export VAANI_DATA_SHA256='<sha256 of the .tar.zst>'
bash training/bootstrap_colab.sh

# 2. real models, 20 steps each, ~15 min. Do this before a long run.
bash training/run_all.sh --smoke

# 3. the run. Stops itself 2 min before the session limit, exit 0, status resumable.
bash training/run_all.sh --full --session-limit-min 660
```

After a disconnect (or a second session), rerun **the same command** in a fresh
runtime: `bootstrap_colab.sh` re-downloads the data, `run_all.sh` reads
`$OUT/state.json` and continues at the saved step and stage.

## Expected time and VRAM (measured on a T4, `01-empirical.md`)

| stage | config | VRAM (reserved) | speed | 60 h / 20k pairs |
|---|---|---|---|---|
| STT | bs4 × accum 8, fp32 + fp16 autocast, 8-bit Adam | 7.6–8.6 GB | 2.5–3.0 s/micro-step | ~12 h per epoch, **~24 h for 2 epochs** |
| formatter | bs2 × accum 16, fp16 master, seq 512 | 11.5–12.1 GB | ~1.2 s/micro-step | **~3.5 h for 1 epoch** |
| STT averaging | 3 checkpoints, fp32 | ~4 GB | seconds | — |
| formatter averaging | 3 checkpoints, fp16 | ~9 GB | seconds | — |

So the frozen recipe (2 STT epochs) is **~28 h ≈ three 10–11 h sessions**, not
two. If you must fit two sessions, set `"epochs": 1` in
`training/configs/stt.json` (~12 h STT); the best-checkpoint rule still ships the
right model, since V7 overfit after ~1 epoch.

## What the run does

`run_all.sh`: STT → (VRAM freed, new process) formatter → exports → evals →
`$OUT/report.md`. Logs go to `$OUT/logs/*.log`, teed to stdout. Exit code is 0
for both "done" and "resumable"; `state.json` says which.

| file | role |
|---|---|
| `training/bootstrap_colab.sh` | apt deps (ffmpeg, tar, zstd), pip deps, gdown/curl download, sha256, unpack, row counts |
| `training/stt_train.py` | Whisper full FT, WER eval, checkpoints, top-3 average |
| `training/formatter_train.py` | Qwen2.5-1.5B full FT, EM eval, checkpoints, top-3 average |
| `training/common.py` | state, heartbeat, checkpoints, WSD, 8-bit Adam, frozen prompt |
| `training/eval_stt.py` | WER overall + per source |
| `training/eval_formatter.py` | EM, entity/number survival, token F0.5, over-edit, punctuation, intensity |
| `training/export_stt_ct2.py` | CTranslate2 `int8` |
| `training/export_formatter_gguf.sh` | GGUF `Q4_K_M`, llama.cpp tag **b11588** |
| `training/report.py` | `report.md` from state + eval JSON |
| `training/configs/*.json` | the recipe; the only source of hyperparameters |

## Resume, state, checkpoints

`$OUT/state.json` (atomic write, fsynced):

```json
{"stage": "stt", "status": "resumable", "step": 12000, "epoch": 1, "best": 0.0712,
 "updated_at": "...", "stages": {"stt": {...}, "formatter": {"status": "done", ...}}}
```

Checkpoints are `$OUT/<stage>/step-XXXXXX/{model.pt,optimizer.pt,meta.json}`.
`meta.json` carries `epoch`, `metric`, `metric_name`. Pruning keeps **last 1 +
best 2** (STT: WER lower is better, formatter: EM higher). `optimizer.pt` holds
`{"optimizer": ..., "grad_scaler": ...}` so the T4 autocast scale also resumes.

At the end of each stage the **top-3 checkpoints are averaged** (plain mean, no
EMA) and saved as a normal HF dir in `$OUT/<stage>/averaged/`, which is what the
exporters and evals load. Disk: ≤3 STT checkpoints × (3.2 GB + ~1.6 GB) ≈ 14 GB
of `/content`'s 75 GB.

Session limit: checked before every optimizer step; at `limit − 120 s` it saves,
writes `status: resumable`, exits 0. A heartbeat line
(`HEARTBEAT stage=stt step=120 loss=1.234 lr=1e-05 mem=8.2 elapsed=95s`) is
flushed every 15 s, which is also what keeps the Colab client from freezing.

## Failure recovery

| symptom | action |
|---|---|
| disconnect, quota reclaim | rerun `run_all.sh --full --session-limit-min 660`; it resumes from `state.json` |
| STT OOM with real-length labels | set `batch_size: 2, grad_accum: 16` in `configs/stt.json`, rerun; resume continues |
| formatter OOM | `batch_size: 1`; it was measured at 11.5 GB |
| `non-finite loss/grad, step skipped` | expected guard, not fatal. If the count in `average.json` (`skipped_steps`) is large, stop and lower `lr` to 2e-6 |
| fp16 divergence that skipping cannot fix | fallback (not implemented): fp32 weights + `torch.optim.Adafactor` at seq 512, or DeepSpeed ZeRO-2 with optimizer offload |
| export fails on `gguf` mismatch | the script installs `llama.cpp/gguf-py` from tag b11588; the pip `gguf` is too old |
| bad data (missing rows, 16 kHz) | `bootstrap_colab.sh` counts rows and `common.load_wav_16k` refuses non-16 kHz mono PCM16 |

## Exports and evals

- `$OUT/export/stt-ct2-int8/` — `ct2.converters.TransformersConverter(...).convert(quantization="int8")`,
  processor files copied alongside; `export.json` records source steps.
- `$OUT/export/formatter-q4_k_m.gguf` — `convert_hf_to_gguf.py --outtype f16` then
  `llama-quantize ... Q4_K_M`, both from tag b11588.
- `$OUT/eval/stt.json` — overall WER + `per_source`, plus `stt_predictions.jsonl`.
- `$OUT/eval/formatter.json` + `predictions.jsonl` — exact match (strict and
  normalised), protected/entity and number survival (numbers must match exactly,
  names may change case), precision-weighted token F0.5 (β=0.5), over-edit rate
  (input tokens the target keeps but the model changed), final-punctuation
  accuracy, intensity-marker survival (`!`, ALL-CAPS emphasis, profanity).
  Rule-6 `vocab` rows are prompted with the extra block exactly as the Rust
  `prompt()` builds it.
- Re-evaluate the **exported** artefacts before shipping; the checkpoint is not
  what runs.

## What is deliberately off

- **Packing** — `--pack` exists and runs (block-diagonal mask, per-segment
  position ids), but is **off by default**: the ACL 2025 result says packing can
  lose on a small model/small dataset and it changes the batch↔LR relation. Run
  a 500-step A/B first. It has only been exercised on CPU tiny models.
- **EMA** — no spare VRAM; top-3 checkpoint averaging gives the same free gain.
- **Distillation** — the contract puts "no LLM-written targets" in the data
  pipeline; the formatter trains on rule/template-regenerated human text.
- **FlashAttention-2** — T4 is SM75; SDPA is the only path. `bitsandbytes` and
  `flash-attn` are never built together.
- **LoRA/adapters** — full fine-tune only.
- **Chat-template tweaks** — the Qwen2.5 template is used as shipped. Only the
  system message is our prompt.
- **QAT** — neither CT2 int8 nor GGUF supports it cleanly; both quantise after.

## Local smoke (no model downloads)

```sh
bash training/smoke_test.sh
```

Builds `training/.venv` with CPU torch on first run, writes the 32 STT + 64
formatter fixtures, two tiny random models, then for each stage: forced session
limit → save step 0 → resume → 2 steps → eval → export `--dry-run`, plus one
packed formatter run. It asserts `state.json`, `averaged/`, eval JSON,
`predictions.jsonl` and `report.md`, and it `bash -n`s every script and
`py_compile`s every module. Everything runs offline (`HF_HUB_OFFLINE=1`).

## Decisions where the contract was silent

- `optimizer.pt` is a dict (`optimizer` + `grad_scaler`) rather than a bare
  optimizer state, so the fp16 scaler survives a reconnect.
- `state.json` keeps the contract's flat keys for the current stage and adds
  `stages{}` so `run_all.sh` can skip a finished stage.
- Averaging runs inside each trainer at stage end, so a resumed session always
  ends with a valid `averaged/` dir.
- `--smoke` means 20 steps, eval every 20, ≤8 eval clips, dry-run exports; it is
  the same code path as `--full`, only shorter.
- Eval generation does not force `language="en"`; Whisper's own prefix logic is
  used (forcing it needs a generation config a tiny smoke model does not have).
- Fixtures are committed: deterministic 2 s silence wavs plus the generator
  (`make_fixtures.py`).

## Known risks (not tested on a GPU here)

- The 2-epoch STT budget is ~24 h, i.e. three free sessions; the contract's
  12–14 h figure assumed one epoch.
- `--pack` has never been exercised on CUDA or on real data; it is opt-in.
- fp16-master formatter training was measured for 13 steps only; a long-run
  divergence is possible (guard + fallback above).
- Averaging 3 fp16 checkpoints peaks around 9 GB of RAM/VRAM; on an OOM, average
  fewer (`average.json` records which steps were used).
- CT2 int8 and GGUF Q4_K_M must be evaluated after export; numbers in
  `report.md` come from the pre-quantisation averaged model.
