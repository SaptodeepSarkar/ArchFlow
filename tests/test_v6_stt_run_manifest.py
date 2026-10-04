import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
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

    def test_cpu_preflight_does_not_start_training(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio = root / "fixture.wav"
            audio.write_bytes(b"hash fixture, not acoustic validation")
            data = root / "train.jsonl"
            data.write_text(json.dumps({"audio_path": str(audio), "text": "fixture"}) + "\n")
            model = root / "model"
            model.mkdir()
            (model / "config.json").write_text("{}")
            out = root / "run"
            script = Path(__file__).resolve().parents[1] / "tools/train_v6_stt.py"
            result = subprocess.run([sys.executable, str(script), "--preflight-only",
                                     "--pre-split", "--streaming", "--manifest", str(data),
                                     "--model", str(model), "--out", str(out)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)["training_started"])
            identity = json.loads((out / "v6-run-manifest.json").read_text())
            self.assertNotIn("--preflight-only", identity["settings"])
            self.assertEqual(list(out.iterdir()), [out / "v6-run-manifest.json"])
