import importlib.util
from pathlib import Path
import unittest
import json
import tempfile


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "build_v6_hard_examples.py"
SPEC = importlib.util.spec_from_file_location("build_v6_hard_examples", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
RENDER_SPEC = importlib.util.spec_from_file_location(
    "render_v6_edit_plan", Path(__file__).resolve().parents[1] / "tools" / "render_v6_edit_plan.py"
)
RENDERER = importlib.util.module_from_spec(RENDER_SPEC)
assert RENDER_SPEC.loader is not None
RENDER_SPEC.loader.exec_module(RENDERER)


class HardExamplesTest(unittest.TestCase):
    def test_targeted_filler_quota_keeps_short_middle_examples(self):
        rows = MODULE.build(1000, categories={"filler-context"})
        self.assertTrue(rows)
        self.assertTrue(all(row["metadata"]["categories"] == ["filler-context"] for row in rows))
        self.assertTrue(any(len(row["source_tokens"]) <= 6 and
                            row["token_labels"].index("DELETE_FILLER") > 0 for row in rows))
        self.assertTrue(all(RENDERER.render(row) == row["target_text"] for row in rows))

    def test_foundation_exclusions_cannot_silently_leak(self):
        row = MODULE.build(1, categories={"filler-context"})[0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "heldout.jsonl"
            path.write_text(json.dumps({"source": {"type": "synthetic"},
                                        "utterance": {"raw_stt": row["source"]}}) + "\n")
            excluded = MODULE.read_excluded_sources([path])
            replay = MODULE.build(1000, excluded, {"filler-context"})
            self.assertNotIn(row["source"].casefold(), {r["source"].casefold() for r in replay})
            path.write_text(json.dumps({"utterance": {}}) + "\n")
            with self.assertRaises(ValueError):
                MODULE.read_excluded_sources([path])

    def test_exclusions_are_applied_before_quota_and_rows_stay_unique(self):
        initial = MODULE.build(2000)
        excluded = {row["source"].casefold() for row in initial[:372]}
        rows = MODULE.build(2000, excluded)
        sources = [row["source"].casefold() for row in rows]
        self.assertTrue(rows)
        self.assertEqual(len(sources), len(set(sources)))
        self.assertFalse(set(sources) & excluded)
        self.assertTrue(any("cue-preservation" in row["metadata"]["categories"] for row in rows))
        self.assertTrue(any("explicit-repair" in row["metadata"]["categories"] for row in rows))

    def test_generated_rows_have_aligned_labels_and_supported_heads(self):
        rows = MODULE.build(2000)
        for row in rows:
            self.assertEqual(len(row["source_tokens"]), len(row["token_labels"]))
            self.assertTrue(set(row["token_labels"]) <= set(MODULE.__dict__.get("TOKEN_LABELS", {
                "KEEP", "DELETE_FILLER", "DELETE_FALSE_START", "DELETE_RETRACTED", "CAPITALIZE", "NORMALIZE_ALLOWED"})))
            self.assertIn(row["structure"], {"PROSE", "UNORDERED_LIST", "ORDERED_LIST"})
        self.assertTrue(all(RENDERER.render(row) == row["target_text"] for row in rows))


if __name__ == "__main__":
    unittest.main()
