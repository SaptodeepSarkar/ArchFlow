# Vaani cleanup-LLM finetune 🧹→✨

Teaches **Qwen3-0.6B** to turn raw dictation transcripts into sendable text:
grammar, punctuation (commas/full stops), lists/points formatting, spelling,
and light emotion cues — while never inventing facts. LLM v1 additionally
learns source-grounded structure: bullets, dotted bullets, numbered sequences,
explicit titles, name capitalization, explicit emoji, and no-invention
controls. It serves Vaani's `cleanup.mode = "stream"` direct-torch path via
`scripts/vaani_inject.py`.

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
| 5. Eval | `scripts/eval.py` | holdout: exact edits, list-format retention, and no-invention checks |
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

## Vaani wiring (stream mode)

```toml
[cleanup]
mode = "stream"
model_path = "/home/saptodeep/Projects/ArchFlow/training/cleanup-llm/output/base-model"
adapter_path = "/home/saptodeep/Projects/ArchFlow/training/cleanup-llm/output/llm-v1"
python_path = "/home/saptodeep/.local/bin/vaani_inject.py"
word_threshold = 10
```

The base model stays frozen. Only the selected LoRA adapter changes behavior.

## LLM v1 acceptance snapshot

- Training mix: 43,518 grammar rows, speech replay, 114 structure rows repeated per epoch.
- Schedule: 600 steps from `dpo-sft` at 1e-4, then focused LoRA-only correction passes at 5e-5 (pronouns, emoji-as-decoration, item-number enumerations, lists in long utterances).
- Holdout: grammar 13/60, speech 1/1, structure 9/13, structure lists 7/7, no invented lists 1/1.
- Targeted checks passed for grocery lists, dotted lists, explicit emoji, names/pronouns, item-number sequences, and bare formatting commands.
