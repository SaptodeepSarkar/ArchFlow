from __future__ import annotations

import unittest

from tools.v6_eval_aggregate import add_category_result, category_report, row_categories


class V6EvaluationAggregateTest(unittest.TestCase):
    def test_categories_are_deduplicated_and_missing_tags_are_explicit(self) -> None:
        self.assertEqual(row_categories({"metadata": {"categories": [" repair ", "repair", "filler"]}}),
                         ["filler", "repair"])
        self.assertEqual(row_categories({"metadata": {"categories": []}}), ["uncategorized"])
        self.assertEqual(row_categories({}), ["uncategorized"])

    def test_foundation_schema_labels_are_included_with_categories(self) -> None:
        row = {"metadata": {"categories": ["filler"]},
               "labels": [" real_derived ", "meaning_preservation", "filler"]}
        self.assertEqual(row_categories(row),
                         ["filler", "meaning_preservation", "real_derived"])
        self.assertEqual(row_categories({"labels": ["real_derived"]}), ["real_derived"])

    def test_aligned_token_edits_add_length_and_position_slices(self) -> None:
        row = {"metadata": {"categories": ["filler-context"]},
               "source_tokens": ["x"] * 8,
               "token_labels": ["KEEP", "DELETE_FILLER"] + ["KEEP"] * 6}
        self.assertEqual(row_categories(row), [
            "edit:DELETE_FILLER", "edit_position:DELETE_FILLER:beginning",
            "filler-context", "source_length:8",
        ])

    def test_reports_only_aggregate_counts_and_rates(self) -> None:
        groups: dict[str, dict[str, int]] = {}
        row = {"metadata": {"categories": ["repair", "meaning"]},
               "source": "private input", "target_text": "private target"}
        add_category_result(
            groups, row, exact=False, normalized_exact=True,
            copy_guard_fallback=True, novel_content_tokens=0,
            missing_target_content_tokens=0, token_order_violation=True,
        )
        report = category_report(groups)
        self.assertEqual(report["repair"]["rows"], 1)
        self.assertEqual(report["repair"]["exact_rate"], 0.0)
        self.assertEqual(report["meaning"]["normalized_exact_rate"], 1.0)
        self.assertEqual(report["meaning"]["copy_guard_fallbacks"], 1)
        self.assertEqual(report["meaning"]["token_order_violations"], 1)
        serialized = repr(report)
        self.assertNotIn("private input", serialized)
        self.assertNotIn("private target", serialized)


if __name__ == "__main__":
    unittest.main()
