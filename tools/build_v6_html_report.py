#!/usr/bin/env python3
"""Build a self-contained V6 STT/formatter benchmark report."""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

STT_METRICS = {
    "rows", "reference_words", "literal_errors", "normalized_errors",
    "literal_wer_percent", "normalized_wer_percent",
    "mean_row_normalized_wer_percent", "protected_terms",
    "protected_terms_recognized", "protected_term_accuracy_percent",
    "decode_seconds", "real_time_factor",
}
ANDROID_METRICS = {"rows", "launch_ms", "peak_rss_mb", "latency_ms", "memory_mb"}


def rows(path: Path) -> list[dict]:
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise SystemExit("evaluation input contains a non-object row")
        result.append(row)
    return result


def index_rows(path: Path) -> dict[str, dict]:
    indexed = {}
    for row in rows(path):
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id or row_id in indexed:
            raise SystemExit("evaluation input has a missing or duplicate row ID")
        indexed[row_id] = row
    return indexed


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--learned", type=Path, required=True)
    ap.add_argument("--hybrid", type=Path, required=True)
    ap.add_argument("--stt-summary", default="", help="JSON object with measured STT control metrics")
    ap.add_argument("--stt-cases", type=Path, help="JSONL with per-audio STT reference/hypothesis rows")
    ap.add_argument("--formatter-cases", type=Path, help="JSONL with prior formatter audit rows")
    ap.add_argument("--android-summary", default="", help="JSON object with measured Android smoke metrics")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    data = index_rows(args.data)
    learned = index_rows(args.learned)
    if not data or set(data) != set(learned):
        raise SystemExit("learned results do not cover the complete source set")
    hybrid = json.loads(args.hybrid.read_text(encoding="utf-8"))
    stt = json.loads(args.stt_summary) if args.stt_summary else {}
    android = json.loads(args.android_summary) if args.android_summary else {}
    if not all(isinstance(value, dict) for value in (hybrid, stt, android)):
        raise SystemExit("aggregate summaries must be JSON objects")

    if any(type(row.get("exact")) is not bool for row in learned.values()):
        raise SystemExit("learned results contain invalid exact-match flags")
    exact = sum(row["exact"] for row in learned.values())
    body = ["<!doctype html><meta charset='utf-8'><title>Vaani V6 benchmark</title>",
            "<style>body{font:14px system-ui;margin:2rem;background:#f5f6f8;color:#17202a}section{background:#fff;padding:1rem;margin:1rem 0;border-radius:10px;box-shadow:0 1px 4px #ccd}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d9dee5;padding:.5rem;text-align:left;vertical-align:top}pre{white-space:pre-wrap;margin:0}.bad{background:#fff1f1}.good{background:#effff1}.mono{font-family:ui-monospace,monospace}</style>",
            "<h1>Vaani V6 STT + formatter benchmark</h1>",
            "<p>This report separates learned-plan accuracy from the deterministic hybrid renderer. It does not claim the closed fallback is learned accuracy.</p>"]
    def metric_rows(values: dict, allowed: set[str]) -> str:
        safe = ((key, value) for key, value in values.items()
                if key in allowed and isinstance(value, (int, float))
                and not isinstance(value, bool) and math.isfinite(value)
                and value >= 0)
        return "".join(f"<tr><td>{esc(key)}</td><td>{esc(value)}</td></tr>" for key, value in safe)

    hybrid_rows = hybrid.get("rows", 0)
    hybrid_exact = hybrid.get("rendered_exact", 0)
    protected_failures = hybrid.get("protected_failures", 0)
    counts = (hybrid_rows, hybrid_exact, protected_failures)
    if (any(type(value) is not int or value < 0 for value in counts)
            or hybrid_exact > hybrid_rows or protected_failures > hybrid_rows
            or hybrid_rows != len(data)):
        raise SystemExit("hybrid summary contains invalid or incomplete aggregate counts")
    body.append("<section><h2>STT control</h2><table><tr><th>Metric</th><th>Measured value</th></tr>" + metric_rows(stt, STT_METRICS) + "</table></section>")
    body.append("<section><h2>Android smoke benchmark</h2><p>Launch and memory smoke metrics only.</p><table><tr><th>Metric</th><th>Measured value</th></tr>" + metric_rows(android, ANDROID_METRICS) + "</table></section>")
    body.append(f"<section><h2>Formatter summary</h2><p>Challenge rows: {len(data)}. Learned plan exact: {exact}/{len(learned)}. Hybrid rendered exact: {hybrid_exact}/{hybrid_rows}. Hybrid protected-span failures: {protected_failures}.</p></section>")
    body.append("<section><h2>Privacy boundary</h2><p>Per-row transcripts, paths, references, model outputs, and failures are intentionally excluded from this report.</p></section>")
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text("".join(body), encoding="utf-8")
    print(json.dumps({"learned_exact": exact, "hybrid_exact": hybrid_exact, "rows": len(data)}))


if __name__ == "__main__":
    main()
