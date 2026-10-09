"""Regression tests for multilingual STT evaluation normalization/configuration."""
import importlib.util
from pathlib import Path
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "eval_v5_whisper_adapter.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("eval_v6_whisper_adapter", SCRIPT)
EVALUATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(EVALUATOR)


class WhisperLanguageEvaluationTest(unittest.TestCase):
    def test_auto_language_maps_to_detection_without_changing_default(self):
        self.assertIsNone(EVALUATOR.resolve_language("auto"))
        self.assertEqual(EVALUATOR.resolve_language("english"), "english")
        self.assertEqual(EVALUATOR.resolve_language("Hindi"), "Hindi")
        with self.assertRaises(ValueError):
            EVALUATOR.resolve_language("  ")

    def test_normalization_preserves_devanagari_letters_and_marks(self):
        reference = "कृपया मॉडल को जाँचें।"
        self.assertEqual(EVALUATOR.norm(reference), "कृपया मॉडल को जाँचें")
        self.assertEqual(EVALUATOR.tokens(reference), ["कृपया", "मॉडल", "को", "जाँचें"])

    def test_ascii_english_normalization_remains_stable(self):
        self.assertEqual(EVALUATOR.norm("I'm testing, V6!"), "i'm testing v6")


if __name__ == "__main__":
    unittest.main()
