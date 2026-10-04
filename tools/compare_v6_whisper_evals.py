#!/usr/bin/env python3
"""Compare aggregate-only V6 STT evaluator reports on the same held-out set."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def read(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    try:
        report = json.loads(raw)
    except json.JSONDecodeError:
        # eval_v5_whisper_adapter.py stores privacy-safe per-row counts as
        # JSONL, not transcripts. Reduce those rows here without serializing
        # hypotheses or references.
        try:
            rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        except json.JSONDecodeError as error:
            raise SystemExit(f"{path}: invalid aggregate JSON/JSONL") from error
        required_row = {"row_id", "reference_words", "normalized_errors",
                        "protected_terms", "missing_protected_terms"}
        if not rows or any(not required_row <= row.keys() for row in rows):
            raise SystemExit(f"{path}: missing aggregate-only row fields")
        row_ids = [row["row_id"] for row in rows]
        if any(not isinstance(value, str) for value in row_ids) or len(set(row_ids)) != len(row_ids):
            raise SystemExit(f"{path}: row IDs must be unique strings")
        reference_words = sum(int(row["reference_words"]) for row in rows)
        errors = sum(int(row["normalized_errors"]) for row in rows)
        protected_terms = sum(int(row["protected_terms"]) for row in rows)
        protected_hits = sum(
            int(row["protected_terms"]) - int(row["missing_protected_terms"])
            for row in rows
        )
        report = {
            "rows": len(rows),
            "evaluated_row_ids_sha256": hashlib.sha256(
                "\n".join(row_ids).encode("utf-8")
            ).hexdigest(),
            "normalized_wer_percent": 100 * errors / max(reference_words, 1),
            "protected_terms": protected_terms,
            "protected_term_accuracy_percent": (
                100 * protected_hits / protected_terms if protected_terms else None
            ),
        }
        metadata_path = path.with_name(path.name + ".meta.json")
        if metadata_path.is_file():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            required_metadata = {
                "rows", "evaluated_row_ids_sha256", "base_model_sha256",
                "adapter_sha256", "decoder",
            }
            if not required_metadata <= metadata.keys():
                raise SystemExit(f"{metadata_path}: missing model provenance fields")
            if (metadata["rows"] != report["rows"]
                    or metadata["evaluated_row_ids_sha256"] != report["evaluated_row_ids_sha256"]):
                raise SystemExit(f"{metadata_path}: provenance does not match evaluation rows")
            report.update(metadata)
    required = {"evaluated_row_ids_sha256", "rows", "normalized_wer_percent",
                "protected_term_accuracy_percent", "protected_terms"}
    if isinstance(report, dict) and "selected_example_ids_sha256" in report:
        if report.get("decode_failures") != 0 or report.get("rows_decoded") != report.get("rows_requested"):
            raise SystemExit(f"{path}: CT2 report contains decode failures")
        report = {
            **report,
            "evaluated_row_ids_sha256": report["selected_example_ids_sha256"],
            "rows": report["rows_requested"],
        }
    missing = required - report.keys()
    if missing:
        raise SystemExit(f"{path}: missing aggregate fields {sorted(missing)}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--suite", help="stable evaluation suite identifier for qualification evidence")
    parser.add_argument("--minimum-wer-improvement", type=float, default=0.0,
                        help="required positive percentage-point WER improvement")
    parser.add_argument("--maximum-protected-term-drop", type=float, default=0.0,
                        help="largest allowed protected-term accuracy drop in percentage points")
    parser.add_argument("--minimum-protected-term-support", type=int, default=0,
                        help="minimum protected-term occurrences required for promotion")
    parser.add_argument("--minimum-protected-term-gain", type=float, default=0.0,
                        help="required protected-term accuracy gain in percentage points")
    parser.add_argument("--minimum-protected-term-accuracy", type=float, default=0.0,
                        help="absolute candidate protected-term accuracy floor")
    parser.add_argument("--allow-model-mismatch", action="store_true",
                        help="compare distinct model hashes when the held-out rows and decoder settings match")
    parser.add_argument("--allow-hotword-mismatch", action="store_true",
                        help="allow only hotwords_enabled/hotwords_sha256 to differ in paired decoder reports")
    args = parser.parse_args()
    base, candidate = read(args.base), read(args.candidate)
    if (base["evaluated_row_ids_sha256"] != candidate["evaluated_row_ids_sha256"]
            or base["rows"] != candidate["rows"]):
        raise SystemExit("reports do not cover the same held-out evaluation manifest")
    if ("source_manifest_sha256" in base or "source_manifest_sha256" in candidate) \
            and base.get("source_manifest_sha256") != candidate.get("source_manifest_sha256"):
        raise SystemExit("reports do not match in source_manifest_sha256")
    model_hash_match = base.get("model_sha256") == candidate.get("model_sha256")
    if not model_hash_match and not args.allow_model_mismatch:
        raise SystemExit("reports do not match in model_sha256 (pass --allow-model-mismatch for a paired model comparison)")
    base_decoder = base.get("decoder")
    candidate_decoder = candidate.get("decoder")
    hotword_settings_match = True
    if ("decoder" in base or "decoder" in candidate) and base_decoder != candidate_decoder:
        if not args.allow_hotword_mismatch or not isinstance(base_decoder, dict) \
                or not isinstance(candidate_decoder, dict):
            raise SystemExit("reports do not match in decoder settings")
        base_other = {key: value for key, value in base_decoder.items()
                      if key not in {"hotwords_enabled", "hotwords_sha256"}}
        candidate_other = {key: value for key, value in candidate_decoder.items()
                           if key not in {"hotwords_enabled", "hotwords_sha256"}}
        if base_other != candidate_other:
            raise SystemExit("reports differ in decoder settings beyond hotwords")
        hotword_settings_match = all(
            base_decoder.get(key) == candidate_decoder.get(key)
            for key in ("hotwords_enabled", "hotwords_sha256")
        )
    if base.get("protected_terms") != candidate.get("protected_terms"):
        raise SystemExit("reports do not cover the same protected-term occurrences")
    if base.get("scored_vocabulary_sha256") != candidate.get("scored_vocabulary_sha256"):
        raise SystemExit("reports do not match in scored_vocabulary_sha256")
    provenance_present = ("base_model_sha256" in base or "base_model_sha256" in candidate
                          or "adapter_sha256" in base or "adapter_sha256" in candidate)
    if provenance_present:
        if "base_model_sha256" not in base or "base_model_sha256" not in candidate:
            raise SystemExit("paired reports are missing base-model provenance")
        if base["base_model_sha256"] != candidate["base_model_sha256"]:
            raise SystemExit("reports were evaluated with different base model artifacts")
        if candidate.get("adapter_sha256") is None:
            raise SystemExit("candidate evaluation has no adapter artifact provenance")
    wer_delta = base["normalized_wer_percent"] - candidate["normalized_wer_percent"]
    base_protected = base["protected_term_accuracy_percent"]
    candidate_protected = candidate["protected_term_accuracy_percent"]
    protected_support = int(candidate.get("protected_terms", 0))
    protected_delta = (candidate_protected - base_protected
                       if base_protected is not None and candidate_protected is not None
                       else 0.0)
    protected_accuracy_gate = (
        args.minimum_protected_term_accuracy == 0.0
        or (candidate_protected is not None
            and candidate_protected >= args.minimum_protected_term_accuracy)
    )
    promoted = (wer_delta >= args.minimum_wer_improvement and
                protected_delta >= -args.maximum_protected_term_drop and
                protected_delta >= args.minimum_protected_term_gain and
                protected_accuracy_gate and
                protected_support >= args.minimum_protected_term_support)
    output = {
        "suite": args.suite,
        "rows": base["rows"],
        "evaluated_row_ids_sha256": base["evaluated_row_ids_sha256"],
        "base_model_sha256": base.get("model_sha256"),
        "candidate_model_sha256": candidate.get("model_sha256"),
        "model_hash_match": model_hash_match,
        "base_normalized_wer_percent": base["normalized_wer_percent"],
        "candidate_normalized_wer_percent": candidate["normalized_wer_percent"],
        "wer_improvement_percentage_points": wer_delta,
        "base_protected_term_accuracy_percent": base_protected,
        "candidate_protected_term_accuracy_percent": candidate_protected,
        "protected_term_accuracy_delta_percentage_points": protected_delta,
        "minimum_wer_improvement": args.minimum_wer_improvement,
        "maximum_protected_term_drop": args.maximum_protected_term_drop,
        "protected_term_support": protected_support,
        "minimum_protected_term_support": args.minimum_protected_term_support,
        "minimum_protected_term_gain": args.minimum_protected_term_gain,
        "minimum_protected_term_accuracy": args.minimum_protected_term_accuracy,
        "protected_term_accuracy_gate": protected_accuracy_gate,
        "protected_term_support_gate": protected_support >= args.minimum_protected_term_support,
        "model_provenance_verified": provenance_present,
        "base_model_provenance_sha256": base.get("base_model_sha256"),
        "candidate_adapter_sha256": candidate.get("adapter_sha256"),
        "decoder": base_decoder,
        "candidate_decoder": candidate_decoder,
        "hotword_settings_match": hotword_settings_match,
        "promotion_eligible": promoted,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
