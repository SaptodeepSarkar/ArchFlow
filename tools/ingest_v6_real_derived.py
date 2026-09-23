#!/usr/bin/env python3
"""Create review-required V6 rows from a licensed audio manifest and V5 STT.

Input rows must contain a portable ``audio_ref``, a trusted ``reference``, and
source provenance.  This is deliberately bounded and never marks formatter
targets approved: STT hypotheses and references are evidence for human review,
not formatter ground truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import wave
from pathlib import Path


def seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def portable_audio(ref: str) -> str:
    path = Path(ref)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"audio_ref must be portable and relative: {ref!r}")
    return path.as_posix()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="licensed source JSONL")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=25)
    parser.add_argument("--max-audio-seconds", type=float, default=300.0)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--compute-type", default="int8_float16")
    args = parser.parse_args()
    if args.max_rows < 1 or args.max_audio_seconds <= 0:
        raise SystemExit("max limits must be positive")

    source_rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    selected, total_seconds = [], 0.0
    for item in source_rows:
        required = {"audio_ref", "reference", "source_name", "source_record_id", "license_ref", "language"}
        if missing := required - item.keys():
            raise SystemExit(f"source row lacks {sorted(missing)}")
        ref = portable_audio(item["audio_ref"])
        audio_path = args.audio_root / ref
        duration = seconds(audio_path)
        if len(selected) >= args.max_rows or total_seconds + duration > args.max_audio_seconds:
            continue
        selected.append((item, ref, audio_path, duration))
        total_seconds += duration
    if not selected:
        raise SystemExit("no source rows fit the requested bounds")

    # Estimate before importing the model. This pilot cap is intentionally
    # small: 25 clips / 300 seconds. Actual RTF is recorded after inference.
    print(json.dumps({"selected_rows": len(selected), "audio_seconds": total_seconds,
                      "device": args.device, "compute_type": args.compute_type,
                      "stage": "bounded_target_stt"}))
    from faster_whisper import WhisperModel
    model = WhisperModel(str(args.model), device=args.device, compute_type=args.compute_type)
    rows = []
    for index, (source, ref, audio_path, _) in enumerate(selected, 1):
        segments, _ = model.transcribe(str(audio_path), language=source["language"],
                                       beam_size=1, condition_on_previous_text=False,
                                       word_timestamps=True, vad_filter=False)
        words, hypothesis, segment_ids = [], [], []
        for segment_id, segment in enumerate(segments):
            hypothesis.append(segment.text.strip())
            for word in segment.words or []:
                start = round(word.start * 1000)
                end = round(word.end * 1000)
                words.append({"text": word.word, "word_start_ms": start, "word_end_ms": end,
                              "pause_before_ms": None, "pause_after_ms": None,
                              "segment_id": segment_id, "confidence": word.probability,
                              "alternatives": None})
            segment_ids.append({"segment_id": segment_id, "no_speech_probability": segment.no_speech_prob,
                                "average_log_probability": segment.avg_logprob})
        for previous, following in zip(words, words[1:]):
            pause = max(0, following["word_start_ms"] - previous["word_end_ms"])
            previous["pause_after_ms"] = pause
            following["pause_before_ms"] = pause
        digest = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        record_id = str(source["source_record_id"])
        rows.append({
            "schema_version": "vaani.v6.formatter-example/2",
            "example_id": f"v6-real-{source['source_name']}-{record_id}",
            "source": {"name": source["source_name"], "record_id": record_id, "type": "real_derived"},
            "provenance": {"license_ref": source["license_ref"], "transformation_history": ["licensed audio", "frozen-v5-target-stt"]},
            "utterance": {"raw_stt": " ".join(hypothesis), "reference_transcript": source["reference"], "clean_target": source["reference"]},
            "stt": {"backend": "faster-whisper", "model": str(args.model.name), "final": True,
                    "words": words, "segments": segment_ids},
            "labels": ["real_derived", "formatter_target_unreviewed"],
            "language": {"primary": source["language"], "code_switching": bool(source.get("code_switching", False)),
                         "accent_or_domain": source.get("accent_or_domain")},
            "annotation": {"method": "source-reference-plus-target-stt", "review_status": "needs_human_review", "reviewer": None},
            "split": None, "group_id": source.get("speaker_id") or f"source-{source['source_name']}-{record_id}",
            "audio": {"ref": ref, "sha256": digest},
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"real_derived_candidates": len(rows), "review_status": "needs_human_review", "out": str(args.out)}))


if __name__ == "__main__":
    main()
