#!/usr/bin/env python3
"""Hash-only provenance records for local synthetic STT vocabulary audio."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance_record(
    *,
    model_sha256: str,
    voice_asset_sha256: str,
    voice_id: str,
    template_index: int,
    sample_rate: int,
    runtime_version: str,
    package_version: str,
    execution_provider: str = "CPUExecutionProvider",
) -> str:
    """Serialize reproducibility metadata without source text or local paths."""
    return json.dumps({
        "schema_version": 1,
        "dataset_source": "organization-authored synthetic audio",
        "generator_version": "v6-synthetic-vocab-context-v2",
        "tts_engine": "kokoro-onnx",
        "tts_package_version": package_version,
        "onnxruntime_version": runtime_version,
        "execution_provider": execution_provider,
        "model_sha256": model_sha256,
        "voice_id": voice_id,
        "voice_asset_sha256": voice_asset_sha256,
        "template_set_version": "v2",
        "template_index": template_index,
        "sample_rate": sample_rate,
        "speed": 1.0,
    }, ensure_ascii=False, sort_keys=True)
