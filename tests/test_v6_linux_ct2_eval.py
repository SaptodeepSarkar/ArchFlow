from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import eval_v6_linux_ct2 as evaluator


class LinuxCt2EvalTests(unittest.TestCase):
    def test_edit_counts_and_term_matching(self):
        self.assertEqual(evaluator.edit_counts(["the", "llm"], ["the", "ants"]), (1, 0, 0))
        self.assertTrue(evaluator.contains_term(["the", "llm", "works"], "LLM"))
        self.assertFalse(evaluator.contains_term(["the", "ants"], "LLM"))

    def test_hotword_packs_combine_and_deduplicate_case_insensitively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first.txt", root / "second.txt"
            first.write_text("# pack one\nLLM\nCUDA\n", encoding="utf-8")
            second.write_text("cuda\nwhisper.cpp\n", encoding="utf-8")
            self.assertEqual(evaluator.read_hotwords([first, second]), "LLM, CUDA, whisper.cpp")

    def test_writes_only_aggregate_metrics_for_hotword_run(self):
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
            }) + "\n", encoding="utf-8")
            hotwords = root / "hotwords.txt"
            hotwords.write_text("LLM\n", encoding="utf-8")
            model_path = root / "ct2-model"
            model_path.mkdir()
            (model_path / "model.bin").write_bytes(b"test model")
            report_path = root / "report.json"
            calls = []

            def transcribe(*args, **kwargs):
                calls.append(kwargs)
                return iter([SimpleNamespace(text="The LLM works.")]), SimpleNamespace()

            fake_model = SimpleNamespace(transcribe=transcribe)
            fake_module = SimpleNamespace(WhisperModel=lambda *args, **kwargs: fake_model)
            argv = [
                "eval_v6_linux_ct2.py", "--manifest", str(manifest),
                "--audio-root", str(root), "--model", str(model_path),
                "--hotwords-file", str(hotwords), "--device", "cpu",
                "--limit", "1", "--report", str(report_path),
            ]
            with patch.object(sys, "argv", argv), patch.dict(
                sys.modules, {"faster_whisper": fake_module}
            ), contextlib.redirect_stdout(io.StringIO()):
                evaluator.main()

            serialized = report_path.read_text(encoding="utf-8")
            report = json.loads(serialized)
            self.assertEqual(report["normalized_wer_percent"], 0.0)
            self.assertEqual(report["protected_term_accuracy_percent"], 100.0)
            self.assertEqual(report["challenge_tag_metrics"]["acronym"]["rows"], 1)
            self.assertTrue(report["decoder"]["hotwords_enabled"])
            self.assertEqual(calls[0]["hotwords"], "LLM")
            self.assertNotIn("LLM", serialized)
            self.assertNotIn("works", serialized)
            self.assertNotIn("clip.wav", serialized)

    def test_all_decode_failures_do_not_look_like_zero_wer(self):
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
                "utterance": {"reference_transcript": "a test phrase"},
            }) + "\n", encoding="utf-8")
            model_path = root / "ct2-model"
            model_path.mkdir()
            (model_path / "model.bin").write_bytes(b"test model")
            report_path = root / "report.json"

            def transcribe(*args, **kwargs):
                raise RuntimeError("backend unavailable")

            fake_model = SimpleNamespace(transcribe=transcribe)
            fake_module = SimpleNamespace(WhisperModel=lambda *args, **kwargs: fake_model)
            argv = [
                "eval_v6_linux_ct2.py", "--manifest", str(manifest),
                "--audio-root", str(root), "--model", str(model_path),
                "--device", "cpu", "--limit", "1", "--report", str(report_path),
            ]
            with patch.object(sys, "argv", argv), patch.dict(
                sys.modules, {"faster_whisper": fake_module}
            ), contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(
                    SystemExit,
                    r"all rows failed to decode.*failure_classes=RuntimeError:1",
                ):
                    evaluator.main()

            self.assertFalse(report_path.exists())

    def test_reads_private_sqlite_manifest_and_scores_relevant_terms_in_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "clip.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16_000)
                handle.writeframes(struct.pack("<h", 0) * 1600)
            manifest = root / "heldout.sqlite3"
            with sqlite3.connect(manifest) as database:
                database.execute(
                    "CREATE TABLE examples (id TEXT, audio_path TEXT, target_text TEXT)"
                )
                database.executemany("INSERT INTO examples VALUES (?, ?, ?)", [
                    ("row-a", str(audio), "The LLM works"),
                    ("row-b", str(audio), "A meeting works"),
                ])
            vocabulary = root / "engineering.txt"
            vocabulary.write_text("LLM\nCUDA\n", encoding="utf-8")
            model_path = root / "ct2-model"
            model_path.mkdir()
            (model_path / "model.bin").write_bytes(b"test model")
            report_path = root / "report.json"

            def transcribe(*args, **kwargs):
                return iter([SimpleNamespace(text="The LLM works")]), SimpleNamespace()

            fake_model = SimpleNamespace(transcribe=transcribe)
            fake_module = SimpleNamespace(WhisperModel=lambda *args, **kwargs: fake_model)
            argv = [
                "eval_v6_linux_ct2.py", "--manifest", str(manifest),
                "--model", str(model_path), "--score-hotwords-file", str(vocabulary),
                "--device", "cpu", "--limit", "0", "--report", str(report_path),
            ]
            with patch.object(sys, "argv", argv), patch.dict(
                sys.modules, {"faster_whisper": fake_module}
            ), contextlib.redirect_stdout(io.StringIO()):
                evaluator.main()

            serialized = report_path.read_text(encoding="utf-8")
            report = json.loads(serialized)
            self.assertEqual(report["rows_decoded"], 2)
            self.assertEqual(report["protected_terms"], 1)
            self.assertEqual(report["protected_terms_recognized"], 1)
            self.assertFalse(report["decoder"]["hotwords_enabled"])
            self.assertEqual(len(report["scored_vocabulary_sha256"]), 64)
            self.assertNotIn("LLM", serialized)
            self.assertNotIn("meeting", serialized)
            self.assertNotIn(str(audio), serialized)


if __name__ == "__main__":
    unittest.main()
