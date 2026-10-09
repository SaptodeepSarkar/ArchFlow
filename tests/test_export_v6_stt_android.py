from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.export_v6_stt_android import (
    checkpoint_files,
    tokenizer_compatibility,
    validate_adapter_base,
    validate_qualification_reports,
)


class ExportV6SttAndroidTest(unittest.TestCase):
    def test_adapter_must_declare_the_exact_existing_base_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base"
            other = Path(directory) / "other"
            base.mkdir()
            other.mkdir()
            validate_adapter_base({"base_model_name_or_path": str(base)}, base.resolve())
            with self.assertRaisesRegex(ValueError, "different base checkpoint"):
                validate_adapter_base({"base_model_name_or_path": str(other)}, base.resolve())
            with self.assertRaisesRegex(ValueError, "must declare"):
                validate_adapter_base({}, base.resolve())
            with self.assertRaisesRegex(ValueError, "must declare"):
                validate_adapter_base({"base_model_name_or_path": 42}, base.resolve())
            with self.assertRaisesRegex(ValueError, "not available locally"):
                validate_adapter_base(
                    {"base_model_name_or_path": str(Path(directory) / "missing")}, base.resolve())

    def test_tokenizer_compatibility_preserves_contiguous_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tokenizer.json"
            path.write_text(json.dumps({
                "model": {"type": "BPE", "vocab": {"a": 0, "b": 1}},
                "added_tokens": [
                    {"content": "b", "id": 1},
                    {"content": "<|extra|>", "id": 2},
                ],
            }), encoding="utf-8")
            vocab, added = tokenizer_compatibility(path)
        self.assertEqual(vocab, {"a": 0, "b": 1})
        self.assertEqual(added, {"b": 1, "<|extra|>": 2})

    def test_tokenizer_compatibility_rejects_id_gaps_and_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tokenizer.json"
            path.write_text(json.dumps({
                "model": {"type": "BPE", "vocab": {"a": 0, "b": 2}},
                "added_tokens": [],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contiguous"):
                tokenizer_compatibility(path)
            path.write_text(json.dumps({
                "model": {"type": "BPE", "vocab": {"a": 0, "b": 1}},
                "added_tokens": [{"content": "other", "id": 1}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "conflicts"):
                tokenizer_compatibility(path)

    def test_requires_full_hf_whisper_not_adapter_or_ct2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory)
            (checkpoint / "config.json").write_text(json.dumps({
                "model_type": "whisper",
                "architectures": ["WhisperForConditionalGeneration"],
                "num_mel_bins": 80,
                "vocab_size": 1,
            }), encoding="utf-8")
            (checkpoint / "tokenizer.json").write_text(json.dumps({
                "model": {"type": "BPE", "vocab": {"a": 0}},
                "added_tokens": [],
            }), encoding="utf-8")
            (checkpoint / "model.safetensors").touch()
            checkpoint_files(checkpoint)
            (checkpoint / "adapter_config.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PEFT adapters"):
                checkpoint_files(checkpoint)
            (checkpoint / "adapter_config.json").unlink()
            config = json.loads((checkpoint / "config.json").read_text())
            config["vocab_size"] = 4
            (checkpoint / "config.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "vocabulary size"):
                checkpoint_files(checkpoint)

    def test_requires_passing_qualification_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vocab_path = root / "comparison-vocab.json"
            ami_path = root / "comparison-ami.json"
            vocab_path.write_text(json.dumps({
                "promotion_eligible": True,
                "base_model_provenance_sha256": "base",
                "candidate_adapter_sha256": "adapter",
                "suite": "vocab-heldout",
            }), encoding="utf-8")
            ami_path.write_text(json.dumps({
                "promotion_eligible": True,
                "base_model_provenance_sha256": "base",
                "candidate_adapter_sha256": "adapter",
                "suite": "ami-dev",
            }), encoding="utf-8")
            reports = validate_qualification_reports([vocab_path, ami_path], "base", "adapter")
            self.assertEqual(len(reports[0]["sha256"]), 64)
            self.assertEqual({item["suite"] for item in reports}, {"vocab-heldout", "ami-dev"})
            with self.assertRaisesRegex(ValueError, "missing required qualification suites"):
                validate_qualification_reports([vocab_path], "base", "adapter")
            vocab_path.write_text(json.dumps({
                "promotion_eligible": True,
                "base_model_provenance_sha256": "wrong-base",
                "candidate_adapter_sha256": "adapter",
                "suite": "vocab-heldout",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "supplied base"):
                validate_qualification_reports([vocab_path, ami_path], "base", "adapter")
            vocab_path.write_text(json.dumps({
                "promotion_eligible": True,
                "base_model_provenance_sha256": "base",
                "candidate_adapter_sha256": "wrong-adapter",
                "suite": "vocab-heldout",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "supplied candidate adapter"):
                validate_qualification_reports([vocab_path, ami_path], "base", "adapter")
            vocab_path.write_text(json.dumps({
                "promotion_eligible": False,
                "base_model_provenance_sha256": "base",
                "candidate_adapter_sha256": "adapter",
                "suite": "vocab-heldout",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must pass"):
                validate_qualification_reports([vocab_path, ami_path], "base", "adapter")
            vocab_path.write_text(json.dumps({
                "promotion_eligible": True,
                "base_model_provenance_sha256": "base",
                "candidate_adapter_sha256": "adapter",
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must name its evaluation suite"):
                validate_qualification_reports([vocab_path, ami_path], "base", "adapter")
            with self.assertRaisesRegex(ValueError, "duplicate qualification suite"):
                validate_qualification_reports([ami_path, ami_path], "base", "adapter")


if __name__ == "__main__":
    unittest.main()
