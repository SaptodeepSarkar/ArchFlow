from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.import_v6_mdc_common_voice import convert_mp3


class ImportV6MdcCommonVoiceTest(unittest.TestCase):
    def test_failed_decode_removes_partial_wav(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp3"
            destination = root / "out.wav"
            source.touch()

            def failed_decode(command, **_kwargs):
                Path(command[-1]).write_bytes(b"partial wav")
                return SimpleNamespace(returncode=1)

            with patch("tools.import_v6_mdc_common_voice.subprocess.run", failed_decode):
                with self.assertRaisesRegex(ValueError, "audio decode failed"):
                    convert_mp3(source, destination)
            self.assertFalse(destination.exists())

    def test_invalid_pcm_output_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mp3"
            destination = root / "out.wav"
            source.touch()

            def invalid_decode(command, **_kwargs):
                Path(command[-1]).write_bytes(b"not a wav")
                return SimpleNamespace(returncode=0)

            with patch("tools.import_v6_mdc_common_voice.subprocess.run", invalid_decode):
                with self.assertRaisesRegex(ValueError, "audio decode failed or output"):
                    convert_mp3(source, destination)
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
