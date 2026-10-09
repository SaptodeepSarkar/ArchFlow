import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().with_name("capture_android_screens.py")
SPEC = importlib.util.spec_from_file_location("capture_android_screens", MODULE_PATH)
capture_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = capture_module
SPEC.loader.exec_module(capture_module)


class CaptureAndroidScreensPrivacyTest(unittest.TestCase):
    def test_metadata_omits_device_identifiers_and_full_output_path(self):
        png = bytearray(24)
        png[:8] = b"\x89PNG\r\n\x1a\n"
        png[12:16] = b"IHDR"
        png[16:24] = (320).to_bytes(4, "big") + (640).to_bytes(4, "big")

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "screenshot.png"
            device = capture_module.Device("192.0.2.10:5555", "model:private-device", "phone")
            with patch.object(capture_module, "adb", return_value=bytes(png)):
                record = capture_module.capture(device, output)

        self.assertEqual(record, {
            "role": "phone",
            "file": "screenshot.png",
            "width": 320,
            "height": 640,
        })


if __name__ == "__main__":
    unittest.main()
