#!/usr/bin/env python3
"""Write $OUT/report.md from state.json plus whatever evals finished."""

from __future__ import annotations

import argparse
import os

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402


def metric_table(report, keys):
    lines = ["| metric | value |", "|---|---|"]
    for key in keys:
        value = report.get(key)
        if isinstance(value, float):
            lines.append(f"| {key} | {value:.4f} |")
        else:
            lines.append(f"| {key} | {value} |")
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = args.out

    state = common.read_state(out)
    stt = common.read_json(os.path.join(out, "eval", "stt.json"))
    formatter = common.read_json(os.path.join(out, "eval", "formatter.json"))
    stt_average = common.read_json(os.path.join(out, "stt", "averaged", "average.json"))
    fmt_average = common.read_json(os.path.join(out, "formatter", "averaged", "average.json"))

    lines = ["# V8 training report", "",
             f"state: **{state.get('status', 'unknown')}** at stage `{state.get('stage')}` "
             f"(updated {state.get('updated_at', 'n/a')})", ""]

    if stt:
        lines += ["## STT (CTranslate2 int8 is the shipped model)", ""]
        lines += metric_table(stt, ["n", "wer"])
        lines.append("")
        if stt.get("per_source"):
            lines += ["| source | n | WER |", "|---|---|---|"]
            for source, values in sorted(stt["per_source"].items()):
                lines.append(f"| {source} | {values['n']} | {values['wer']:.4f} |")
            lines.append("")

    if formatter:
        lines += ["## Formatter (GGUF Q4_K_M is the shipped model)", ""]
        lines += metric_table(formatter, ["n", "exact_match", "exact_match_normalised",
                                         "entity_survival", "number_survival", "token_f0_5",
                                         "over_edit_rate", "punctuation_accuracy",
                                         "intensity_survival"])
        lines.append("")

    lines += ["## Artefacts", ""]
    artefacts = [
        ("STT checkpoints", os.path.join(out, "stt")),
        ("STT averaged", os.path.join(out, "stt", "averaged")),
        ("STT CT2 int8", os.path.join(out, "export", "stt-ct2-int8")),
        ("Formatter averaged", os.path.join(out, "formatter", "averaged")),
        ("Formatter GGUF", os.path.join(out, "export", "formatter-q4_k_m.gguf")),
        ("Formatter predictions", os.path.join(out, "eval", "predictions.jsonl")),
    ]
    for label, path in artefacts:
        lines.append(f"- {label}: `{path}` {'✅' if os.path.exists(path) else '—'}")
    lines.append("")
    if stt_average:
        best = stt_average.get("best")
        shown = f"{best:.4f}" if isinstance(best, float) else "n/a"
        lines.append(f"STT averaged steps: {stt_average.get('source_steps')} (best WER {shown})")
    if fmt_average:
        best = fmt_average.get("best")
        shown = f"{best:.4f}" if isinstance(best, float) else "n/a"
        lines.append(f"Formatter averaged steps: {fmt_average.get('source_steps')} "
                     f"(best EM {shown}, skipped steps {fmt_average.get('skipped_steps')})")
    lines.append("")
    lines.append("Resume with `bash training/run_all.sh --full`; it reads `state.json`.")
    lines.append("")

    path = os.path.join(out, "report.md")
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
