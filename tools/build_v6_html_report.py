#!/usr/bin/env python3
"""Build a self-contained V6 STT/formatter benchmark report."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--learned", type=Path, required=True)
    ap.add_argument("--hybrid", type=Path, required=True)
    ap.add_argument("--stt-summary", default="", help="JSON object with measured STT control metrics")
    ap.add_argument("--android-summary", default="", help="JSON object with measured Android smoke metrics")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    data = {r["id"]: r for r in rows(args.data)}
    learned = {r["id"]: r for r in rows(args.learned)}
    hybrid = json.loads(args.hybrid.read_text())
    stt = json.loads(args.stt_summary) if args.stt_summary else {}
    android = json.loads(args.android_summary) if args.android_summary else {}

    exact = sum(bool(r["exact"]) for r in learned.values())
    body = ["<!doctype html><meta charset='utf-8'><title>Vaani V6 benchmark</title>",
            "<style>body{font:14px system-ui;margin:2rem;background:#f5f6f8;color:#17202a}section{background:#fff;padding:1rem;margin:1rem 0;border-radius:10px;box-shadow:0 1px 4px #ccd}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d9dee5;padding:.5rem;text-align:left;vertical-align:top}pre{white-space:pre-wrap;margin:0}.bad{background:#fff1f1}.good{background:#effff1}.mono{font-family:ui-monospace,monospace}</style>",
            "<h1>Vaani V6 STT + formatter benchmark</h1>",
            "<p>This report separates learned-plan accuracy from the deterministic hybrid renderer. It does not claim the closed fallback is learned accuracy.</p>"]
    body.append("<section><h2>STT control</h2><table><tr><th>Metric</th><th>Measured value</th></tr>" + "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in stt.items()) + "</table></section>")
    body.append("<section><h2>Android smoke benchmark</h2><p>This is a launch/memory smoke test only. It does not measure speech WER, transcription quality, or speech-end to insertion latency.</p><table><tr><th>Metric</th><th>Measured value</th></tr>" + "".join(f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in android.items()) + "</table></section>")
    body.append(f"<section><h2>Formatter summary</h2><p>Learned plan exact: {exact}/{len(learned)}. Hybrid rendered exact: {hybrid.get('rendered_exact', 0)}/{hybrid.get('rows', 0)}. Hybrid protected-span failures: {hybrid.get('protected_failures', 0)}.</p></section>")
    body.append("<section><h2>Challenge cases</h2><table><tr><th>Category</th><th>Raw source</th><th>Expected</th><th>Learned plan</th><th>Hybrid output</th><th>Status</th></tr>")
    hybrid_rows = {r["id"]: r for r in hybrid.get("rows_detail", [])}
    for ident, row in data.items():
        learned_row = learned[ident]; hybrid_row = hybrid_rows.get(ident, {})
        ok = bool(hybrid_row.get("exact")); cls = "good" if ok else "bad"
        body.append(f"<tr class='{cls}'><td>{esc(', '.join(row.get('metadata', {}).get('categories', [])))}</td><td><pre>{esc(row['source'])}</pre></td><td><pre>{esc(row['target_text'])}</pre></td><td><pre>{esc(json.dumps(learned_row['generated'], ensure_ascii=False, indent=2))}</pre></td><td><pre>{esc(hybrid_row.get('rendered'))}</pre></td><td>{'PASS' if ok else 'FAIL'}</td></tr>")
    body.append("</table></section>")
    args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text("".join(body), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "learned_exact": exact, "hybrid_exact": hybrid.get("rendered_exact", 0), "rows": len(data)}))


if __name__ == "__main__":
    main()
