from __future__ import annotations

import sys
import contextlib
import io
import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import eval_v6_android_stt_export as evaluator


class ProtectedTermMetricTests(unittest.TestCase):
    def test_matches_case_insensitive_acronym_and_phrase(self):
        hypothesis = evaluator.normalized_tokens("The LLM uses a speech-to-text model.")
        self.assertTrue(evaluator.contains_term(hypothesis, "LLM"))
        self.assertTrue(evaluator.contains_term(hypothesis, "speech-to-text"))

    def test_does_not_count_substrings_as_term_matches(self):
        hypothesis = evaluator.normalized_tokens("The ants are outside.")
        self.assertFalse(evaluator.contains_term(hypothesis, "LLM"))
        self.assertFalse(evaluator.contains_term(hypothesis, "ant"))

    def test_empty_term_is_not_a_match(self):
        self.assertFalse(evaluator.contains_term(["anything"], "  "))

    def test_export_report_scores_terms_and_edge_tags_without_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "clip.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16_000)
                handle.writeframes(struct.pack("<h", 0) * 1600)
            manifest = root / "challenge.jsonl"
            manifest.write_text(json.dumps({
                "example_id": "example-1",
                "audio": {"ref": "clip.wav"},
                "utterance": {"reference_transcript": "the LLM works"},
                "challenge_terms": ["LLM"],
                "challenge_tags": ["acronym", "clean"],
            }) + "\n")
            cli = root / "whisper-cli"
            cli.touch()
            model = root / "model.bin"
            model.write_bytes(b"test model")
            report_path = root / "report.json"
            argv = [
                "eval_v6_android_stt_export.py", "--manifest", str(manifest),
                "--audio-root", str(root), "--whisper-cli", str(cli),
                "--model", str(model), "--limit", "1", "--report", str(report_path),
            ]
            with patch.object(sys, "argv", argv), patch.object(
                evaluator.subprocess, "run",
                return_value=SimpleNamespace(returncode=0, stdout="The LLM works."),
            ), contextlib.redirect_stdout(io.StringIO()):
                evaluator.main()

            serialized = report_path.read_text()
            report = json.loads(serialized)
            self.assertEqual(report["protected_term_accuracy_percent"], 100.0)
            self.assertEqual(report["challenge_tag_metrics"]["acronym"]["normalized_wer_percent"], 0.0)
            self.assertEqual(report["challenge_tag_metrics"]["clean"]["rows"], 1)
            self.assertNotIn("LLM", serialized)
            self.assertNotIn("works", serialized)


if __name__ == "__main__":
    unittest.main()
