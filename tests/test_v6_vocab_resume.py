import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_v6_synthetic_vocab_audio import verify_resume_clip


class ResumeIntegrityTest(unittest.TestCase):
    def test_verified_clip_and_changed_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture.wav"
            output.write_bytes(b"fixture")
            digest = hashlib.sha256(b"fixture").hexdigest()
            metadata = {"model_sha256": "model", "voice_asset_sha256": "voice", "speed": 1.0}
            row = ("fixture target", digest, json.dumps(metadata))
            verify_resume_clip(row, output, "fixture target", "model", "voice")
            for target, model, voice in (("changed", "model", "voice"),
                                         ("fixture target", "changed", "voice"),
                                         ("fixture target", "model", "changed")):
                with self.subTest(target=target, model=model, voice=voice):
                    with self.assertRaises(SystemExit):
                        verify_resume_clip(row, output, target, model, voice)
            output.write_bytes(b"corrupt")
            with self.assertRaises(SystemExit):
                verify_resume_clip(row, output, "fixture target", "model", "voice")
