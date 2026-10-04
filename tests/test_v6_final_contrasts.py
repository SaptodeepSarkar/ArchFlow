import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from freeze_v6_final_contrasts import CASES, freeze, normalized_source


class FinalContrastTest(unittest.TestCase):
    def run_fixture(self, source):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        data = root / "train.jsonl"
        data.write_text(json.dumps({"source": source}) + "\n")
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps({"inputs": {"train": [{"path": str(data),
            "sha256": hashlib.sha256(data.read_bytes()).hexdigest()}]}}))
        return manifest, data, root / "challenge.jsonl"

    def test_freezes_unique_nonhuman_labels_without_overwrite(self):
        manifest, _, out = self.run_fixture("unrelated fixture")
        with contextlib.redirect_stdout(io.StringIO()):
            freeze(manifest, out)
        rows = [json.loads(line) for line in out.read_text().splitlines()]
        self.assertEqual(len(rows), 28)
        self.assertEqual(len({normalized_source(row["source"]) for row in rows}), 28)
        self.assertTrue(all(row["metadata"]["human_reviewed"] is False for row in rows))
        before = out.read_bytes()
        with self.assertRaises(SystemExit):
            freeze(manifest, out)
        self.assertEqual(out.read_bytes(), before)

    def test_normalized_overlap_rejects_before_write(self):
        manifest, _, out = self.run_fixture(CASES[0][0].upper() + "!!!")
        with self.assertRaises(SystemExit):
            freeze(manifest, out)
        self.assertFalse(out.exists())

    def test_changed_input_rejects_before_write(self):
        manifest, data, out = self.run_fixture("unrelated fixture")
        data.write_text("{}\n")
        with self.assertRaises(SystemExit):
            freeze(manifest, out)
        self.assertFalse(out.exists())
