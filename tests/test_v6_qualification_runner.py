"""Exercise suite orchestration without loading weights or claiming accuracy."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "pipelines/formatter/evaluate-v6-seq2seq-all.sh"


class QualificationRunnerTest(unittest.TestCase):
    def test_runs_all_suites_after_failure_and_preserves_reports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            (data / "test.jsonl").write_text("{}\n")
            fixture = root / "fixture.jsonl"
            fixture.write_text("{}\n")
            fake = root / "fake-python"
            fake.write_text('''#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv[1:]
report = pathlib.Path(args[args.index("--report") + 1])
report.write_text(json.dumps({"fixture_only": True}))
raise SystemExit(1 if report.name == "comparison-challenge.json" else 0)
''')
            fake.chmod(0o755)
            output = root / "reports"
            command = ["bash", str(RUNNER), "--synthetic-dir", str(data),
                       "--real-dir", str(data), "--challenge", str(fixture),
                       "--hard-eval", str(fixture), "--independent-challenge", str(fixture), "--model", str(data),
                       "--adapter", str(data), "--v5-adapter", str(data),
                       "--out", str(output)]
            env = {**os.environ, "PYTHON": str(fake)}
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            reports = list(output.glob("*.json"))
            self.assertEqual(len(reports), 15)
            self.assertTrue((output / "comparison-real-test.json").exists())
            before = {path.name: path.read_bytes() for path in reports}
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 73, result.stderr)
            self.assertEqual(before, {path.name: path.read_bytes() for path in reports})

    def test_rejects_missing_test_split_before_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / "fixture.jsonl"
            fixture.write_text("{}\n")
            output = root / "reports"
            command = ["bash", str(RUNNER), "--synthetic-dir", str(root),
                       "--real-dir", str(root), "--challenge", str(fixture),
                       "--hard-eval", str(fixture), "--independent-challenge", str(fixture), "--model", str(root),
                       "--adapter", str(root), "--v5-adapter", str(root),
                       "--out", str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 66)
            self.assertFalse(output.exists())
