"""Privacy-safe category aggregates for V6 formatter evaluations."""
from __future__ import annotations


def row_categories(row: dict) -> list[str]:
    metadata = row.get("metadata")
    values = metadata.get("categories") if isinstance(metadata, dict) else None
    if not isinstance(values, list):
        return ["uncategorized"]
    categories = sorted({value.strip() for value in values
                         if isinstance(value, str) and value.strip()})
    return categories or ["uncategorized"]


def add_category_result(
    groups: dict[str, dict[str, int]],
    row: dict,
    *,
    exact: bool,
    normalized_exact: bool,
    copy_guard_fallback: bool,
    novel_content_tokens: int,
    missing_target_content_tokens: int,
    token_order_violation: bool,
) -> None:
    """Accumulate counts only; never retain source, target, or generated text."""
    for category in row_categories(row):
        metrics = groups.setdefault(category, {
            "rows": 0,
            "exact_matches": 0,
            "normalized_exact_matches": 0,
            "copy_guard_fallbacks": 0,
            "novel_content_tokens": 0,
            "outputs_with_novel_content": 0,
            "missing_target_content_tokens": 0,
            "outputs_missing_target_content": 0,
            "token_order_violations": 0,
        })
        metrics["rows"] += 1
        metrics["exact_matches"] += int(exact)
        metrics["normalized_exact_matches"] += int(normalized_exact)
        metrics["copy_guard_fallbacks"] += int(copy_guard_fallback)
        metrics["novel_content_tokens"] += novel_content_tokens
        metrics["outputs_with_novel_content"] += int(novel_content_tokens > 0)
        metrics["missing_target_content_tokens"] += missing_target_content_tokens
        metrics["outputs_missing_target_content"] += int(missing_target_content_tokens > 0)
        metrics["token_order_violations"] += int(token_order_violation)


def category_report(groups: dict[str, dict[str, int]]) -> dict[str, dict[str, int | float]]:
    report = {}
    for category, counts in sorted(groups.items()):
        rows = counts["rows"]
        report[category] = {
            **counts,
            "exact_rate": counts["exact_matches"] / rows,
            "normalized_exact_rate": counts["normalized_exact_matches"] / rows,
            "copy_guard_fallback_rate": counts["copy_guard_fallbacks"] / rows,
        }
    return report
