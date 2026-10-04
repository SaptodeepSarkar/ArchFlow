from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.audit_v6_stt_sampling import audit_sampling


class AuditV6SttSamplingTest(unittest.TestCase):
    def make_manifest(self, root: Path, name: str, rows: list[tuple[str, str | None]]) -> Path:
        path = root / name
        connection = sqlite3.connect(path)
        connection.execute(
            "CREATE TABLE examples (id TEXT, term_sha256 TEXT, target_text TEXT)"
        )
        connection.executemany("INSERT INTO examples VALUES (?, ?, ?)", [
            (str(index), term_hash, "private target")
            for index, (term_hash, _) in enumerate(rows)
        ])
        connection.commit()
        connection.close()
        return path

    def test_estimates_term_coverage_without_exposing_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.make_manifest(Path(directory), "vocab.sqlite3", [
                ("term-a", None), ("term-a", None),
                ("term-b", None), ("term-b", None),
            ])
            result = audit_sampling([manifest], 10, source_fractions=[0.4],
                                    min_expected_draws_per_term=0)
        self.assertEqual(result["sqlite_source_rows"], 4)
        self.assertEqual(result["vocabulary_terms"], 2)
        self.assertAlmostEqual(result["expected_sqlite_draws"], 4)
        self.assertAlmostEqual(result["expected_draws_per_term"], 2)
        self.assertAlmostEqual(result["expected_terms_exposed_at_least_once"],
                               2 * (1 - 0.8 ** 10))
        self.assertNotIn("private target", str(result))

    def test_combined_sampling_accounts_for_non_vocabulary_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            vocab = self.make_manifest(root, "vocab.sqlite3", [("term-a", None)] * 2)
            other = self.make_manifest(root, "other.sqlite3", [(None, None)] * 2)
            result = audit_sampling([vocab, other], 20, combined_fraction=0.5,
                                    min_expected_draws_per_term=0)
        self.assertEqual(result["sqlite_source_rows"], 4)
        self.assertAlmostEqual(result["expected_sqlite_draws"], 10)
        self.assertAlmostEqual(result["expected_draws_per_term"], 5)
        self.assertAlmostEqual(result["expected_terms_exposed_at_least_once"],
                               1 - 0.75 ** 20)

    def test_warns_when_training_budget_underexposes_terms(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.make_manifest(Path(directory), "vocab.sqlite3", [
                (f"term-{index}", None) for index in range(100)
            ])
            result = audit_sampling([manifest], 1500, source_fractions=[0.05])
        self.assertLess(result["expected_draws_per_term"], 1)
        self.assertGreater(len(result["warnings"]), 0)

    def test_rejects_invalid_fraction_count_or_empty_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.make_manifest(root, "vocab.sqlite3", [("term-a", None)])
            with self.assertRaisesRegex(ValueError, "one source fraction"):
                audit_sampling([manifest, manifest], 10, source_fractions=[0.1])
            with self.assertRaisesRegex(ValueError, "between zero and one"):
                audit_sampling([manifest], 10, source_fractions=[1.0])
            with self.assertRaisesRegex(ValueError, "sum to less than one"):
                audit_sampling([manifest, manifest], 10, source_fractions=[0.6, 0.5])
            empty = self.make_manifest(root, "empty.sqlite3", [])
            with self.assertRaisesRegex(ValueError, "empty"):
                audit_sampling([empty], 10, source_fractions=[0.1])


if __name__ == "__main__":
    unittest.main()
