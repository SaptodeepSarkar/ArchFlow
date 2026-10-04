import importlib.util
from pathlib import Path
import unittest


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
