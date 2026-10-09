from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.v6_synthetic_vocab_provenance import provenance_record, sha256_file


class SyntheticVocabularyProvenanceTest(unittest.TestCase):
    def test_audio_builder_help_does_not_require_onnx_runtime(self) -> None:
        builder = Path(__file__).resolve().parents[1] / "tools/build_v6_synthetic_vocab_audio.py"
        result = subprocess.run(
            [sys.executable, str(builder), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--voices-list", result.stdout)
        self.assertIn("--execution-provider", result.stdout)

    def test_provenance_pins_model_voice_runtime_without_text_or_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model.onnx"
            voice = root / "voice.bin"
            model.write_bytes(b"local model bytes")
            voice.write_bytes(b"local voice bytes")
            record = json.loads(provenance_record(
                model_sha256=sha256_file(model), voice_asset_sha256=sha256_file(voice),
                voice_id="af_sarah",
                template_index=11, sample_rate=24000,
                runtime_version="1.20.0", package_version="0.4.0",
                execution_provider="CUDAExecutionProvider",
            ))
            self.assertEqual(record["schema_version"], 1)
            self.assertEqual(record["generator_version"], "v6-synthetic-vocab-context-v2")
            self.assertEqual(record["voice_id"], "af_sarah")
            self.assertEqual(record["sample_rate"], 24000)
            self.assertEqual(record["execution_provider"], "CUDAExecutionProvider")
            self.assertEqual(len(record["model_sha256"]), 64)
            self.assertEqual(len(record["voice_asset_sha256"]), 64)
            self.assertNotIn(str(root), json.dumps(record))
            self.assertNotIn("target_text", record)
            self.assertNotIn("transcript", record)


if __name__ == "__main__":
    unittest.main()
