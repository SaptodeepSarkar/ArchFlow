# Vaani cleanup-LLM finetune 🧹→✨

Teaches **Qwen3-0.6B** to turn raw dictation transcripts into sendable text:
grammar, punctuation (commas/full stops), lists/points formatting, spelling,
and light emotion cues — while never inventing facts. Serves Vaani's
`cleanup.mode = "clean"` endpoint via Ollama after GGUF export.

Hardware target: NVIDIA RTX 3050 6GB. Full fine-tuning does not fit;
**LoRA adapters** (like Cozy's STT recipe) carry the adaptation.

## Pipeline

| Stage | Script | What it does |
|---|---|---|
| 0. Setup | `source env.sh` + `.venv` | project-local HF cache; CUDA torch |
| 1. Base model | `scripts/download_model.py` | `Qwen/Qwen3-0.6B` snapshot (~1.2 GB) |
| 2. Grammar data | `scripts/build_grammar_data.py` | CoEdit instruction pairs (grammar/coherence) |
| 3. Speech data | `scripts/build_speech_data.py` | synthetic transcript→clean pairs: fillers, false starts, duplicates, punctuation, lists/points |
| 3b. Structure data | `scripts/build_structure_data.py` | LLM v1 formatting pairs: bullets, dotted bullets, numbers, titles, names, explicit emoji, no-invention controls |
| 4. SFT | `scripts/train_sft.py` | LoRA (r=32 q/v/o + mlp) on grammar + speech mixes; v1 continues `dpo-sft` with `--from-adapter dpo-sft --structure-repeat N --out-name llm-v1` |
| 5. Eval | `scripts/eval.py` | holdout: exact-edit checks + list-format checks |
| 6. DPO prefs | `scripts/mine_prefs.py` | SFT mistakes → chosen/rejected pairs (the practical RLHF) |
| 7. DPO | `scripts/train_dpo.py` | preference-tune the SFT adapter |
| 8. Export | `scripts/export_gguf.sh` + `ollama create` | Q8 GGUF → `vaani-cleanup:0.6b` for the endpoint |

PPO-style RLHF is intentionally deferred: DPO gives the preference signal at
a fraction of the memory (no reward/value nets beside the policy on 6 GB).

## Quickstart

```bash
cd training/cleanup-llm
uv venv .venv --python 3.11 --system-site-packages
uv pip install --python .venv/bin/python torch transformers accelerate peft trl datasets soundfile
source env.sh
.venv/bin/python scripts/download_model.py     # Qwen3-0.6B
.venv/bin/python scripts/build_grammar_data.py # CoEdit pairs
.venv/bin/python scripts/build_speech_data.py  # transcript pairs
.venv/bin/python scripts/build_structure_data.py  # LLM v1 formatting pairs
.venv/bin/python scripts/train_sft.py --steps 2000
.venv/bin/python scripts/train_sft.py --from-adapter dpo-sft --structure-repeat 200 --lr 1e-4 --steps 600 --out-name llm-v1
.venv/bin/python scripts/eval.py --tag llm-v1
.venv/bin/python scripts/mine_prefs.py         # from SFT mistakes
.venv/bin/python scripts/train_dpo.py
```

## Vaani wiring (after export)

```
cleanup.mode = "clean"
cleanup.endpoint = "http://localhost:11434"
VAANI_CLEAN_MODEL=vaani-cleanup:0.6b  # in the vaanid environment
```
