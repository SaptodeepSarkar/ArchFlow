"""Privacy-safe category aggregates for V6 formatter evaluations."""
from __future__ import annotations


def row_categories(row: dict) -> list[str]:
    metadata = row.get("metadata")
    metadata_values = metadata.get("categories") if isinstance(metadata, dict) else None
    label_values = row.get("labels")
    values: list[str] = []
    for group in (metadata_values, label_values):
        if isinstance(group, list):
            values.extend(group)
    source_tokens = row.get("source_tokens")
    token_labels = row.get("token_labels")
    if (isinstance(source_tokens, list) and isinstance(token_labels, list)
            and source_tokens and len(source_tokens) == len(token_labels)):
        values.append(f"source_length:{len(source_tokens)}")
        for index, label in enumerate(token_labels):
            if not isinstance(label, str) or label == "KEEP":
                continue
            values.append(f"edit:{label}")
            relative_position = index / len(token_labels)
            position = ("beginning" if relative_position < 0.25 else
                        "ending" if relative_position >= 0.75 else "middle")
            values.append(f"edit_position:{label}:{position}")
    if not values:
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
