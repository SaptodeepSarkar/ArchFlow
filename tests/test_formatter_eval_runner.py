from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "pipelines/formatter/evaluate-v6-seq2seq-all.sh"


class FormatterEvalRunnerTests(unittest.TestCase):
    def test_gate_failures_do_not_skip_later_suites(self) -> None:
        false_command = shutil.which("false")
        bash = shutil.which("bash")
        self.assertIsNotNone(false_command)
        self.assertIsNotNone(bash)

        with tempfile.TemporaryDirectory(prefix="vaani-formatter-eval-runner-") as temp:
            root = Path(temp)
            synthetic = root / "synthetic"
            real = root / "real"
            model = root / "model"
            adapter = root / "adapter"
            for directory in (synthetic, real, model, adapter):
                directory.mkdir()
            (synthetic / "test.jsonl").write_text("{}\n", encoding="utf-8")
            (real / "test.jsonl").write_text("{}\n", encoding="utf-8")
            challenge = root / "challenge.jsonl"
            hard_eval = root / "hard-eval.jsonl"
            challenge.write_text("{}\n", encoding="utf-8")
            hard_eval.write_text("{}\n", encoding="utf-8")
            output = root / "reports"

            env = os.environ.copy()
            fake_python = root / "fake-python"
            fake_python.write_text(
                f"#!{sys.executable}\n"
                "import sys\n"
                "args = sys.argv[1:]\n"
                "if '--protocol' in args and args[args.index('--protocol') + 1] == 'v5':\n"
                "    if '--adapter' not in args:\n"
                "        raise SystemExit('missing trained V5 control')\n"
                f"    if args[args.index('--adapter') + 1] != {str(adapter)!r}:\n"
                "        raise SystemExit('wrong trained V5 control')\n"
                "    print('v5-control-adapter-ok')\n"
                "raise SystemExit(1)\n", encoding="utf-8",
            )
            fake_python.chmod(0o755)
            env["PYTHON"] = str(fake_python)
            result = subprocess.run(
                [
                    str(RUNNER),
                    "--synthetic-dir", str(synthetic),
                    "--real-dir", str(real),
                    "--challenge", str(challenge),
                    "--hard-eval", str(hard_eval),
                    "--model", str(model),
                    "--adapter", str(adapter),
                    "--v5-adapter", str(adapter),
                    "--out", str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Aggregate reports written", result.stdout)
        self.assertEqual(result.stdout.count("v5-control-adapter-ok"), 4)
        for suite in ("challenge", "hard-eval", "mixed-heldout-test", "real-test"):
            with self.subTest(suite=suite):
                self.assertIn(f"{suite}:v6-evaluation", result.stderr)
                self.assertIn(f"{suite}:v5-evaluation", result.stderr)
                self.assertIn(f"{suite}:comparison-input-missing", result.stderr)

    def test_both_wrappers_require_explicit_v5_control(self) -> None:
        for script in (RUNNER, REPO_ROOT / "pipelines/formatter/train-v6-seq2seq.sh"):
            with self.subTest(script=script.name):
                result = subprocess.run(["bash", str(script)], capture_output=True,
                                        text=True, check=False)
                self.assertEqual(result.returncode, 64)
                self.assertIn("--v5-adapter PATH", result.stderr)


if __name__ == "__main__":
    unittest.main()
