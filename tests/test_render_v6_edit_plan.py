import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "render_v6_edit_plan.py"
SPEC = importlib.util.spec_from_file_location("render_v6_edit_plan_lists", SCRIPT)
RENDERER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RENDERER)


class UnorderedListRendererTest(unittest.TestCase):
    def plan(self, source, target):
        tokens = source.split()
        return {
            "source_tokens": tokens,
            "token_labels": ["KEEP"] * len(tokens),
            "punctuation_after": {"1": "COLON"},
            "structure": "UNORDERED_LIST",
            "target_text": target,
        }

    def test_generator_list_lead_ins_render_without_inventing_items(self):
        cases = [
            ("please list eggs milk bread", "Please list:\n- Eggs\n- Milk\n- Bread"),
            ("make a list of eggs milk bread", "Make a list:\n- Eggs\n- Milk\n- Bread"),
        ]
        for source, target in cases:
            with self.subTest(source=source):
                self.assertEqual(RENDERER.render(self.plan(source, target)), target)

    def test_ordinary_need_sentence_stays_prose_even_with_list_prediction(self):
        plan = self.plan("I need eggs milk bread and coffee", "I need eggs, milk, bread and coffee.")
        plan["punctuation_after"] = {"2": "COMMA", "3": "COMMA", "6": "PERIOD"}
        self.assertEqual(RENDERER.render(plan), plan["target_text"])

    def test_unrecognized_list_lead_in_does_not_create_a_list(self):
        plan = self.plan("eggs milk bread", "Eggs milk bread")
        plan["punctuation_after"] = {}
        self.assertEqual(RENDERER.render(plan), "Eggs milk bread")


if __name__ == "__main__":
    unittest.main()
