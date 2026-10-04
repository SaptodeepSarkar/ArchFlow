#!/usr/bin/env python3
"""Estimate vocabulary-term exposure under the V6 SQLite source sampler.

Only aggregate counts and term hashes are read or reported; audio paths and
targets never enter stdout or the generated report.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path


def read_source(path: Path) -> tuple[int, Counter[str]]:
    if not path.is_file():
        raise ValueError(f"SQLite sampling source is missing: {path.name}")
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(examples)")}
        if not columns:
            raise ValueError(f"SQLite sampling source has no examples table: {path.name}")
        total_rows = connection.execute("SELECT COUNT(*) FROM examples").fetchone()[0]
        term_counts: Counter[str] = Counter()
        if "term_sha256" in columns:
            term_counts.update(dict(
                (str(term_hash), int(count))
                for term_hash, count in connection.execute(
                    "SELECT term_sha256, COUNT(*) FROM examples "
                    "WHERE term_sha256 IS NOT NULL AND term_sha256 != '' "
                    "GROUP BY term_sha256"
                )
            ))
    except sqlite3.Error as error:
        raise ValueError(f"could not read SQLite sampling source {path.name}: {error}") from error
    finally:
        if "connection" in locals():
            connection.close()
    if total_rows <= 0:
        raise ValueError(f"SQLite sampling source is empty: {path.name}")
    return int(total_rows), term_counts


def audit_sampling(
    manifests: list[Path],
    steps: int,
    *,
    combined_fraction: float | None = None,
    source_fractions: list[float] | None = None,
    min_expected_draws_per_term: float = 3.0,
) -> dict:
    if steps <= 0:
        raise ValueError("steps must be positive")
    if not manifests:
        raise ValueError("at least one SQLite sampling source is required")
    if (combined_fraction is None) == (source_fractions is None):
        raise ValueError("choose exactly one of a combined fraction or per-source fractions")
    if source_fractions is not None and len(source_fractions) != len(manifests):
        raise ValueError("pass one source fraction per SQLite manifest")
    fractions = source_fractions if source_fractions is not None else [combined_fraction]
    if any(not math.isfinite(float(value)) or not 0 < float(value) < 1 for value in fractions):
        raise ValueError("sampling fractions must be finite and between zero and one")
    if sum(fractions) >= 1:
        raise ValueError("SQLite source fractions must sum to less than one")
    if not math.isfinite(min_expected_draws_per_term) or min_expected_draws_per_term < 0:
        raise ValueError("minimum expected draws per term must be finite and nonnegative")

    sources = [read_source(path) for path in manifests]
    term_probabilities: dict[str, float] = {}
    if source_fractions is None:
        total_rows = sum(row_count for row_count, _ in sources)
        for term_hash in {term for _, terms in sources for term in terms}:
            term_rows = sum(terms[term_hash] for _, terms in sources)
            term_probabilities[term_hash] = combined_fraction * term_rows / total_rows
    else:
        for term_hash in {term for _, terms in sources for term in terms}:
            probability = sum(
                fraction * terms.get(term_hash, 0) / row_count
                for (row_count, terms), fraction in zip(sources, source_fractions)
            )
            term_probabilities[term_hash] = probability

    term_count = len(term_probabilities)
    expected_exposed_terms = sum(
        1.0 - (1.0 - probability) ** steps
        for probability in term_probabilities.values()
    )
    expected_draws_per_term = (
        steps * sum(term_probabilities.values()) / term_count if term_count else 0.0
    )
    expected_sqlite_draws = steps * sum(fractions)
    warnings = []
    if term_count and expected_draws_per_term < min_expected_draws_per_term:
        warnings.append("expected vocabulary draws per term are below the configured minimum")
    if term_count and expected_exposed_terms < 0.8 * term_count:
        warnings.append("fewer than 80% of vocabulary terms are expected to be sampled")

    return {
        "schema_version": 1,
        "steps": steps,
        "sqlite_source_rows": sum(row_count for row_count, _ in sources),
        "vocabulary_terms": term_count,
        "expected_sqlite_draws": expected_sqlite_draws,
        "expected_draws_per_term": expected_draws_per_term,
        "expected_terms_exposed_at_least_once": expected_exposed_terms,
        "expected_term_coverage_percent": (
            100 * expected_exposed_terms / term_count if term_count else None
        ),
        "min_expected_draws_per_term": min_expected_draws_per_term,
        "warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite-manifest", type=Path, action="append", required=True)
    parser.add_argument("--source-fraction", type=float, action="append")
    parser.add_argument("--combined-fraction", type=float)
    parser.add_argument("--steps", type=int, required=True,
                        help="number of example draws, not optimizer steps; multiply steps by batch and accumulation")
    parser.add_argument("--min-expected-draws-per-term", type=float, default=3.0)
    parser.add_argument("--report", type=Path,
                        help="optional aggregate-only JSON report written outside Git")
    args = parser.parse_args()
    try:
        report = audit_sampling(
            args.sqlite_manifest,
            args.steps,
            combined_fraction=args.combined_fraction,
            source_fractions=args.source_fraction,
            min_expected_draws_per_term=args.min_expected_draws_per_term,
        )
    except ValueError as error:
        raise SystemExit(f"sampling audit failed: {error}") from error
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
