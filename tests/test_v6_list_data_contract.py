"""Generated formatter labels must not infer list intent from enumeration."""
import importlib.util
from collections import Counter
from pathlib import Path
import unittest


def load(name):
    path = Path(__file__).resolve().parents[1] / "tools" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ListDataContractTest(unittest.TestCase):
    def test_generated_prose_and_requested_lists_have_grounded_targets(self):
        rows = load("build_v6_formatter_dataset").build(2000, 20261001)
        renderer = load("render_v6_edit_plan")
        prose = [r for r in rows if r["source"].startswith("I need ")]
        lists = [r for r in rows if r["structure"] == "UNORDERED_LIST"]
        self.assertTrue(prose)
        self.assertTrue(lists)
        for row in prose:
            self.assertEqual(row["structure"], "PROSE")
            self.assertNotIn("\n", row["target_text"])
        for row in prose + lists:
            self.assertEqual(renderer.render(row), row["target_text"])
        for row in lists:
            self.assertTrue(row["source"].startswith(("please list ", "make a list of ")))

    def test_balanced_control_buckets_are_unique_and_render_exactly(self):
        rows = load("build_v6_formatter_dataset").build(3000, 20261003)
        renderer = load("render_v6_edit_plan")
        counts = Counter(category for row in rows for category in row["metadata"]["categories"])
        self.assertEqual(len({row["source"].casefold() for row in rows}), len(rows))
        self.assertEqual(counts["question"], 240)
        self.assertEqual(counts["filler"], 360)
        self.assertEqual(counts["quoted-filler"], 120)
        self.assertEqual(counts["code-switching"], 150)
        self.assertTrue(all(renderer.render(row) == row["target_text"] for row in rows))

    def test_split_keeps_template_families_together_and_stratifies_buckets(self):
        rows = load("build_v6_formatter_dataset").build(3000, 20261003)
        splitter = load("split_v6_formatter_dataset")
        splits = splitter.grouped_splits(rows, "contract-test-seed")
        memberships = {}
        bucket_splits = {}
        for split, split_rows in splits.items():
            for row in split_rows:
                family = row["metadata"]["base_id"]
                if family in memberships:
                    self.assertEqual(memberships[family], split)
                else:
                    memberships[family] = split
                for category in row["metadata"]["categories"]:
                    bucket_splits.setdefault(category, set()).add(split)
        self.assertEqual(sum(map(len, splits.values())), len(rows))
        self.assertTrue(all(value == {"train", "dev", "test"} for value in bucket_splits.values()))


if __name__ == "__main__":
    unittest.main()
