from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools.eval_v6_android_stt_export import require_complete_decodes, sha256_file


class EvalV6AndroidSttExportTest(unittest.TestCase):
    def test_model_hash_matches_streaming_sha256(self) -> None:
        payload = b"whisper model bytes" * 100_000
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.bin"
            model.write_bytes(payload)
            self.assertEqual(sha256_file(model), hashlib.sha256(payload).hexdigest())

    def test_complete_evaluation_requires_every_requested_decode(self) -> None:
        require_complete_decodes({
            "rows_requested": 100,
            "rows_decoded": 100,
            "decode_failures": 0,
        })
        for report in (
            {"rows_requested": 100, "rows_decoded": 99, "decode_failures": 1},
            {"rows_requested": 100, "rows_decoded": 100, "decode_failures": 1},
            {"rows_requested": 0, "rows_decoded": 0, "decode_failures": 0},
            {"rows_requested": True, "rows_decoded": 1, "decode_failures": 0},
            {"rows_requested": 100, "rows_decoded": 100},
        ):
            with self.subTest(report=report), self.assertRaisesRegex(ValueError, "decode failures"):
                require_complete_decodes(report)


if __name__ == "__main__":
    unittest.main()
