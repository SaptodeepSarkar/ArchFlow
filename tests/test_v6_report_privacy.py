#!/usr/bin/env python3
"""Regression tests for aggregate-only V6 renderer reports."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RendererReportPrivacyTest(unittest.TestCase):
    def test_report_excludes_source_and_target_text(self) -> None:
        marker = "UNIQUE_PRIVATE_DICTATION_MARKER"
        row = {
            "id": "privacy-check-1",
            "source_tokens": [marker],
            "token_labels": ["KEEP"],
            "punctuation_after": {"0": "PERIOD"},
            "target_text": marker.capitalize() + ".",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inp, report = root / "plans.jsonl", root / "report.json"
            inp.write_text(json.dumps(row) + "\n", encoding="utf-8")
            result = subprocess.run(
                ["python3", str(ROOT / "tools/render_v6_edit_plan.py"),
                 "--input", str(inp), "--report", str(report)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = report.read_text(encoding="utf-8")
            self.assertNotIn(marker, saved)
            self.assertNotIn(marker, result.stdout)
            payload = json.loads(saved)
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["rows"], 1)
            self.assertNotIn("target_text", payload)
            self.assertNotIn("rendered", payload)

    def test_html_benchmark_excludes_case_text_and_audio_paths(self) -> None:
        marker = "UNIQUE_PRIVATE_BENCHMARK_MARKER"
        audio_marker = "/private/audio/location.wav"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, learned, hybrid, report = (root / "data.jsonl", root / "learned.jsonl",
                                              root / "hybrid.json", root / "report.html")
            data.write_text(json.dumps({"id": "case-1", "source": marker,
                                        "target_text": marker, "audio_path": audio_marker}) + "\n",
                            encoding="utf-8")
            learned.write_text(json.dumps({"id": "case-1", "exact": True,
                                           "generated": {"hidden": marker}}) + "\n", encoding="utf-8")
            hybrid.write_text(json.dumps({"rows": 1, "rendered_exact": 1,
                                          "protected_failures": 0, "rows_detail": []}), encoding="utf-8")
            result = subprocess.run(
                ["python3", str(ROOT / "tools/build_v6_html_report.py"),
                 "--data", str(data), "--learned", str(learned), "--hybrid", str(hybrid),
                 "--out", str(report)], text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = report.read_text(encoding="utf-8")
            self.assertNotIn(marker, saved)
            self.assertNotIn(audio_marker, saved)

    def test_html_benchmark_excludes_untrusted_metric_keys_and_summary_values(self) -> None:
        marker = "UNIQUE_PRIVATE_METRIC_MARKER"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, learned, hybrid, report = (root / "data.jsonl", root / "learned.jsonl",
                                              root / "hybrid.json", root / "report.html")
            data.write_text(json.dumps({"id": "case-1", "source": "safe",
                                        "target_text": "safe"}) + "\n", encoding="utf-8")
            learned.write_text(json.dumps({"id": "case-1", "exact": True}) + "\n",
                               encoding="utf-8")
            hybrid.write_text(json.dumps({"rows": 1, "rendered_exact": marker,
                                          "protected_failures": 0, "rows_detail": []}),
                              encoding="utf-8")
            result = subprocess.run(
                ["python3", str(ROOT / "tools/build_v6_html_report.py"),
                 "--data", str(data), "--learned", str(learned), "--hybrid", str(hybrid),
                 "--stt-summary", json.dumps({marker: 1}), "--out", str(report)],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = report.read_text(encoding="utf-8")
            self.assertNotIn(marker, saved)


if __name__ == "__main__":
    unittest.main()
