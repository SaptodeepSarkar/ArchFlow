import json
from pathlib import Path
import tempfile
import unittest
from tools.v6_stt_run_manifest import run_identity, verify_or_create


class RunManifestTest(unittest.TestCase):
    def test_changed_audio_model_code_settings_and_missing_checkpoint_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "audio.wav"
            audio.write_bytes(b"audio fixture")
            data = root / "train.jsonl"
            data.write_text(json.dumps({"audio_path": str(audio), "text": "fixture"}) + "\n")
            model = root / "model"
            model.mkdir()
            weights = model / "model.safetensors"
            weights.write_bytes(b"weights fixture")
            code = root / "trainer.py"
            code.write_text("fixture")
            identity = lambda settings=["--steps", "10"]: run_identity([data], [], model, [code], settings)
            original = identity()
            out = root / "run"
            verify_or_create(out, original)
            with self.assertRaises(ValueError):
                verify_or_create(out, original)
            checkpoint = out / "checkpoint-5"
            checkpoint.mkdir()
            with self.assertRaises(ValueError):
                verify_or_create(out, original, checkpoint)
            for name in ("trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth", "adapter_model.safetensors"):
                (checkpoint / name).write_bytes(b"fixture")
            verify_or_create(out, identity(), checkpoint)
            for path in (audio, weights, code, data):
                before = path.read_bytes()
                path.write_bytes(before + b" ")
                with self.subTest(path=path.name), self.assertRaises(ValueError):
                    verify_or_create(out, identity(), checkpoint)
                path.write_bytes(before)
            with self.assertRaises(ValueError):
                verify_or_create(out, identity(["--steps", "11"]), checkpoint)
            self.assertEqual(original["audio_files"], 1)
            self.assertNotIn("text", original)
