# Source me: source env.sh — keeps every byte inside training/cleanup-llm/
export HF_HOME="$PWD/.hf_cache"
export HF_HUB_DISABLE_PROGRESS_BARS=1
export TOKENIZERS_PARALLELISM=false

# --- dGPU priority: train on the RTX 3050, never fall back silently ---
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
export CUDA_DEVICE_ORDER=FASTEST_FIRST

# --- FULLY LOCAL: downloads happen once via scripts, never during training ---
export HF_HUB_OFFLINE=0
