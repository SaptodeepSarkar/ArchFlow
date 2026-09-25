import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import ingest_v6_ami_scale as ingest


class SkipLedgerTests(unittest.TestCase):
    def test_skipped_ids_survive_resume_without_transcript_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skips.jsonl"
            self.assertEqual(ingest.load_skipped_record_ids(path), set())
            ingest.append_skip(path, "AMI-record-1", "empty")
            ingest.append_skip(path, "AMI-record-2", "duplicate")

            self.assertEqual(
                ingest.load_skipped_record_ids(path),
                {"AMI-record-1", "AMI-record-2"},
            )
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertTrue(all(set(row) == {"source_record_id", "status"} for row in rows))

    def test_invalid_skip_status_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skips.jsonl"
            path.write_text(json.dumps({"source_record_id": "x", "status": "approved"}) + "\n")
            with self.assertRaises(ValueError):
                ingest.load_skipped_record_ids(path)


if __name__ == "__main__":
    unittest.main()
