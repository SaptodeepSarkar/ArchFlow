#!/usr/bin/env python3
"""Export a qualified fused HF Whisper checkpoint to Android GGML artifacts.

This is a packaging/conversion step, not a quality qualification. It accepts
only a full Hugging Face Whisper checkpoint, a pinned clean whisper.cpp/OpenAI
Whisper checkout, and aggregate comparison reports whose gates all passed.
Audio, transcripts, and hypotheses are never included in output metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WHISPER_CPP_COMMIT = "a44e07845931421bb6f3447ce0010ed9dc76a118"
OPENAI_WHISPER_COMMIT = "86098128c0b4f24f0e2aa2994de830614b474227"
WEIGHT_PATTERNS = ("model.safetensors", "model-*.safetensors", "pytorch_model.bin",
                   "pytorch_model-*.bin")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_sha256(directory: Path, patterns: tuple[str, ...]) -> str:
    """Match eval_v5_whisper_adapter.py's aggregate artifact digest."""
    files = sorted({path for pattern in patterns for path in directory.glob(pattern)
                    if path.is_file()})
    if not files:
        raise ValueError(f"no model artifact files found under {directory}")
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def tokenizer_compatibility(tokenizer_path: Path) -> tuple[dict[str, int], dict[str, int]]:
    """Derive converter vocab files without adding or renumbering tokens."""
    data = json.loads(tokenizer_path.read_text(encoding="utf-8"))
    model = data.get("model")
    vocab = model.get("vocab") if isinstance(model, dict) else None
    added = data.get("added_tokens")
    if (not isinstance(model, dict) or model.get("type") != "BPE"
            or not isinstance(vocab, dict) or not isinstance(added, list)):
        raise ValueError("expected a Whisper BPE tokenizer with an added_tokens array")
    if not vocab or any(not isinstance(token, str) or type(token_id) is not int or token_id < 0
                        for token, token_id in vocab.items()):
        raise ValueError("tokenizer BPE vocabulary is empty or malformed")
    ids = list(vocab.values())
    if len(set(ids)) != len(ids) or set(ids) != set(range(len(ids))):
        raise ValueError("tokenizer BPE IDs must be unique and contiguous from zero")
    compat_added: dict[str, int] = {}
    all_ids = {token_id: token for token, token_id in vocab.items()}
    for entry in added:
        if (not isinstance(entry, dict) or not isinstance(entry.get("content"), str)
                or type(entry.get("id")) is not int or entry["id"] < 0):
            raise ValueError("tokenizer added-token entry is malformed")
        token, token_id = entry["content"], entry["id"]
        previous = all_ids.get(token_id)
        if previous is not None and previous != token:
            raise ValueError("added-token ID conflicts with a different BPE token")
        if token in compat_added and compat_added[token] != token_id:
            raise ValueError("added token maps to multiple IDs")
        compat_added[token] = token_id
        all_ids[token_id] = token
    if len(set(all_ids.values())) != len(all_ids):
        raise ValueError("tokenizer assigns one token string to multiple IDs")
    if set(all_ids) != set(range(max(all_ids) + 1)):
        raise ValueError("combined tokenizer IDs contain gaps")
    return vocab, compat_added


def checkpoint_files(checkpoint: Path) -> tuple[dict, list[Path], Path]:
    config_path = checkpoint / "config.json"
    tokenizer_path = checkpoint / "tokenizer.json"
    if not config_path.is_file() or not tokenizer_path.is_file():
        raise ValueError("checkpoint must contain config.json and tokenizer.json")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("checkpoint config must be a JSON object")
    architectures = config.get("architectures", [])
    if (config.get("model_type") != "whisper" or not isinstance(architectures, list)
            or "WhisperForConditionalGeneration" not in architectures):
        raise ValueError("input must be a full Hugging Face Whisper checkpoint")
    if int(config.get("num_mel_bins", 0)) != 80:
        raise ValueError("only the 80-bin Whisper architecture is supported")
    if (checkpoint / "adapter_config.json").exists() or (checkpoint / "model.bin").exists():
        raise ValueError("PEFT adapters and CTranslate2 directories must be fused/exported first")
    weights = sorted({path for pattern in WEIGHT_PATTERNS for path in checkpoint.glob(pattern)})
    if not weights:
        raise ValueError("checkpoint has no full model weight files")
    vocab, added_tokens = tokenizer_compatibility(tokenizer_path)
    token_ids = set(vocab.values()) | set(added_tokens.values())
    configured_vocab = config.get("vocab_size")
    if type(configured_vocab) is not int or configured_vocab != len(token_ids):
        raise ValueError("tokenizer IDs do not match the configured Whisper vocabulary size")
    return config, weights, tokenizer_path


def validate_adapter_base(adapter_config: dict, base_model: Path) -> None:
    """Require the PEFT adapter to identify the exact local HF base used at export."""
    declared_base = adapter_config.get("base_model_name_or_path")
    if not isinstance(declared_base, str) or not declared_base.strip():
        raise ValueError("adapter config must declare base_model_name_or_path")
    try:
        resolved_declared_base = Path(declared_base).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ValueError("adapter's declared base checkpoint is not available locally") from error
    if resolved_declared_base != base_model:
        raise ValueError("adapter was trained against a different base checkpoint")


