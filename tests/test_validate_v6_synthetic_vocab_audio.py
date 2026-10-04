from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.validate_v6_synthetic_vocab_audio import count_untracked_audio


class SyntheticVocabularyAudioValidationTest(unittest.TestCase):
    def test_detects_audio_without_a_manifest_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio_dir = Path(directory) / "audio"
            audio_dir.mkdir()
            tracked = audio_dir / "tracked.wav"
            orphan = audio_dir / "orphan.wav"
            tracked.touch()
            orphan.touch()
            self.assertEqual(count_untracked_audio(audio_dir, {tracked}), 1)

    def test_accepts_a_fully_manifested_audio_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio_dir = Path(directory) / "audio"
            audio_dir.mkdir()
            tracked = audio_dir / "tracked.wav"
            tracked.touch()
            self.assertEqual(count_untracked_audio(audio_dir, {tracked}), 0)


if __name__ == "__main__":
    unittest.main()
