import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from v6_real_alignment import TOKEN_RE, build_plan, validate_auto_row
from auto_label_v6_real_derived import auto_labels
from train_v6_edit_tagger import TOKEN_RE as TAGGER_TOKEN_RE


class RealAlignmentTest(unittest.TestCase):
    def test_shared_tokenizer_separates_terminal_periods_but_keeps_versions(self):
        expected = ["URL", ".", "Build", "v1.2.3", "."]
        self.assertEqual(TOKEN_RE.findall("URL. Build v1.2.3."), expected)
        self.assertEqual(TAGGER_TOKEN_RE.findall("URL. Build v1.2.3."), expected)

    def test_exact_words_allow_casing_and_punctuation_only(self):
        plan = build_plan("i need the URL", "I need the URL.")
        self.assertIsNotNone(plan)
        self.assertEqual(plan["target_text"], "I need the URL.")
        self.assertEqual(set(plan["token_labels"]), {"KEEP"})

    def test_keeps_quoted_or_discussed_filler_tokens(self):
        plan = build_plan('the word "um" is in the transcript', 'The word "um" is in the transcript.')
        self.assertIsNotNone(plan)
        self.assertIn("um", plan["target_text"].casefold())
        self.assertEqual(set(plan["token_labels"]), {"KEEP"})

    def test_rejects_any_lexical_mismatch_instead_of_rewriting(self):
        self.assertIsNone(build_plan("i need the module", "I need the model."))
        self.assertIsNone(build_plan("uh i need the URL", "I need the URL."))
        self.assertIsNone(build_plan("i am not ready", "I am ready."))
        self.assertIsNone(build_plan("i need the model twice twice", "I need the model twice."))

    def test_automated_real_row_is_recomputed_not_trusted_by_metadata(self):
        plan = build_plan("i need the URL", "I need the URL.")
        row = {
            "source": {"type": "real_derived"},
            "annotation": {
                "method": "reference-grounded-deterministic-validator",
                "validator": "v6-real-lexical-alignment-v1",
            },
            "utterance": {"raw_stt": "i need the URL", "reference_transcript": "I need the URL.",
                          "clean_target": plan["target_text"]},
            **plan,
        }
        self.assertTrue(validate_auto_row(row))
        row["token_labels"][0] = "DELETE_FILLER"
        self.assertFalse(validate_auto_row(row))

    def test_automated_rows_never_inherit_a_human_review_claim(self):
        labels = auto_labels(["human_reviewed", "formatter_target_unreviewed", "dataset_tag"])
        self.assertNotIn("human_reviewed", labels)
        self.assertNotIn("formatter_target_unreviewed", labels)
        self.assertIn("auto_reference_aligned", labels)


if __name__ == "__main__":
    unittest.main()
