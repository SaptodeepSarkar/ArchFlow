from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import tempfile
import unittest
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = (
    "Please explain {term} in the Vaani project.",
    "Check the {term} configuration before deployment.",
    "Could you repeat the {term} result?",
    "I heard {term} during the review yesterday.",
    "The documentation uses {term} in this example.",
    "We should verify {term} before publishing the update.",
    "Did you say {term} or the earlier option?",
    "Put {term} near the top of the notes.",
    "I will ask the team whether {term} is available.",
    "Can you spell {term} for me one more time?",
    "The new build reports a problem with {term}.",
    "I think the audio says {term}, but I'm not sure.",
)


class SplitSyntheticVocabularyTest(unittest.TestCase):
    def test_incomplete_and_duplicate_grids_are_rejected(self) -> None:
        spec = importlib.util.spec_from_file_location("split_vocab", ROOT / "tools/split_v6_synthetic_vocab.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        rows = [{"term_sha256": term, "template_index": template, "voice": voice}
                for term in ("a", "b") for template in (0, 1) for voice in ("x", "y")]
        module.validate_grid(rows, 2, 2, 2)
        for candidate, dimensions in ((rows[:-1], (2, 2, 2)),
                                      (rows + [rows[0]], (2, 2, 2)),
                                      (rows, (3, 2, 2)), (rows, (2, 12, 2))):
            with self.assertRaises(SystemExit):
                module.validate_grid(candidate, *dimensions)

    def test_whole_terms_are_held_out_and_never_printed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            out = root / "split"
            connection = sqlite3.connect(source)
            connection.execute("""CREATE TABLE examples (
                id TEXT PRIMARY KEY, audio_path TEXT NOT NULL, target_text TEXT NOT NULL,
                term_pack TEXT NOT NULL, term_sha256 TEXT NOT NULL, template_index INTEGER NOT NULL,
                voice TEXT NOT NULL, sample_rate INTEGER NOT NULL, audio_sha256 TEXT NOT NULL,
                provenance TEXT NOT NULL)""")
            for term_index in range(10):
                term = f"VocabTerm{term_index}"
                term_hash = hashlib.sha256(term.encode()).hexdigest()
                for template_index, template in enumerate(TEMPLATES):
                    for voice in ("voice_a", "voice_b"):
                        audio = root / f"{term_index}-{template_index}-{voice}.wav"
                        audio.write_bytes(f"audio:{term_index}:{template_index}:{voice}".encode())
                        identity = hashlib.sha256(str(audio).encode()).hexdigest()
                        connection.execute("INSERT INTO examples VALUES (?,?,?,?,?,?,?,?,?,?)", (
                            identity, str(audio), template.format(term=term), "test-pack", term_hash,
                            template_index, voice, 24000,
                            hashlib.sha256(audio.read_bytes()).hexdigest(), "synthetic fixture",
                        ))
            connection.commit(); connection.close()
            result = subprocess.run([
                "python3", str(ROOT / "tools/split_v6_synthetic_vocab.py"),
                "--manifest", str(source), "--out-dir", str(out), "--holdout-percent", "20",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("VocabTerm", result.stdout)
            metrics = json.loads(result.stdout)
            self.assertEqual(metrics["train_terms"], 8)
            self.assertEqual(metrics["heldout_terms"], 2)
            self.assertEqual(metrics["train_rows"], 192)
            self.assertEqual(metrics["heldout_rows"], 48)
            train_db = sqlite3.connect(out / "train.sqlite3")
            train_hashes = {row[0] for row in train_db.execute(
                "SELECT DISTINCT term_sha256 FROM examples")}
            training_audio = Path(train_db.execute("SELECT audio_path FROM examples LIMIT 1").fetchone()[0])
            train_db.close()
            heldout = [json.loads(line) for line in (out / "heldout.jsonl").read_text().splitlines()]
            heldout_terms = {row["challenge_terms"][0] for row in heldout}
            heldout_hashes = {hashlib.sha256(term.encode()).hexdigest() for term in heldout_terms}
            self.assertFalse(train_hashes & heldout_hashes)
            self.assertTrue(all(row["challenge_tags"] == ["synthetic_vocab_unseen_term"] for row in heldout))
            training_audio.write_bytes(b"corrupt training-only clip")
            rejected_out = root / "rejected"
            corrupt_result = subprocess.run([
                "python3", str(ROOT / "tools/split_v6_synthetic_vocab.py"),
                "--manifest", str(source), "--out-dir", str(rejected_out),
            ], text=True, capture_output=True, check=False)
            self.assertNotEqual(corrupt_result.returncode, 0)
            self.assertIn("checksum mismatch", corrupt_result.stderr)
            self.assertFalse(rejected_out.exists())
            again = subprocess.run([
                "python3", str(ROOT / "tools/split_v6_synthetic_vocab.py"),
                "--manifest", str(source), "--out-dir", str(out),
            ], text=True, capture_output=True, check=False)
            self.assertNotEqual(again.returncode, 0)

    def test_seen_terms_hold_out_a_whole_context_for_both_voices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.sqlite3"
            out = root / "split"
            connection = sqlite3.connect(source)
            connection.execute("""CREATE TABLE examples (
                id TEXT PRIMARY KEY, audio_path TEXT NOT NULL, target_text TEXT NOT NULL,
                term_pack TEXT NOT NULL, term_sha256 TEXT NOT NULL, template_index INTEGER NOT NULL,
                voice TEXT NOT NULL, sample_rate INTEGER NOT NULL, audio_sha256 TEXT NOT NULL,
                provenance TEXT NOT NULL)""")
            for term_index in range(10):
                term = f"VocabTerm{term_index}"
                term_hash = hashlib.sha256(term.encode()).hexdigest()
                for template_index, template in enumerate(TEMPLATES[:3]):
                    for voice in ("voice_a", "voice_b"):
                        audio = root / f"{term_index}-{template_index}-{voice}.wav"
                        audio.write_bytes(f"audio:{term_index}:{template_index}:{voice}".encode())
                        identity = hashlib.sha256(str(audio).encode()).hexdigest()
                        connection.execute("INSERT INTO examples VALUES (?,?,?,?,?,?,?,?,?,?)", (
                            identity, str(audio), template.format(term=term), "test-pack", term_hash,
                            template_index, voice, 24000,
                            hashlib.sha256(audio.read_bytes()).hexdigest(), "synthetic fixture",
                        ))
            connection.commit(); connection.close()
            result = subprocess.run([
                "python3", str(ROOT / "tools/split_v6_synthetic_vocab.py"),
                "--manifest", str(source), "--out-dir", str(out),
                "--strategy", "seen-term-context",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("VocabTerm", result.stdout)
            metrics = json.loads(result.stdout)
            self.assertEqual(metrics["strategy"], "seen-term-context")
            self.assertEqual(metrics["train_terms"], 10)
            self.assertEqual(metrics["heldout_terms"], 10)
            self.assertEqual(metrics["train_rows"], 40)
            self.assertEqual(metrics["heldout_rows"], 20)
            train_db = sqlite3.connect(out / "train.sqlite3")
            train_hashes = {row[0] for row in train_db.execute(
                "SELECT DISTINCT term_sha256 FROM examples")}
            train_contexts = {(row[0], row[1]) for row in train_db.execute(
                "SELECT DISTINCT term_sha256, template_index FROM examples")}
            train_db.close()
            heldout = [json.loads(line) for line in (out / "heldout.jsonl").read_text().splitlines()]
            heldout_hashes = {hashlib.sha256(row["challenge_terms"][0].encode()).hexdigest()
                              for row in heldout}
            self.assertEqual(train_hashes, heldout_hashes)
            self.assertTrue(all(
                (term_hash, index) not in train_contexts
                for term_hash in heldout_hashes
                for index in range(len(TEMPLATES))
                if any(hashlib.sha256(row["challenge_terms"][0].encode()).hexdigest() == term_hash
                       and TEMPLATES[index].split("{term}")[0] in row["reference"]
                       for row in heldout)
            ))
            self.assertTrue(all(
                row["challenge_tags"] == ["synthetic_vocab_seen_term_new_context"]
                for row in heldout
            ))
            # Expanding the template grid must not admit previously held-out
            # contexts to training when the frozen suite is supplied.
            connection = sqlite3.connect(source)
            for term_index in range(10):
                term = f"VocabTerm{term_index}"
                term_hash = hashlib.sha256(term.encode()).hexdigest()
                for template_index, template in enumerate(TEMPLATES[3:], 3):
                    for voice in ("voice_a", "voice_b"):
                        audio = root / f"{term_index}-{template_index}-{voice}.wav"
                        audio.write_bytes(f"audio:{term_index}:{template_index}:{voice}".encode())
                        identity = hashlib.sha256(str(audio).encode()).hexdigest()
                        connection.execute("INSERT INTO examples VALUES (?,?,?,?,?,?,?,?,?,?)", (
                            identity, str(audio), template.format(term=term), "test-pack", term_hash,
                            template_index, voice, 24000,
                            hashlib.sha256(audio.read_bytes()).hexdigest(), "synthetic fixture"))
            connection.commit(); connection.close()
            expanded = root / "expanded"
            result = subprocess.run([
                "python3", str(ROOT / "tools/split_v6_synthetic_vocab.py"),
                "--manifest", str(source), "--out-dir", str(expanded),
                "--strategy", "seen-term-context", "--freeze-heldout", str(out / "heldout.jsonl"),
                "--expected-terms", "10", "--expected-templates", "12", "--expected-voices", "2",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["frozen_example_ids"], 20)
            connection = sqlite3.connect(expanded / "train.sqlite3")
            expanded_ids = {row[0] for row in connection.execute("SELECT id FROM examples")}
            connection.close()
            self.assertFalse(expanded_ids & {row["example_id"] for row in heldout})


if __name__ == "__main__":
    unittest.main()
