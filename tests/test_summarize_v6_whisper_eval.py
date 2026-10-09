from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import summarize_v6_whisper_eval as summary


class SummarizeV6WhisperEvalTests(unittest.TestCase):
    def test_reduces_private_rows_to_aggregate_only_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "private.jsonl"
            source.write_text("\n".join(json.dumps(row) for row in (
                {"row_id": "hash-one", "reference_words": 4, "literal_errors": 2,
                 "normalized_errors": 1, "normalized_wer": 0.25,
                 "protected_terms": 1, "missing_protected_terms": 0},
                {"row_id": "hash-two", "reference_words": 6, "literal_errors": 3,
                 "normalized_errors": 2, "normalized_wer": 1 / 3,
                 "protected_terms": 2, "missing_protected_terms": 1},
            )) + "\n", encoding="utf-8")
            report_path = root / "aggregate.json"
            with patch.object(sys, "argv", [
                "summarize_v6_whisper_eval.py", "--input", str(source),
                "--report", str(report_path),
            ]), contextlib.redirect_stdout(io.StringIO()):
                summary.main()
            serialized = report_path.read_text(encoding="utf-8")
            report = json.loads(serialized)
            self.assertEqual(report["rows"], 2)
            self.assertEqual(report["normalized_wer_percent"], 30.0)
            self.assertEqual(report["protected_term_accuracy_percent"], 66.6667)
            self.assertIn("evaluated_row_ids_sha256", report)
            self.assertNotIn("hash-one", serialized)
            self.assertNotIn("hash-two", serialized)


if __name__ == "__main__":
    unittest.main()
