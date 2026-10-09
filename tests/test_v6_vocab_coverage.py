from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import measure_v6_vocab_coverage as coverage


class VocabCoverageTests(unittest.TestCase):
    def test_measures_both_manifest_schemas_without_retaining_text_in_report(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "manifest.jsonl"
            manifest.write_text("\n".join([
                json.dumps({"text": "Please use the LLM, not ants."}),
                json.dumps({"utterance": {"reference_transcript": "A plain sentence."}}),
            ]) + "\n")

            result = coverage.measure(manifest, ["acronyms"])
            serialized = json.dumps(result)

        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["terms_total"], 38)
        self.assertEqual(result["terms_present"], 1)
        self.assertEqual(result["clips_with_terms"], 1)
        self.assertEqual(result["term_clip_counts"]["LLM"], 1)
        self.assertNotIn("Please use", serialized)
        self.assertNotIn("ants", serialized)


if __name__ == "__main__":
    unittest.main()
