from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CompareSeq2SeqTest(unittest.TestCase):
    def run_compare(self, v5: dict, v6: dict,
                    max_fallback: float | None = None,
                    add_provenance: bool = True) -> tuple[subprocess.CompletedProcess, dict]:
        if add_provenance:
            common = {"target_set_sha256": "targets", "base_model_sha256": "base",
                      "evaluation_code_sha256": "eval-code", "protocol_code_sha256": "protocol-code"}
            v5 = {**common, "protocol": "v5", "adapter_sha256": "v5-adapter", **v5}
            v6 = {**common, "protocol": "v6", "adapter_sha256": "v6-adapter", **v6}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base, candidate, report = root / "v5.json", root / "v6.json", root / "comparison.json"
            base.write_text(json.dumps(v5), encoding="utf-8")
            candidate.write_text(json.dumps(v6), encoding="utf-8")
            command = ["python3", str(ROOT / "tools/compare_v6_seq2seq.py"),
                       "--v5", str(base), "--v6", str(candidate), "--suite", "challenge",
                       "--report", str(report)]
            if max_fallback is not None:
                command += ["--max-copy-fallback-rate", str(max_fallback)]
            result = subprocess.run(
                command,
                capture_output=True, text=True, check=False,
            )
            return result, json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}

    def test_only_same_set_nonregressing_copy_safe_candidate_is_eligible(self) -> None:
        base = {"rows": 18, "source_set_sha256": "same", "exact_rate": .4,
                "normalized_exact_rate": .4, "novel_content_tokens": 0,
                "outputs_with_novel_content": 0,
                "missing_target_content_tokens": 0,
                "outputs_missing_target_content": 0}
        candidate = {**base, "exact_rate": .5, "normalized_exact_rate": .5}
        result, report = self.run_compare(base, candidate)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report["promotion_eligible"])
        unsafe = {**candidate, "novel_content_tokens": 1, "outputs_with_novel_content": 1}
        result, report = self.run_compare(base, unsafe)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(report["promotion_eligible"])

    def test_rejects_missing_control_and_mismatched_targets_or_code(self) -> None:
        base = {"rows": 18, "source_set_sha256": "same", "exact_rate": .4,
                "normalized_exact_rate": .4, "novel_content_tokens": 0,
                "outputs_with_novel_content": 0, "missing_target_content_tokens": 0,
                "outputs_missing_target_content": 0}
        result, report = self.run_compare(base, base, add_provenance=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(report)
        for field in ("target_set_sha256", "base_model_sha256", "evaluation_code_sha256",
                      "protocol_code_sha256", "adapter_sha256", "protocol"):
            with self.subTest(field=field):
                value = None if field == "adapter_sha256" else "different"
                result, report = self.run_compare(base, {**base, field: value})
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(report)

    def test_fallback_rate_is_a_separate_promotion_gate(self) -> None:
        base = {"rows": 100, "source_set_sha256": "same", "exact_rate": .4,
                "normalized_exact_rate": .4, "novel_content_tokens": 0,
                "outputs_with_novel_content": 0,
                "missing_target_content_tokens": 0,
                "outputs_missing_target_content": 0}
        candidate = {**base, "exact_rate": .6, "normalized_exact_rate": .6,
                     "copy_guard_fallbacks": 8}
        result, report = self.run_compare(base, candidate, .05)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(report["fallback_rate_gate"])
        self.assertFalse(report["promotion_eligible"])

    def test_token_reordering_requires_a_guard_fallback(self) -> None:
        base = {"rows": 100, "source_set_sha256": "same", "exact_rate": .4,
                "normalized_exact_rate": .4, "novel_content_tokens": 0,
                "outputs_with_novel_content": 0,
                "missing_target_content_tokens": 0,
                "outputs_missing_target_content": 0}
        candidate = {**base, "exact_rate": .6, "normalized_exact_rate": .6,
                     "raw_token_order_violations": 1}
        result, report = self.run_compare(base, candidate)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(report["meaning_preservation_gate"])
        self.assertFalse(report["promotion_eligible"])
        guarded = {**candidate, "copy_guard_fallbacks": 1}
        result, report = self.run_compare(base, guarded)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(report["meaning_preservation_gate"])
        self.assertTrue(report["promotion_eligible"])

    def test_refuses_nonpaired_source_sets(self) -> None:
        base = {"rows": 18, "source_set_sha256": "one", "exact_rate": .4,
                "normalized_exact_rate": .4, "novel_content_tokens": 0,
                "outputs_with_novel_content": 0,
                "missing_target_content_tokens": 0,
                "outputs_missing_target_content": 0}
        candidate = {**base, "source_set_sha256": "other"}
        result, _ = self.run_compare(base, candidate)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("same ordered source set", result.stderr)

    def test_target_content_deletion_fails_semantic_promotion_gate(self) -> None:
        base = {"rows": 18, "source_set_sha256": "same", "exact_rate": .4,
                "normalized_exact_rate": .4, "novel_content_tokens": 0,
                "outputs_with_novel_content": 0,
                "missing_target_content_tokens": 0,
                "outputs_missing_target_content": 0}
        candidate = {**base, "exact_rate": .9, "normalized_exact_rate": .9,
                     "missing_target_content_tokens": 1,
                     "outputs_missing_target_content": 1}
        result, report = self.run_compare(base, candidate)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(report["gold_target_content_gate"])
        self.assertFalse(report["meaning_preservation_gate"])
        self.assertFalse(report["promotion_eligible"])


if __name__ == "__main__":
    unittest.main()
