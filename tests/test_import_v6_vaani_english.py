from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import types
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from tools.import_v6_vaani_english import (
    AUDITED_REVISION,
    checked_revision,
    mono_pcm16,
    record_for,
    write_audio,
)

ROOT = Path(__file__).resolve().parents[1]


class VaaniEnglishImportTest(unittest.TestCase):
    def test_audited_revision_is_full_commit_hash(self) -> None:
        self.assertEqual(len(checked_revision(AUDITED_REVISION)), 40)
        for invalid in ("main", "d2acadf", "A" * 40, "0" * 39):
            with self.assertRaises(ValueError):
                checked_revision(invalid)

    def test_audio_is_resampled_and_written_as_mono_pcm16(self) -> None:
        pcm = mono_pcm16([0.0] * 8000, 8000)
        self.assertEqual(len(pcm), 16000)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.wav"
            digest = write_audio(path, [0.0] * 8000, 8000)
            self.assertEqual(len(digest), 64)
            with wave.open(str(path), "rb") as handle:
                self.assertEqual((handle.getnchannels(), handle.getsampwidth(), handle.getframerate()),
                                 (1, 2, 16000))

    def test_manifest_record_keeps_only_training_fields(self) -> None:
        row = {"transcript": "A Vaani example.", "gender": "private",
               "district": "not retained", "speakerID": "must-not-leak"}
        record = record_for("train", 0, row, Path("/private/audio.wav"), "a" * 64,
                            AUDITED_REVISION)
        self.assertEqual(record["text"], row["transcript"])
        self.assertEqual(record["reference"], row["transcript"])
        self.assertEqual(record["license"], "CC BY 4.0")
        self.assertNotIn("gender", record)
        self.assertNotIn("district", record)
        self.assertNotIn("speakerID", record)

    def test_blank_transcript_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            record_for("train", 0, {"transcript": "  "}, Path("audio.wav"), "a" * 64,
                       AUDITED_REVISION)

    def test_no_dataset_access_without_explicit_terms_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "never-created"
            result = subprocess.run(
                ["python3", str(ROOT / "tools/import_v6_vaani_english.py"), "--out", str(out)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("accept the dataset's access terms", result.stderr)
            self.assertFalse(out.exists())

    def test_duplicate_audio_is_removed_and_every_staged_wav_is_manifested(self) -> None:
        from tools.import_v6_vaani_english import import_dataset

        def row(text: str, samples: list[float]) -> dict:
            return {"transcript": text, "audio": {"array": samples, "sampling_rate": 16000},
                    "district": "discarded metadata"}

        shared = [0.1] * 3200
        splits = {
            "train": [row("train once", shared), row("train duplicate", shared)],
            "validation": [row("validation", [0.2] * 3200)],
            "test": [row("test", [0.3] * 3200)],
        }
        fake_datasets = types.ModuleType("datasets")
        fake_datasets.load_dataset = lambda _dataset, _config, split, **_kwargs: iter(splits[split])
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "imported"
            with patch.dict(sys.modules, {"datasets": fake_datasets}):
                provenance = import_dataset(out, AUDITED_REVISION)
            manifests = [json.loads(line) for name in ("train", "validation", "test")
                         for line in (out / f"{name}.jsonl").read_text().splitlines()]
            referenced = {Path(record["audio_path"]).resolve() for record in manifests}
            staged = {path.resolve() for path in (out / "audio").rglob("*.wav")}
        self.assertEqual(provenance["counts"]["duplicate_train"], 1)
        self.assertEqual(len(manifests), 3)
        self.assertEqual(staged, referenced)


if __name__ == "__main__":
    unittest.main()
