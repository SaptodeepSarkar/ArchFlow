from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "training/cleanup-llm/scripts"))
from formatter_protocol import (  # noqa: E402
    IN_TAG, OUT_TAG, SYSTEM_V5, adapter_has_trainable_token_rows, content_tokens,
    align_token_embeddings, max_new_tokens_v5, max_new_tokens_v6,
    prompt_v5, prompt_v6,
    v6_missing_target_content_tokens, v6_requires_copy_fallback,
    v6_unsupported_content_tokens,
)


class FormatterProtocolTest(unittest.TestCase):
    def test_vocab_padding_is_preserved_unless_adapter_saves_token_rows(self) -> None:
        class Model:
            def __init__(self):
                self.rows = 151936

            def get_input_embeddings(self):
                return SimpleNamespace(weight=SimpleNamespace(shape=(self.rows, 8)))

            def resize_token_embeddings(self, size):
                self.rows = size

        class Tokenizer:
            def __len__(self):
                return 151671

        model = Model()
        align_token_embeddings(model, Tokenizer())
        self.assertEqual(model.rows, 151936)
        align_token_embeddings(model, Tokenizer(), force=True)
        self.assertEqual(model.rows, 151671)

    def test_token_row_detection_comes_from_local_peft_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "adapter_config.json"
            config.write_text(json.dumps({"trainable_token_indices": [1, 2]}), encoding="utf-8")
            self.assertTrue(adapter_has_trainable_token_rows(directory))
            config.write_text(json.dumps({"trainable_token_indices": None}), encoding="utf-8")
            self.assertFalse(adapter_has_trainable_token_rows(directory))

    def test_v6_copy_guard_falls_back_on_additions_or_deleted_negation(self) -> None:
        self.assertFalse(v6_requires_copy_fallback(
            "please do not restart service", "Please do not restart service."
        ))
        self.assertTrue(v6_requires_copy_fallback(
            "restart service", "Please restart the service now."
        ))
        self.assertTrue(v6_requires_copy_fallback(
            "Alice gave Bob the file", "Bob gave Alice the file."
        ))
        self.assertTrue(v6_requires_copy_fallback(
            "do not restart service", "Restart service."
        ))
        self.assertTrue(v6_requires_copy_fallback(
            "no, no, keep 10.5 seconds", "No, keep seconds."
        ))
        self.assertFalse(v6_requires_copy_fallback(
            "keep 10.5 seconds", "Keep 10.5 seconds."
        ))

    def test_copy_guard_allows_only_source_grounded_ordered_list_indices(self) -> None:
        self.assertFalse(v6_requires_copy_fallback(
            "first launch the app, second save the log",
            "1. Launch the app.\n2. Save the log."
        ))
        self.assertEqual(v6_unsupported_content_tokens(
            "first launch the app, second save the log",
            "1. Launch the app.\n2. Save the log."
        ), set())
        self.assertTrue(v6_requires_copy_fallback(
            "launch the app, then save the log",
            "1. Launch the app.\n2. Save the log."
        ))
        self.assertTrue(v6_requires_copy_fallback(
            "first save version 10, second save version 20",
            "1. Save version 10.\n2. Save version 21."
        ))
        self.assertTrue(v6_requires_copy_fallback(
            "first launch, second save, third exit",
            "1. Launch.\n3. Exit."
        ))

    def test_copy_guard_allows_only_bounded_spelling_and_letter_sequence_repairs(self) -> None:
        self.assertFalse(v6_requires_copy_fallback("ants", "ands"))
        self.assertFalse(v6_requires_copy_fallback("grammer", "grammar"))
        self.assertFalse(v6_requires_copy_fallback("u r l", "URL"))
        self.assertTrue(v6_requires_copy_fallback("I T", "it"))
        self.assertFalse(v6_requires_copy_fallback("I T", "IT"))
        self.assertFalse(v6_requires_copy_fallback("hyper land", "Hyprland"))
        self.assertTrue(v6_requires_copy_fallback("ants", "birds"))
        self.assertTrue(v6_requires_copy_fallback("ant", "art"))
        self.assertTrue(v6_requires_copy_fallback("restart service", "restart services"))

    def test_gold_evaluation_detects_deleted_content_and_allows_bounded_variants(self) -> None:
        self.assertEqual(v6_missing_target_content_tokens("I need coffee", "I need"), ["coffee"])
        self.assertEqual(v6_missing_target_content_tokens(
            "Keep the very very clear wording", "Keep the very clear wording"
        ), ["very"])
        self.assertEqual(v6_missing_target_content_tokens("Fix the grammar", "Fix the grammer"), [])
        self.assertEqual(v6_missing_target_content_tokens("Copy the URL", "Copy the U R L"), [])

    def test_unicode_content_and_hindi_negation_are_guarded(self) -> None:
        # Keep combining vowel marks attached to their Devanagari word.
        self.assertEqual(content_tokens("मैं नहीं जाऊँगा"), ["मैं", "नहीं", "जाऊँगा"])
        self.assertTrue(v6_requires_copy_fallback("मैं नहीं जाऊँगा", "मैं जाऊँगा"))
        self.assertTrue(v6_requires_copy_fallback("किताब चाहिए", "किताब सही है"))
        self.assertEqual(v6_missing_target_content_tokens(
            "मुझे किताब चाहिए", "मुझे चाहिए"
        ), ["किताब"])

    def test_unicode_digits_are_protected_as_numbers(self) -> None:
        self.assertTrue(v6_requires_copy_fallback("मुझे १२.५ किलो चाहिए", "मुझे १२ किलो चाहिए"))

    def test_fixed_v6_protocol_is_plain_text_and_bounded(self) -> None:
        self.assertEqual(prompt_v6("make it clear"), f"{IN_TAG}\nmake it clear\n{OUT_TAG}\n")
        self.assertEqual(max_new_tokens_v6(0), 32)
        self.assertEqual(max_new_tokens_v6(40), 80)
        self.assertEqual(max_new_tokens_v6(300), 192)

    def test_v5_protocol_matches_the_production_chat_template(self) -> None:
        result = prompt_v5("preserve this claim")
        self.assertIn(f"<|im_start|>system\n{SYSTEM_V5}<|im_end|>\n", result)
        self.assertTrue(result.endswith(
            "<|im_start|>user\npreserve this claim<|im_end|>\n<|im_start|>assistant\n"
        ))
        self.assertEqual(max_new_tokens_v5("x"), 64)
        self.assertEqual(max_new_tokens_v5("x" * 400), 512)


if __name__ == "__main__":
    unittest.main()
