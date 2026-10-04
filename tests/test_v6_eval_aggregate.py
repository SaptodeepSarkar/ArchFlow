from __future__ import annotations

import unittest

from tools.v6_eval_aggregate import add_category_result, category_report, row_categories


class V6EvaluationAggregateTest(unittest.TestCase):
    def test_categories_are_deduplicated_and_missing_tags_are_explicit(self) -> None:
        self.assertEqual(row_categories({"metadata": {"categories": [" repair ", "repair", "filler"]}}),
                         ["filler", "repair"])
        self.assertEqual(row_categories({"metadata": {"categories": []}}), ["uncategorized"])
        self.assertEqual(row_categories({}), ["uncategorized"])

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