def git_revision(root: Path, expected: str, label: str) -> str:
    if not (root / ".git").exists():
        raise ValueError(f"{label} source is not a Git checkout")
    revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              check=True, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                           check=True, capture_output=True, text=True).stdout
    if revision != expected:
        raise ValueError(f"{label} revision must be {expected}")
    if dirty:
        raise ValueError(f"{label} checkout must be clean")
    return revision


def validate_qualification_reports(
    paths: list[Path], base_sha256: str, adapter_sha256: str,
) -> list[dict[str, str]]:
    if not paths:
        raise ValueError("at least one passing aggregate qualification report is required")
    accepted = []
    suites: set[str] = set()
    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("qualification report must be a JSON object")
        suite = report.get("suite")
        if not isinstance(suite, str) or not suite.strip():
            raise ValueError("qualification report must name its evaluation suite")
        if suite in suites:
            raise ValueError(f"duplicate qualification suite: {suite}")
        if report.get("promotion_eligible") is not True:
            raise ValueError("every supplied qualification report must pass its promotion gate")
        if report.get("base_model_provenance_sha256") != base_sha256:
            raise ValueError("qualification report does not match the supplied base model")
        if report.get("candidate_adapter_sha256") != adapter_sha256:
            raise ValueError("qualification report does not match the supplied candidate adapter")
        suites.add(suite)
        accepted.append({"sha256": sha256_file(path), "name": path.name, "suite": suite})
    required_suites = {"vocab-heldout", "ami-dev"}
    missing_suites = required_suites - suites
    if missing_suites:
        raise ValueError(f"missing required qualification suites: {sorted(missing_suites)}")
    return accepted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-model", type=Path, required=True,
                        help="full Hugging Face Whisper base checkpoint")
    parser.add_argument("--adapter", type=Path, required=True,
                        help="the exact evaluated PEFT adapter; it is fused by this tool")
    parser.add_argument("--whisper-cpp", type=Path, required=True,
                        help="clean checkout at the documented tested commit")
    parser.add_argument("--openai-whisper", type=Path, required=True,
                        help="clean checkout providing whisper/assets/mel_filters.npz")
    parser.add_argument("--qualification-report", type=Path, action="append", required=True,
                        help="aggregate comparison report; repeat for every required gate")
    parser.add_argument("--out", type=Path, required=True,
                        help="new output directory outside the Git worktree")
    parser.add_argument("--python", default=sys.executable,
                        help="Python environment containing PyTorch, Transformers, and PEFT")
    parser.add_argument("--quantizer", type=Path,
                        help="defaults to <whisper-cpp>/build/bin/whisper-quantize")
    args = parser.parse_args()

    try:
        base_model = args.base_model.expanduser().resolve(strict=True)
        adapter = args.adapter.expanduser().resolve(strict=True)
        whisper_cpp = args.whisper_cpp.expanduser().resolve(strict=True)
        openai_whisper = args.openai_whisper.expanduser().resolve(strict=True)
        out = args.out.expanduser().resolve()
        if not base_model.is_dir() or not adapter.is_dir() or not whisper_cpp.is_dir() or not openai_whisper.is_dir():
            raise ValueError("model and source arguments must be directories")
        if out == REPO_ROOT or REPO_ROOT in out.parents:
            raise ValueError("model artifacts must stay outside the Git worktree")
        if out.exists():
            raise ValueError(f"refusing to overwrite existing export directory: {out}")
        config, weights, tokenizer_path = checkpoint_files(base_model)
        if not (adapter / "adapter_config.json").is_file() or not (adapter / "adapter_model.safetensors").is_file():
            raise ValueError("adapter must contain adapter_config.json and adapter_model.safetensors")
        adapter_config = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
        if not isinstance(adapter_config, dict):
            raise ValueError("adapter config must be a JSON object")
        validate_adapter_base(adapter_config, base_model)
        base_sha256 = artifact_sha256(base_model, (
            "config.json", "generation_config.json", "model*.safetensors",
            "pytorch_model*.bin", "tokenizer.json", "tokenizer_config.json",
            "special_tokens_map.json", "added_tokens.json", "vocab.json", "merges.txt",
        ))
        adapter_sha256 = artifact_sha256(adapter, (
            "adapter_config.json", "adapter_model*.safetensors", "adapter_model*.bin",
        ))
        qualification = validate_qualification_reports(
            args.qualification_report, base_sha256, adapter_sha256)
        cpp_revision = git_revision(whisper_cpp, WHISPER_CPP_COMMIT, "whisper.cpp")
        openai_revision = git_revision(openai_whisper, OPENAI_WHISPER_COMMIT, "OpenAI Whisper")
        converter = whisper_cpp / "models/convert-h5-to-ggml.py"
        mel_filters = openai_whisper / "whisper/assets/mel_filters.npz"
        quantizer = (args.quantizer.expanduser().resolve(strict=True) if args.quantizer
                     else whisper_cpp / "build/bin/whisper-quantize")
        if not converter.is_file() or not mel_filters.is_file():
            raise ValueError("pinned converter or OpenAI mel_filters.npz is missing")
        if not quantizer.is_file() or not os.access(quantizer, os.X_OK):
            raise ValueError("whisper-quantize is missing or not executable")
        vocab, added_tokens = tokenizer_compatibility(tokenizer_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"preflight failed: {error}") from error

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v6-stt-export-", dir=out.parent) as temporary:
        work = Path(temporary)
        staged_model = work / "hf-checkpoint"
        try:
            import torch
            from peft import PeftModel
            from transformers import WhisperForConditionalGeneration, WhisperProcessor
            base = WhisperForConditionalGeneration.from_pretrained(
                str(base_model), torch_dtype=torch.float32, low_cpu_mem_usage=True)
            adapted = PeftModel.from_pretrained(base, str(adapter))
            merged = adapted.merge_and_unload()
            merged.config.forced_decoder_ids = None
            merged.config.suppress_tokens = []
            merged.save_pretrained(staged_model, safe_serialization=True)
            WhisperProcessor.from_pretrained(str(base_model)).save_pretrained(staged_model)
            del adapted, base, merged
        except Exception as error:
            raise SystemExit(f"base-plus-adapter merge failed: {type(error).__name__}") from error
        merged_config, merged_weights, merged_tokenizer = checkpoint_files(staged_model)
        vocab, added_tokens = tokenizer_compatibility(merged_tokenizer)
        (staged_model / "vocab.json").write_text(
            json.dumps(vocab, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        (staged_model / "added_tokens.json").write_text(
            json.dumps(added_tokens, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        staged_config_path = staged_model / "config.json"
        staged_config = json.loads(staged_config_path.read_text(encoding="utf-8"))
        if not isinstance(staged_config.get("max_length"), int):
            staged_config["max_length"] = int(staged_config.get("max_target_positions") or 448)
            staged_config_path.unlink()
            staged_config_path.write_text(json.dumps(staged_config, indent=2) + "\n", encoding="utf-8")
        converted = subprocess.run(
            [args.python, str(converter), str(staged_model), str(openai_whisper), str(work)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        float_model = work / "ggml-model.bin"
        if converted.returncode or not float_model.is_file() or float_model.stat().st_size == 0:
            raise SystemExit("pinned HF-to-GGML conversion failed; no candidate exported")
        quantized = work / "ggml-v6.bin"
        quant_result = subprocess.run(
            [str(quantizer), str(float_model), str(quantized), "q5_0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if quant_result.returncode or not quantized.is_file() or quantized.stat().st_size == 0:
            raise SystemExit("whisper.cpp Q5_0 quantization failed; no candidate exported")

        staged_out = work / "export"
        staged_out.mkdir()
        final_float = staged_out / "ggml-v6-f16.bin"
        final_mobile = staged_out / "ggml-v6.bin"
        shutil.copyfile(float_model, final_float)
        shutil.move(quantized, final_mobile)
        manifest = {
            "format": "vaani-v6-whispercpp-android-candidate/1",
            "qualification_reports": qualification,
            "source_base_model_sha256": base_sha256,
            "source_adapter_sha256": adapter_sha256,
            "merged_checkpoint": {
                "config_sha256": sha256_file(staged_model / "config.json"),
                "tokenizer_sha256": sha256_file(merged_tokenizer),
                "weight_files": [
                    {"name": path.name, "sha256": sha256_file(path), "bytes": path.stat().st_size}
                    for path in merged_weights
                ],
                "vocab_size": int(merged_config.get("vocab_size", len(vocab) + len(added_tokens))),
                "tokenizer_id_count": len(set(vocab.values()) | set(added_tokens.values())),
            },
            "conversion": {
                "whisper_cpp_commit": cpp_revision,
                "converter_sha256": sha256_file(converter),
                "openai_whisper_commit": openai_revision,
                "mel_filters_sha256": sha256_file(mel_filters),
                "quantizer_sha256": sha256_file(quantizer),
                "quantization": "q5_0",
                "tokenizer_modified": False,
                "ct2_input_used": False,
            },
            "artifacts": {
                final_float.name: {"sha256": sha256_file(final_float), "bytes": final_float.stat().st_size},
                final_mobile.name: {"sha256": sha256_file(final_mobile), "bytes": final_mobile.stat().st_size},
            },
            "qualification_note": "Export candidate only; Android accuracy, memory, and latency are not implied.",
        }
        (staged_out / "export_manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(staged_out, out)
    print(json.dumps({
        "out": str(out),
        "float_sha256": manifest["artifacts"]["ggml-v6-f16.bin"]["sha256"],
        "mobile_sha256": manifest["artifacts"]["ggml-v6.bin"]["sha256"],
        "mobile_bytes": manifest["artifacts"]["ggml-v6.bin"]["bytes"],
        "qualification_reports": len(qualification),
        "base_model_sha256": base_sha256,
        "adapter_sha256": adapter_sha256,
        "android_qualification": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
