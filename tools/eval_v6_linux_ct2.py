#!/usr/bin/env python3
"""Aggregate-only evaluation of a V6 Linux faster-whisper/CT2 artifact.

References and hypotheses are held in process memory only. The report contains
corpus/tag WER, protected-term recall, hashes, latency, and failure counts; it
never writes utterance text or per-row scores.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
import re
import sqlite3
import time
import wave
from pathlib import Path


TOKEN = re.compile(r"[\w]+(?:['-][\w]+)?", flags=re.UNICODE)


def normalized_tokens(text: str) -> list[str]:
    return TOKEN.findall(text.casefold())


def edit_counts(reference: list[str], hypothesis: list[str]) -> tuple[int, int, int]:
    previous = [(index, 0, 0, index) for index in range(len(hypothesis) + 1)]
    for ref_index, ref_token in enumerate(reference, start=1):
        current = [(ref_index, 0, ref_index, 0)]
        for hyp_index, hyp_token in enumerate(hypothesis, start=1):
            substitute, delete, insert = previous[hyp_index - 1], previous[hyp_index], current[hyp_index - 1]
            mismatch = ref_token != hyp_token
            choices = (
                (substitute[0] + mismatch, substitute[1] + mismatch, substitute[2], substitute[3]),
                (delete[0] + 1, delete[1], delete[2] + 1, delete[3]),
                (insert[0] + 1, insert[1], insert[2], insert[3] + 1),
            )
            current.append(min(choices, key=lambda value: value[0]))
        previous = current
    _, substitutions, deletions, insertions = previous[-1]
    return substitutions, deletions, insertions


def contains_term(text_tokens: list[str], term: str) -> bool:
    expected = normalized_tokens(term)
    width = len(expected)
    return bool(width) and any(
        text_tokens[index:index + width] == expected
        for index in range(len(text_tokens) - width + 1)
    )


def model_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    files = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        raise SystemExit("model artifact is empty or unavailable")
    for file in files:
        rel = file.name if path.is_file() else file.relative_to(path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        with file.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def load_rows(manifest: Path, limit: int) -> list[dict]:
    if manifest.suffix == ".sqlite3":
        uri = f"{manifest.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as database:
            columns = {row[1] for row in database.execute("PRAGMA table_info(examples)")}
            required = {"id", "audio_path", "target_text"}
            if not required <= columns:
                raise SystemExit("SQLite manifest examples table is missing required columns")
            query = "SELECT id, audio_path, target_text FROM examples ORDER BY id"
            values = database.execute(query + (" LIMIT ?" if limit else ""), (limit,) if limit else ())
            rows = [
                {"example_id": str(identifier), "audio_path": audio_path,
                 "reference": target_text}
                for identifier, audio_path, target_text in values
            ]
        if not rows:
            raise SystemExit("manifest has no rows")
        return rows

    rows = []
    with manifest.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if limit and len(rows) >= limit:
                break
    if not rows:
        raise SystemExit("manifest has no rows")
    return rows


def row_audio(row: dict, audio_root: Path) -> Path:
    audio_path = row.get("audio_path")
    if isinstance(audio_path, str) and audio_path:
        path = Path(audio_path).expanduser()
        return path if path.is_absolute() else audio_root / path
    audio = row.get("audio", {})
    ref = audio.get("ref") if isinstance(audio, dict) else None
    if isinstance(ref, str) and ref:
        return audio_root / ref
    raise SystemExit("manifest row is missing an audio path")


def row_reference(row: dict) -> str:
    utterance = row.get("utterance", {})
    candidates = (
        row.get("reference"), row.get("text"),
        utterance.get("reference_transcript") if isinstance(utterance, dict) else None,
    )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
    raise SystemExit("manifest row is missing a reference transcript")


def audio_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as audio:
            return audio.getnframes() / audio.getframerate()
    except (wave.Error, OSError):
        # faster-whisper accepts compressed sources (e.g. the MDC MP3 files),
        # so measure them via its PyAV dependency rather than rejecting them.
        try:
            import av
            with av.open(str(path)) as container:
                streams = [stream for stream in container.streams if stream.type == "audio"]
                if streams and streams[0].duration is not None and streams[0].time_base is not None:
                    return float(streams[0].duration * streams[0].time_base)
                if container.duration is not None:
                    return float(container.duration / av.time_base)
        except Exception:  # content-free fallback for unsupported/corrupt audio
            pass
        raise ValueError("audio duration is unavailable")


def read_hotword_terms(paths: list[Path] | None) -> list[str]:
    if not paths:
        return []
    terms: dict[str, str] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            term = line.strip()
            if term and not term.startswith("#"):
                terms.setdefault(term.casefold(), term)
    return list(terms.values())


def read_hotwords(paths: list[Path] | None) -> str | None:
    return ", ".join(read_hotword_terms(paths)) or None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audio-root", type=Path, default=Path("."))
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100,
                        help="first N frozen rows; use 0 for all rows")
    parser.add_argument("--language", default="en")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--compute-type")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--hotwords-file", type=Path, nargs="+",
                        help="one or more vocabulary pack files; terms are deduplicated")
    parser.add_argument("--score-hotwords-file", type=Path, nargs="+",
                        help="score only pack terms present in each reference; does not bias decoding")
    args = parser.parse_args()
    if args.limit < 0 or args.beam_size < 1:
        raise SystemExit("limit must be nonnegative and beam-size must be positive")
    if not args.model.exists():
        raise SystemExit("model artifact is unavailable")
    rows = load_rows(args.manifest, args.limit)
    hotwords = read_hotwords(args.hotwords_file)
    score_terms = read_hotword_terms(args.score_hotwords_file)
    score_terms_sha256 = (
        hashlib.sha256("\n".join(term.casefold() for term in score_terms).encode()).hexdigest()
        if score_terms else None
    )

    # Evaluation inputs and model artifacts are local; avoid hub telemetry or
    # network lookups that cannot improve a frozen, reproducible run.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    from faster_whisper import WhisperModel

    compute_type = args.compute_type or ("int8_float16" if args.device == "cuda" else "int8")
    model = WhisperModel(str(args.model), device=args.device, compute_type=compute_type)

    substitutions = deletions = insertions = reference_words = 0
    protected_terms = protected_hits = failures = 0
    failure_types: dict[str, int] = {}
    tag_counts: dict[str, dict[str, int]] = {}
    vocabulary_slices: dict[str, dict[str, int]] = {}
    audio_seconds = decode_seconds = 0.0
    for row in rows:
        audio = row_audio(row, args.audio_root)
        if not audio.is_file():
            raise SystemExit("a frozen-slice audio file is missing")
        try:
            duration = audio_duration(audio)
            started = time.monotonic()
            segments, _ = model.transcribe(
                str(audio), language=args.language, beam_size=args.beam_size,
                condition_on_previous_text=False, hotwords=hotwords,
            )
            hypothesis = " ".join(segment.text.strip() for segment in segments).strip()
            decode_seconds += time.monotonic() - started
            audio_seconds += duration
        except Exception as error:  # keep diagnostics content-free
            failures += 1
            # Exception classes identify backend/config failures without
            # risking audio, transcript, path, or model-output leakage.
            name = type(error).__name__
            failure_types[name] = failure_types.get(name, 0) + 1
            continue

        reference = normalized_tokens(row_reference(row))
        hypothesis_tokens = normalized_tokens(hypothesis)
        sub, delete, insert = edit_counts(reference, hypothesis_tokens)
        substitutions += sub
        deletions += delete
        insertions += insert
        reference_words += len(reference)

        terms = row.get("challenge_terms", [])
        if not isinstance(terms, list) or any(not isinstance(term, str) for term in terms):
            raise SystemExit("challenge_terms must be a list of strings")
        if score_terms:
            terms = [term for term in score_terms
                     if contains_term(reference, term)]
            slice_name = "relevant_terms" if terms else "ordinary_speech"
            counts = vocabulary_slices.setdefault(slice_name, {
                "rows": 0, "reference_words": 0, "errors": 0,
                "false_vocabulary_hits": 0, "rows_with_false_vocabulary_hits": 0,
            })
            false_hits = sum(
                contains_term(hypothesis_tokens, term)
                for term in score_terms if not contains_term(reference, term)
            )
            counts["rows"] += 1
            counts["reference_words"] += len(reference)
            counts["errors"] += sub + delete + insert
            counts["false_vocabulary_hits"] += false_hits
            counts["rows_with_false_vocabulary_hits"] += int(false_hits > 0)
        protected_terms += len(terms)
        protected_hits += sum(contains_term(hypothesis_tokens, term) for term in terms)

        tags = row.get("challenge_tags", [])
        if (not isinstance(tags, list)
                or any(not isinstance(tag, str)
                       or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", tag)
                       for tag in tags)
                or len(set(tags)) != len(tags)):
            raise SystemExit("challenge_tags must be unique lowercase tag identifiers")
        errors = sub + delete + insert
        for tag in tags:
            aggregate = tag_counts.setdefault(tag, {"rows": 0, "reference_words": 0, "errors": 0})
            aggregate["rows"] += 1
            aggregate["reference_words"] += len(reference)
            aggregate["errors"] += errors

    if failures == len(rows):
        classes = ",".join(f"{name}:{count}" for name, count in sorted(failure_types.items()))
        raise SystemExit(
            "all rows failed to decode; no accuracy report written; "
            f"failure_classes={classes or 'unknown'}"
        )

    errors = substitutions + deletions + insertions
    selected_ids = [str(row.get("example_id", index)) for index, row in enumerate(rows)]
    report = {
        "schema_version": 1,
        "source_manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "selected_example_ids_sha256": hashlib.sha256("\n".join(selected_ids).encode()).hexdigest(),
        "model_sha256": model_sha256(args.model),
        "decoder": {"language": args.language, "beam_size": args.beam_size,
                    "device": args.device, "compute_type": compute_type,
                    "hotwords_enabled": bool(hotwords),
                    "hotwords_sha256": hashlib.sha256(hotwords.encode()).hexdigest() if hotwords else None},
        "rows_requested": len(rows),
        "rows_decoded": len(rows) - failures,
        "decode_failures": failures,
        "decode_failure_classes": failure_types,
        "reference_words": reference_words,
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "normalized_wer_percent": round(100 * errors / max(reference_words, 1), 4),
        "protected_terms": protected_terms,
        "protected_terms_recognized": protected_hits,
        "scored_vocabulary_sha256": score_terms_sha256,
        "vocabulary_slice_metrics": {
            name: {**counts, "normalized_wer_percent": round(
                100 * counts["errors"] / max(counts["reference_words"], 1), 4)}
            for name, counts in sorted(vocabulary_slices.items())
        },
        "protected_term_accuracy_percent": (
            round(100 * protected_hits / protected_terms, 4) if protected_terms else None
        ),
        "challenge_tag_metrics": {
            tag: {**counts, "normalized_wer_percent": round(
                100 * counts["errors"] / max(counts["reference_words"], 1), 4)}
            for tag, counts in sorted(tag_counts.items())
        },
        "audio_seconds": round(audio_seconds, 3),
        "decode_seconds": round(decode_seconds, 3),
        "real_time_factor": round(decode_seconds / max(audio_seconds, 0.001), 5),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    if failures:
        raise SystemExit("evaluation incomplete: decode failures; aggregate report is diagnostic only")


if __name__ == "__main__":
    main()
