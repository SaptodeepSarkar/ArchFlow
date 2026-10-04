"""Ensure the one-shot public benchmark rejects the wrong product control."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "pipelines/stt/qualify-v6-monsoon.sh"


class MonsoonQualificationTests(unittest.TestCase):
    def test_wrong_v5_artifact_cannot_spend_public_test(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            model.mkdir()
            (model / "model.bin").write_bytes(b"not the deployed V5")
            manifest = root / "manifest.jsonl"
            manifest.write_text("", encoding="utf-8")
            (root / "provenance.json").write_text("{}", encoding="utf-8")
            output = root / "output"
            result = subprocess.run([
                "bash", str(SCRIPT), "--base-ct2", str(model),
                "--candidate-ct2", str(model), "--manifest", str(manifest),
                "--out", str(output),
            ], env={**os.environ, "PYTHON": sys.executable},
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 65)
            self.assertIn("pinned deployed V5", result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse((root / ".v6-model-eval-claim.json").exists())
            self.assertFalse((root / ".v6-model-eval-complete.json").exists())
