from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import stage_v6_monsoon_eval as stage


class MonsoonStageTests(unittest.TestCase):
    def test_only_audio_and_reference_are_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            out = root / "staged"
            source = {
                "id": "raw-id-must-not-persist",
                "audio": {"path": "private-looking.wav", "bytes": b"RIFF" + b"x" * 32},
                "text": "A technical reference sentence.",
                "speaker_id": 123,
                "date_of_birth": "private-demographic-sentinel",
                "native_district": "private-location-sentinel",
                "device_model": "private-device-sentinel",
                "audio_length_s": 1.0,
            }
            rows = [dict(source, audio=dict(source["audio"])) for _ in range(2_102)]
            summary = stage.stage_rows(rows, out)
            self.assertEqual(summary["rows"], 2_102)
            serialized = "\n".join(path.read_text(encoding="utf-8")
                                     for path in (out / "manifest.jsonl", out / "provenance.json"))
            self.assertIn("A technical reference sentence.", serialized)
            self.assertNotIn("raw-id-must-not-persist", serialized)
            self.assertNotIn("private-demographic-sentinel", serialized)
            self.assertNotIn("private-location-sentinel", serialized)
            self.assertNotIn("private-device-sentinel", serialized)
            self.assertNotIn("speaker_id", serialized)
            rows_out = [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows_out), 2_102)
            self.assertEqual(rows_out[0]["audio"]["sha256"], rows_out[-1]["audio"]["sha256"])
            self.assertTrue((out / rows_out[0]["audio"]["ref"]).is_file())

    def test_audio_extension_detects_common_formats(self):
        self.assertEqual(stage.audio_extension(None, b"RIFFxxxx"), ".wav")
        self.assertEqual(stage.audio_extension(None, b"fLaCxxxx"), ".flac")
        self.assertEqual(stage.audio_extension("voice.mp3", b"ID3xxx"), ".mp3")


if __name__ == "__main__":
    unittest.main()
