#!/usr/bin/env python3
"""Gate a V6 formatter against V5 on paired aggregate-only reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "rows", "source_set_sha256", "exact_rate", "normalized_exact_rate",
        "novel_content_tokens", "outputs_with_novel_content",
        "missing_target_content_tokens", "outputs_missing_target_content",
    }
    if missing := required - report.keys():
        raise SystemExit(f"{path}: missing aggregate fields {sorted(missing)}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v5", type=Path, required=True)
    parser.add_argument("--v6", type=Path, required=True)
    parser.add_argument("--suite", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-copy-fallback-rate", type=float)
    args = parser.parse_args()
    v5, v6 = load(args.v5), load(args.v6)
    if v5["rows"] != v6["rows"] or v5["source_set_sha256"] != v6["source_set_sha256"]:
        raise SystemExit("V5 and V6 reports do not cover the same ordered source set")
    for field in ("target_set_sha256", "base_model_sha256", "evaluation_code_sha256",
                  "protocol_code_sha256"):
        if not v5.get(field) or v5.get(field) != v6.get(field):
            raise SystemExit(f"V5 and V6 reports lack matching {field}")
    if (v5.get("protocol") != "v5" or v6.get("protocol") != "v6"
            or not v5.get("adapter_sha256") or not v6.get("adapter_sha256")):
        raise SystemExit("paired qualification requires trained V5 and V6 adapter provenance")
    exact_delta = v6["exact_rate"] - v5["exact_rate"]
    normalized_delta = v6["normalized_exact_rate"] - v5["normalized_exact_rate"]
    fallback_count = v6.get("copy_guard_fallbacks", 0)
    # Raw generations can be unsafe when the protocol correctly falls back to
    # the unchanged source. Require every aggregate raw violation type to be
    # covered by a fallback, then gate the delivered output itself below.
    raw_violations_covered = all(
        v6.get(field, 0) <= fallback_count
        for field in (
            "raw_missing_protected_tokens",
            "raw_token_order_violations",
        )
    )
    meaning_safe = (
        v6["novel_content_tokens"] == 0
        and v6["outputs_with_novel_content"] == 0
        and v6["missing_target_content_tokens"] == 0
        and v6["outputs_missing_target_content"] == 0
        and raw_violations_covered
    )
    fallback_rate = v6.get("copy_guard_fallbacks", 0) / v6["rows"]
    fallback_safe = (
        args.max_copy_fallback_rate is None
        or fallback_rate <= args.max_copy_fallback_rate
    )
    output = {
        "suite": args.suite,
        "rows": v5["rows"],
        "source_set_sha256": v5["source_set_sha256"],
        "target_set_sha256": v5["target_set_sha256"],
        "base_model_sha256": v5["base_model_sha256"],
        "v5_adapter_sha256": v5["adapter_sha256"],
        "v6_adapter_sha256": v6["adapter_sha256"],
        "evaluation_code_sha256": v5["evaluation_code_sha256"],
        "protocol_code_sha256": v5["protocol_code_sha256"],
        "v5_exact_rate": v5["exact_rate"],
        "v6_exact_rate": v6["exact_rate"],
        "exact_rate_delta": exact_delta,
        "v5_normalized_exact_rate": v5["normalized_exact_rate"],
        "v6_normalized_exact_rate": v6["normalized_exact_rate"],
        "normalized_exact_rate_delta": normalized_delta,
        "v5_novel_content_tokens": v5["novel_content_tokens"],
        "v5_outputs_with_novel_content": v5["outputs_with_novel_content"],
        "v6_novel_content_tokens": v6["novel_content_tokens"],
        "v6_outputs_with_novel_content": v6["outputs_with_novel_content"],
        "v6_missing_target_content_tokens": v6["missing_target_content_tokens"],
        "v6_outputs_missing_target_content": v6["outputs_missing_target_content"],
        "v6_raw_missing_protected_tokens": v6.get("raw_missing_protected_tokens", 0),
        "v6_raw_token_order_violations": v6.get("raw_token_order_violations", 0),
        "v6_copy_guard_fallbacks": fallback_count,
        "raw_violations_covered_by_fallbacks": raw_violations_covered,
        "v6_copy_guard_fallback_rate": fallback_rate,
        "max_copy_fallback_rate": args.max_copy_fallback_rate,
        "meaning_preservation_gate": meaning_safe,
        "gold_target_content_gate": (
            v6["missing_target_content_tokens"] == 0
            and v6["outputs_missing_target_content"] == 0
        ),
        "fallback_rate_gate": fallback_safe,
        "promotion_eligible": meaning_safe and fallback_safe and exact_delta >= 0,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, sort_keys=True))
    # This command is used as a pipeline gate, not just a report generator.
    # A machine-readable ineligible report must also fail the process so
    # `set -e` callers cannot mistake a rejected candidate for a green run.
    raise SystemExit(0 if output["promotion_eligible"] else 1)


if __name__ == "__main__":
    main()
