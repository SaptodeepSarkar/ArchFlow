#!/usr/bin/env python3
"""One-time: snapshot Qwen3-0.6B into output/base-model (local only)."""
import os

from huggingface_hub import snapshot_download

DEST = os.path.join(os.path.dirname(__file__), "..", "output", "base-model")

os.makedirs(DEST, exist_ok=True)
path = snapshot_download(
    repo_id="Qwen/Qwen3-0.6B",
    local_dir=DEST,
    local_dir_use_symlinks=False,
    ignore_patterns=["*.md", "*.pdf"],
)
print("base model at:", path)
