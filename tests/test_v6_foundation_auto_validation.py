#!/usr/bin/env python3
"""Regression checks for the synthetic-only automatic V6 admission gate."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def control(source_kind: str) -> dict:
    return {
        "id": "control-1",
        "source": "uh check CUDA",
        "target_text": "Check CUDA.",
        "metadata": {"source": source_kind, "categories": ["filler"]},
    }


class AutoValidationGateTest(unittest.TestCase):
    def invoke(self, row: dict, enabled: bool) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp, out = root / "input.jsonl", root / "output.jsonl"
            inp.write_text(json.dumps(row) + "\n", encoding="utf-8")
            command = ["python3", str(ROOT / "tools/import_v6_control_candidates.py"),
                       "--input", str(inp), "--out", str(out)]
            if enabled:
                command.append("--automated-validate")
            return subprocess.run(command, text=True, capture_output=True, check=False)

    def test_recognized_control_can_be_automatically_validated(self) -> None:
        result = self.invoke(control("generated-template"), True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["synthetic_candidates"], 1)
        self.assertEqual(report["review_status"], "automated_validated")
        self.assertEqual(report["splits_assigned"], 0)

    def test_non_control_cannot_be_automatically_validated(self) -> None:
        result = self.invoke(control("external-corpus"), True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("synthetic-control-only", result.stderr)

    def test_default_remains_review_required(self) -> None:
        result = self.invoke(control("external-corpus"), False)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["synthetic_candidates"], 1)
        self.assertEqual(report["review_status"], "needs_human_review")
        self.assertEqual(report["splits_assigned"], 0)


if __name__ == "__main__":
    unittest.main()
