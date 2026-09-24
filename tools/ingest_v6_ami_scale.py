#!/usr/bin/env python3
"""Incrementally make review-required V6 rows from downloaded AMI plan audio.

This is intentionally a bounded, resumable data-preparation worker.  It only
uses complete WAV files from the official acquisition plan, loads target STT
once per invocation, and never assigns a split or approval status.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import wave
from pathlib import Path


def complete_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as stream:
            expected = 44 + stream.getnframes() * stream.getnchannels() * stream.getsampwidth()
        return path.stat().st_size >= expected
    except (OSError, wave.Error):
        return False


def slice_wav(source: Path, target: Path, start_ms: int, end_ms: int) -> None:
    with wave.open(str(source), "rb") as reader:
        rate = reader.getframerate()
        reader.setpos(round(start_ms * rate / 1000))
        frames = reader.readframes(round((end_ms - start_ms) * rate / 1000))
        with wave.open(str(target), "wb") as writer:
            writer.setparams(reader.getparams())
            writer.writeframes(frames)


def transcribe(model, path: Path, language: str) -> tuple[str, list[dict], list[dict]]:
    segments, _ = model.transcribe(str(path), language=language, beam_size=1,
                                  condition_on_previous_text=False,
                                  word_timestamps=True, vad_filter=False)
    words, text, metadata = [], [], []
    for segment_id, segment in enumerate(segments):
        text.append(segment.text.strip())
        for word in segment.words or []:
            words.append({"text": word.word, "word_start_ms": round(word.start * 1000),
                          "word_end_ms": round(word.end * 1000), "pause_before_ms": None,
                          "pause_after_ms": None, "segment_id": segment_id,
                          "confidence": word.probability, "alternatives": None})
        metadata.append({"segment_id": segment_id, "no_speech_probability": segment.no_speech_prob,
                         "average_log_probability": segment.avg_logprob})
    for previous, following in zip(words, words[1:]):
        pause = max(0, following["word_start_ms"] - previous["word_end_ms"])
        previous["pause_after_ms"] = pause; following["pause_before_ms"] = pause
    return " ".join(part for part in text if part), words, metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=25)
    parser.add_argument("--max-audio-seconds", type=float, default=300.0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()
    if args.max_rows < 1 or args.max_audio_seconds <= 0:
        raise SystemExit("max limits must be positive")

    existing = []
    if args.out.exists():
        existing = [json.loads(line) for line in args.out.read_text(encoding="utf-8").splitlines() if line.strip()]
    invalid_existing = [row for row in existing if not row.get("utterance", {}).get("raw_stt", "").strip()]
    retained, seen_raw, duplicate_existing = [], set(), []
    for row in existing:
        raw = row.get("utterance", {}).get("raw_stt", "").strip().casefold()
        if not raw:
            continue
        if raw in seen_raw:
            duplicate_existing.append(row)
            continue
        seen_raw.add(raw); retained.append(row)
    existing = retained
    # Do not repeatedly spend target-STT work on a no-speech source span.  It
    # remains excluded from the formatter manifest rather than being relabelled
    # as a formatter example.
    seen = {row["source"]["record_id"] for row in existing + invalid_existing}
    selected, seconds = [], 0.0
    for line in args.plan.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["source_record_id"] in seen:
            continue
        source = args.audio_dir / f"{row['meeting']}.Mix-Headset.wav"
        start, end = row["source_timestamps"]["start_ms"], row["source_timestamps"]["end_ms"]
        duration = (end - start) / 1000
        if not complete_wav(source) or duration <= 0 or seconds + duration > args.max_audio_seconds:
            continue
        selected.append((row, source)); seconds += duration
        if len(selected) >= args.max_rows:
            break
    if not selected:
        if invalid_existing or duplicate_existing:
            args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing), encoding="utf-8")
        print(json.dumps({"selected_rows": 0, "dropped_empty_existing": len(invalid_existing),
                          "dropped_duplicate_existing": len(duplicate_existing),
                          "reason": "no complete unprocessed planned audio"}))
        return

    from faster_whisper import WhisperModel
    print(json.dumps({"selected_rows": len(selected), "audio_seconds": seconds,
                      "device": args.device, "compute_type": args.compute_type}))
    model = WhisperModel(str(args.model), device=args.device, compute_type=args.compute_type)
    clip_dir = args.out.parent / "audio"; clip_dir.mkdir(parents=True, exist_ok=True)
    skipped_empty = 0
    for row, source in selected:
        record = row["source_record_id"]
        filename = f"{record}.wav".replace("/", "_")
        clip = clip_dir / filename
        slice_wav(source, clip, row["source_timestamps"]["start_ms"], row["source_timestamps"]["end_ms"])
        raw, words, segments = transcribe(model, clip, row["language"])
        if not raw.strip():
            # A no-speech / empty decoding result has no formatter input.  It
            # is an STT-quality observation, not a valid formatter example.
            clip.unlink(missing_ok=True)
            skipped_empty += 1
            continue
        if raw.strip().casefold() in seen_raw:
            clip.unlink(missing_ok=True)
            continue
        seen_raw.add(raw.strip().casefold())
        existing.append({
            "schema_version": "vaani.v6.formatter-example/2",
            "example_id": f"v6-real-{record}",
            "source": {"name": row["source_name"], "record_id": record, "type": "real_derived"},
            "provenance": {"license_ref": row["license_ref"],
                           "transformation_history": ["licensed AMI audio", "frozen-v5-target-stt"]},
            "utterance": {"raw_stt": raw, "reference_transcript": row["reference"],
                          "clean_target": row["reference"]},
            "stt": {"backend": "faster-whisper", "model": args.model.name, "final": True,
                    "words": words, "segments": segments},
            "labels": ["real_derived", "formatter_target_unreviewed"],
            "language": {"primary": row["language"], "code_switching": False,
                         "accent_or_domain": row.get("accent_or_domain")},
            "annotation": {"method": "source-reference-plus-target-stt",
                           "review_status": "needs_human_review", "reviewer": None},
            "split": None, "group_id": row["speaker_id"],
            "audio": {"ref": f"audio/{filename}", "sha256": hashlib.sha256(clip.read_bytes()).hexdigest()},
        })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing), encoding="utf-8")
    print(json.dumps({"new_rows": len(selected) - skipped_empty, "skipped_empty": skipped_empty,
                      "dropped_empty_existing": len(invalid_existing),
                      "dropped_duplicate_existing": len(duplicate_existing), "total_rows": len(existing),
                      "review_status": "needs_human_review", "out": str(args.out)}))


if __name__ == "__main__":
    main()
