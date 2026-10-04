import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "pipelines/stt/prepare-v6-vocab.sh"


class PreparePackTest(unittest.TestCase):
    def test_rejects_missing_holdout_existing_output_and_repo_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.sqlite3"
            manifest.write_bytes(b"fixture")
            heldout = root / "heldout.jsonl"
            command = ["bash", str(SCRIPT), "--manifest", str(manifest),
                       "--freeze-heldout", str(heldout), "--out", str(root / "new")]
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 66)
            self.assertFalse((root / "new").exists())
            heldout.write_text("{}\n")
            output = root / "existing"
            output.mkdir()
            sentinel = output / "keep"
            sentinel.write_text("preserved")
            command[-1] = str(output)
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 73)
            self.assertEqual(sentinel.read_text(), "preserved")
            command[-1] = str(ROOT / "data" / "never-create-prepare-test")
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 73)
            self.assertFalse(Path(command[-1]).exists())

    def test_invalid_audio_database_cannot_create_split(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "invalid.sqlite3"
            manifest.write_bytes(b"not a SQLite database")
            heldout = root / "heldout.jsonl"
            heldout.write_text("{}\n")
            output = root / "new"
            result = subprocess.run(["bash", str(SCRIPT), "--manifest", str(manifest),
                                     "--freeze-heldout", str(heldout), "--out", str(output)],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
