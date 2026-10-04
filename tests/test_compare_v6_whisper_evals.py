#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CompareWhisperEvalsTest(unittest.TestCase):
    def write(self, path: Path, wer: float, protected: float, digest: str = "same") -> None:
        path.write_text(json.dumps({"evaluated_row_ids_sha256": digest, "rows": 100,
                                    "normalized_wer_percent": wer,
                                    "protected_term_accuracy_percent": protected,
                                    "protected_terms": 20}), encoding="utf-8")

    def test_promotes_only_a_same_manifest_improvement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); base, candidate, report = root / "base.json", root / "candidate.json", root / "report.json"
            self.write(base, 20.0, 90.0); self.write(candidate, 18.0, 90.0)
            result = subprocess.run(["python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                                     "--base", str(base), "--candidate", str(candidate), "--report", str(report),
                                     "--suite", "vocab-heldout",
                                     "--minimum-wer-improvement", "1"], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            result_report = json.loads(report.read_text())
            self.assertTrue(result_report["promotion_eligible"])
            self.assertEqual(result_report["suite"], "vocab-heldout")

    def test_rejects_scoring_vocabulary_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.json", root / "candidate.json", root / "report.json"
            self.write(base, 20.0, 90.0)
            self.write(candidate, 18.0, 90.0)
            command = ["python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                       "--base", str(base), "--candidate", str(candidate), "--report", str(report),
                       "--allow-hotword-mismatch"]
            for baseline_hash in (None, "baseline-vocabulary"):
                baseline = json.loads(base.read_text())
                baseline["scored_vocabulary_sha256"] = baseline_hash
                base.write_text(json.dumps(baseline), encoding="utf-8")
                proposed = json.loads(candidate.read_text())
                proposed["scored_vocabulary_sha256"] = "candidate-vocabulary"
                candidate.write_text(json.dumps(proposed), encoding="utf-8")
                result = subprocess.run(command, text=True, capture_output=True, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("scored_vocabulary_sha256", result.stderr)
                self.assertFalse(report.exists())
            baseline["scored_vocabulary_sha256"] = "candidate-vocabulary"
            base.write_text(json.dumps(baseline), encoding="utf-8")
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_manifest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); base, candidate, report = root / "base.json", root / "candidate.json", root / "report.json"
            self.write(base, 20.0, 90.0); self.write(candidate, 18.0, 90.0, "other")
            result = subprocess.run(["python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                                     "--base", str(base), "--candidate", str(candidate), "--report", str(report)],
                                    text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("same held-out", result.stderr)

    def test_reduces_privacy_safe_jsonl_rows_and_rejects_vocab_regression(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.jsonl", root / "candidate.jsonl", root / "report.json"
            rows = [
                {"row_id": "a", "reference_words": 10, "normalized_errors": 4,
                 "protected_terms": 2, "missing_protected_terms": 0},
                {"row_id": "b", "reference_words": 10, "normalized_errors": 3,
                 "protected_terms": 1, "missing_protected_terms": 0},
            ]
            candidate_rows = [
                {**rows[0], "normalized_errors": 3, "missing_protected_terms": 1},
                {**rows[1], "normalized_errors": 2, "missing_protected_terms": 1},
            ]
            base.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            candidate.write_text("".join(json.dumps(row) + "\n" for row in candidate_rows), encoding="utf-8")
            result = subprocess.run(["python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                                     "--base", str(base), "--candidate", str(candidate),
                                     "--report", str(report)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(metrics["rows"], 2)
            self.assertAlmostEqual(metrics["base_normalized_wer_percent"], 35.0)
            self.assertAlmostEqual(metrics["candidate_normalized_wer_percent"], 25.0)
            self.assertAlmostEqual(metrics["protected_term_accuracy_delta_percentage_points"], -66.6667, places=3)
            self.assertFalse(metrics["promotion_eligible"])

    def test_jsonl_pair_requires_matching_base_and_decoder_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.jsonl", root / "candidate.jsonl", root / "report.json"
            rows = [
                {"row_id": "a", "reference_words": 10, "normalized_errors": 4,
                 "protected_terms": 1, "missing_protected_terms": 0},
                {"row_id": "b", "reference_words": 10, "normalized_errors": 3,
                 "protected_terms": 1, "missing_protected_terms": 0},
            ]
            candidate_rows = [{**row, "normalized_errors": 2} for row in rows]
            base.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            candidate.write_text("".join(json.dumps(row) + "\n" for row in candidate_rows), encoding="utf-8")
            metadata = {
                "schema_version": 1,
                "rows": 2,
                "evaluated_row_ids_sha256": "edc8b6a725f3f1d8b6c2e6edaf5e6cb8bb7e5f47c4a2f59133aa6a71c2c2ab91",
                "base_model_sha256": "same-base",
                "adapter_sha256": None,
                "decoder": {"beams": 5, "device": "cpu"},
            }
            # Match the comparator's digest of these synthetic row IDs.
            import hashlib
            metadata["evaluated_row_ids_sha256"] = hashlib.sha256(b"a\nb").hexdigest()
            base.with_name(base.name + ".meta.json").write_text(json.dumps(metadata), encoding="utf-8")
            candidate_meta = {**metadata, "adapter_sha256": "candidate-adapter"}
            candidate.with_name(candidate.name + ".meta.json").write_text(json.dumps(candidate_meta), encoding="utf-8")
            command = ["python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                       "--base", str(base), "--candidate", str(candidate), "--report", str(report)]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(report.read_text())["model_provenance_verified"])

            candidate_meta["base_model_sha256"] = "different-base"
            candidate.with_name(candidate.name + ".meta.json").write_text(json.dumps(candidate_meta), encoding="utf-8")
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("different base model", result.stderr)

    def test_rejects_vocabulary_result_with_too_little_support(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.json", root / "candidate.json", root / "report.json"
            self.write(base, 20.0, 80.0); self.write(candidate, 18.0, 100.0)
            result = subprocess.run([
                "python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                "--base", str(base), "--candidate", str(candidate), "--report", str(report),
                "--minimum-protected-term-support", "30",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(metrics["protected_term_support_gate"])
            self.assertFalse(metrics["promotion_eligible"])

    def test_enforces_absolute_protected_term_accuracy_floor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.json", root / "candidate.json", root / "report.json"
            self.write(base, 20.0, 98.0); self.write(candidate, 19.0, 98.5)
            command = [
                "python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                "--base", str(base), "--candidate", str(candidate), "--report", str(report),
                "--minimum-protected-term-accuracy", "99",
            ]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(metrics["protected_term_accuracy_gate"])
            self.assertFalse(metrics["promotion_eligible"])
            self.write(candidate, 19.0, 99.0)
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(metrics["protected_term_accuracy_gate"])
            self.assertTrue(metrics["promotion_eligible"])

    def test_requires_a_minimum_vocabulary_gain_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.json", root / "candidate.json", root / "report.json"
            self.write(base, 20.0, 80.0); self.write(candidate, 19.0, 82.0)
            result = subprocess.run([
                "python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                "--base", str(base), "--candidate", str(candidate), "--report", str(report),
                "--minimum-protected-term-gain", "5",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(metrics["promotion_eligible"])

    def test_missing_term_accuracy_only_blocks_an_explicit_floor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.json", root / "candidate.json", root / "report.json"
            common = {"evaluated_row_ids_sha256": "same", "rows": 100,
                      "protected_terms": 0, "protected_term_accuracy_percent": None}
            base.write_text(json.dumps({**common, "normalized_wer_percent": 20.0}))
            candidate.write_text(json.dumps({**common, "normalized_wer_percent": 18.0}))
            command = ["python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                       "--base", str(base), "--candidate", str(candidate), "--report", str(report)]
            result = subprocess.run(command, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(report.read_text())["promotion_eligible"])
            result = subprocess.run(command + ["--minimum-protected-term-accuracy", "99"],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(report.read_text())["promotion_eligible"])

    def test_compares_ct2_reports_on_matching_model_and_rows_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.json", root / "hotwords.json", root / "report.json"
            common = {
                "source_manifest_sha256": "manifest",
                "selected_example_ids_sha256": "rows",
                "model_sha256": "model",
                "rows_requested": 96,
                "rows_decoded": 96,
                "decode_failures": 0,
                "protected_terms": 96,
            }
            base.write_text(json.dumps({**common, "normalized_wer_percent": 9.5,
                                        "protected_term_accuracy_percent": 84.375}), encoding="utf-8")
            candidate.write_text(json.dumps({**common, "normalized_wer_percent": 5.9,
                                             "protected_term_accuracy_percent": 96.875}), encoding="utf-8")
            result = subprocess.run([
                "python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                "--base", str(base), "--candidate", str(candidate), "--report", str(report),
                "--minimum-wer-improvement", "0", "--minimum-protected-term-support", "50",
                "--minimum-protected-term-gain", "5",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(metrics["promotion_eligible"])
            candidate.write_text(json.dumps({**common, "model_sha256": "other-model",
                                             "normalized_wer_percent": 5.9,
                                             "protected_term_accuracy_percent": 96.875}), encoding="utf-8")
            result = subprocess.run([
                "python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                "--base", str(base), "--candidate", str(candidate), "--report", str(report),
            ], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("model_sha256", result.stderr)

            result = subprocess.run([
                "python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                "--base", str(base), "--candidate", str(candidate), "--report", str(report),
                "--allow-model-mismatch",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(metrics["promotion_eligible"])
            self.assertFalse(metrics["model_hash_match"])
            self.assertEqual(metrics["base_model_sha256"], "model")
            self.assertEqual(metrics["candidate_model_sha256"], "other-model")

    def test_distinct_models_still_require_identical_decoder_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.json", root / "candidate.json", root / "report.json"
            common = {
                "source_manifest_sha256": "manifest",
                "selected_example_ids_sha256": "rows",
                "rows_requested": 2,
                "rows_decoded": 2,
                "decode_failures": 0,
                "protected_terms": 0,
                "protected_term_accuracy_percent": None,
                "normalized_wer_percent": 10.0,
                "decoder": {"beam_size": 5, "language": "en", "hotwords_enabled": False},
            }
            base.write_text(json.dumps({**common, "model_sha256": "base"}), encoding="utf-8")
            candidate.write_text(json.dumps({
                **common, "model_sha256": "candidate",
                "decoder": {"beam_size": 1, "language": "en", "hotwords_enabled": False},
            }), encoding="utf-8")
            result = subprocess.run([
                "python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                "--base", str(base), "--candidate", str(candidate), "--report", str(report),
                "--allow-model-mismatch",
            ], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("decoder settings", result.stderr)

    def test_hotword_ablation_allows_only_explicit_context_difference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "base.json", root / "hotwords.json", root / "report.json"
            common = {
                "source_manifest_sha256": "manifest",
                "selected_example_ids_sha256": "rows",
                "model_sha256": "model",
                "rows_requested": 32,
                "rows_decoded": 32,
                "decode_failures": 0,
                "protected_terms": 0,
                "protected_term_accuracy_percent": None,
            }
            base_decoder = {"beam_size": 5, "language": "en", "hotwords_enabled": False,
                            "hotwords_sha256": None}
            hotword_decoder = {"beam_size": 5, "language": "en", "hotwords_enabled": True,
                               "hotwords_sha256": "digest"}
            base.write_text(json.dumps({**common, "decoder": base_decoder,
                                        "normalized_wer_percent": 17.9}), encoding="utf-8")
            candidate.write_text(json.dumps({**common, "decoder": hotword_decoder,
                                             "normalized_wer_percent": 25.5}), encoding="utf-8")
            command = ["python3", str(ROOT / "tools/compare_v6_whisper_evals.py"),
                       "--base", str(base), "--candidate", str(candidate), "--report", str(report)]
            result = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("decoder settings", result.stderr)

            result = subprocess.run(command + ["--allow-hotword-mismatch"],
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(report.read_text(encoding="utf-8"))
            self.assertFalse(metrics["hotword_settings_match"])
            self.assertEqual(metrics["decoder"], base_decoder)
            self.assertEqual(metrics["candidate_decoder"], hotword_decoder)
            self.assertFalse(metrics["promotion_eligible"])

            candidate.write_text(json.dumps({
                **common,
                "decoder": {**hotword_decoder, "beam_size": 1},
                "normalized_wer_percent": 25.5,
            }), encoding="utf-8")
            result = subprocess.run(command + ["--allow-hotword-mismatch"],
                                    text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("beyond hotwords", result.stderr)


if __name__ == "__main__":
    unittest.main()
