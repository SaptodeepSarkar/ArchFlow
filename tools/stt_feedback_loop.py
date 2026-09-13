#!/usr/bin/env python3
"""Collect or score STT feedback without mixing private and public data.

Examples:
  python3 tools/stt_feedback_loop.py record
  python3 tools/stt_feedback_loop.py public --limit 100

Record mode asks for a human reading of each prompt, transcribes with the
active v2 model, and writes a JSONL report. The human reference is the reward
target; the model transcript is never treated as ground truth. Public mode
downloads a Hugging Face dataset into the project cache and evaluates it
separately. Both modes use CPU by default so they do not fight training VRAM.
"""
from __future__ import annotations

import argparse
import itertools
import random
import json
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COZY = Path("/home/saptodeep/Projects/Cozy/stt-finetune")
DEFAULT_MODEL = Path.home() / ".local/share/vaani/models/cozy"
DEFAULT_PROMPTS = ROOT / "data/stt_feedback_prompts.txt"
SR = 16_000


def score(reference: str, hypothesis: str) -> dict:
    import jiwer

    ref = reference.strip()
    hyp = hypothesis.strip()
    distance = jiwer.process_words(ref, hyp)
    words = max(1, len(ref.split()))
    protected = re.findall(
        r"(?:https?://\S+|/[\w./-]+|\b[A-Z][A-Z0-9]{1,}\b|\b\d+(?:\.\d+)?\b|Celsius|narcotics|acrobat|glioblastoma|pharmacokinetics|otorhinolaryngology)",
        ref,
    )
    missing = [term for term in protected if term.lower() not in hyp.lower()]
    ref_words = ref.split()
    hyp_words = hyp.split()
    errors = []
    for chunk in distance.alignments[0]:
        if chunk.type == "equal":
            continue
        errors.append({
            "type": chunk.type,
            "reference_words": ref_words[chunk.ref_start_idx:chunk.ref_end_idx],
            "hypothesis_words": hyp_words[chunk.hyp_start_idx:chunk.hyp_end_idx],
            "reference_position": chunk.ref_start_idx,
        })
    wer = distance.wer
    # This is an auditable reward for ranking candidates, not a claim that WER
    # alone captures speech quality. Missing critical terms receive extra cost.
    reward = max(-1.0, 1.0 - wer - 0.25 * len(missing))
    return {
        "wer": round(wer, 6),
        "substitutions": distance.substitutions,
        "deletions": distance.deletions,
        "insertions": distance.insertions,
        "errors": errors,
        "protected_terms": protected,
        "missing_protected_terms": missing,
        "reward": round(reward, 6),
        "reference_confirmed": False,
    }


def transcriber(model_path: Path, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    model = WhisperModel(str(model_path), device=device, compute_type=compute_type)

    def run(audio):
        segments, _ = model.transcribe(
            audio, language="en", beam_size=1,
            condition_on_previous_text=False,
            initial_prompt="Indian English. HTML CSS MCP CTC Celsius narcotics acrobat.",
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    return run


def record_wav(path: Path, max_seconds: int = 15) -> None:
    print("Speak now. Press ENTER when finished.")
    proc = subprocess.Popen(
        ["arecord", "-q", "-f", "S16_LE", "-r", str(SR), "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE,
    )
    chunks: list[bytes] = []
    started = time.monotonic()
    try:
        while time.monotonic() - started < max_seconds:
            raw = proc.stdout.read(SR // 10 * 2) if proc.stdout else b""
            if raw:
                chunks.append(raw)
            if sys.stdin in select_readable():
                sys.stdin.readline()
                break
    finally:
        proc.terminate()
        proc.wait(timeout=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SR)
        output.writeframes(b"".join(chunks))


def select_readable():
    import select

    readable, _, _ = select.select([sys.stdin], [], [], 0)
    return readable


def audio_array(path: Path):
    import librosa

    audio, _ = librosa.load(str(path), sr=SR, mono=True)
    return audio


def run_record(args) -> None:
    prompts = [line.strip() for line in args.prompts.read_text().splitlines() if line.strip()]
    out_dir = args.out / "private" / f"session_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    transcribe = transcriber(args.model, args.device, args.compute_type)
    report = out_dir / "feedback.jsonl"
    with report.open("w", encoding="utf-8") as handle:
        for index, reference in enumerate(prompts):
            print(f"\n[{index + 1}/{len(prompts)}] {reference}")
            input("Press ENTER to record...")
            wav = out_dir / f"{index:03d}.wav"
            record_wav(wav, args.max_seconds)
            hypothesis = transcribe(audio_array(wav))
            metrics = score(reference, hypothesis)
            print(f"STT: {hypothesis}\nWER={metrics['wer']:.3f} reward={metrics['reward']:.3f}")
            confirmed = input("Reference correct? [Y/n/r=record again/q=quit] ").strip().lower()
            if confirmed == "q":
                break
            if confirmed == "r":
                wav.unlink(missing_ok=True)
                continue
            metrics["reference_confirmed"] = confirmed != "n"
            row = {"audio_path": str(wav), "reference": reference, "hypothesis": hypothesis, **metrics}
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
    print(f"Saved private feedback: {report}")


def run_public(args) -> None:
    from datasets import Audio, load_dataset
    import soundfile as sf

    load_args = {"split": args.split, "cache_dir": str(args.cache), "streaming": True}
    if args.config:
        load_args["name"] = args.config
    dataset = load_dataset(args.dataset, **load_args)
    if args.shuffle:
        dataset = dataset.shuffle(seed=args.seed, buffer_size=args.shuffle_buffer)
    # decode=False avoids requiring torchcodec; librosa can decode the local
    # cached files and this keeps the evaluator usable in a small CPU venv.
    dataset = dataset.cast_column("audio", Audio(sampling_rate=SR, decode=False))
    transcribe = transcriber(args.model, args.device, args.compute_type)
    args.out.mkdir(parents=True, exist_ok=True)
    suffix = f"_{args.config}" if args.config else ""
    report = args.out / f"public_{args.dataset.replace('/', '_')}{suffix}_{args.split}.jsonl"
    audio_dir = args.out / f"public_audio_{args.dataset.replace('/', '_')}{suffix}_{args.split}"
    audio_dir.mkdir(parents=True, exist_ok=True)
    start_index = 0
    if args.resume and report.exists():
        for line in report.read_text(encoding="utf-8").splitlines():
            try:
                start_index = max(start_index, int(json.loads(line).get("index", -1)) + 1)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        print(f"resuming public feedback at dataset index {start_index}", flush=True)
    mode = "a" if args.resume else "w"
    with report.open(mode, encoding="utf-8") as handle:
        rows = itertools.islice(dataset, start_index, args.limit) if args.limit else itertools.islice(dataset, start_index, None)
        for index, row in enumerate(rows, start=start_index):
            audio_info = row["audio"]
            if audio_info.get("array") is not None:
                audio = audio_info["array"]
            elif audio_info.get("bytes"):
                # Streaming parquet commonly exposes encoded bytes plus a
                # non-local archive filename. Decode the bytes, not the path.
                with tempfile.NamedTemporaryFile(suffix=Path(audio_info.get("path", "audio.mp3")).suffix or ".mp3") as tmp:
                    tmp.write(audio_info["bytes"])
                    tmp.flush()
                    audio = audio_array(Path(tmp.name))
            elif audio_info.get("path"):
                audio = audio_array(Path(audio_info["path"]))
            else:
                raise ValueError(f"audio row {index} has neither bytes nor path")
            reference = str(row.get(args.text_column, "")).strip()
            if not reference:
                raise ValueError(f"empty reference at dataset row {index}; use --text-column")
            hypothesis = transcribe(audio)
            metrics = score(reference, hypothesis)
            wav = audio_dir / f"{index:06d}.wav"
            sf.write(str(wav), audio, SR)
            handle.write(json.dumps({"dataset": args.dataset, "config": args.config, "split": args.split, "index": index, "audio_path": str(wav), "reference": reference, "hypothesis": hypothesis, **metrics, "reference_confirmed": True}, ensure_ascii=False) + "\n")
            if (index + 1) % 10 == 0:
                print(f"{index + 1} evaluated", flush=True)
    print(f"Saved public feedback: {report}")


def run_manifest(args) -> None:
    """Score already-downloaded labelled Indian-English audio offline."""
    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    valid = []
    for row in rows:
        path = Path(row["audio_path"])
        if not path.is_absolute():
            path = COZY / path
        if path.exists():
            row = dict(row)
            row["audio_path"] = str(path)
            valid.append(row)
    print(f"manifest rows={len(rows)} valid_audio={len(valid)} missing={len(rows) - len(valid)}", flush=True)
    random.Random(args.seed).shuffle(valid)
    rows = valid[:args.limit] if args.limit else valid
    transcribe = transcriber(args.model, args.device, args.compute_type)
    args.out.mkdir(parents=True, exist_ok=True)
    report = args.out / f"feedback_{args.manifest.stem}_{len(rows)}.jsonl"
    with report.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            audio_path = Path(row["audio_path"])
            hypothesis = transcribe(audio_array(audio_path))
            reference = str(row.get("text", row.get("reference", ""))).strip()
            metrics = score(reference, hypothesis)
            handle.write(json.dumps({"dataset": "local_manifest", "index": index,
                                     "audio_path": str(audio_path), "reference": reference,
                                     "hypothesis": hypothesis, **metrics,
                                     "reference_confirmed": True}, ensure_ascii=False) + "\n")
            if (index + 1) % 10 == 0:
                print(f"{index + 1}/{len(rows)}", flush=True)
    print(f"Saved manifest feedback: {report}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["record", "public", "manifest"])
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--out", type=Path, default=COZY / "data/stt_feedback")
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--max-seconds", type=int, default=15)
    parser.add_argument("--dataset", default="ishands/commonvoice-indian_accent")
    parser.add_argument("--config", default="")
    parser.add_argument("--split", default="train")
    parser.add_argument("--text-column", default="sentence")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--shuffle", action="store_true", help="sample varied records instead of dataset order")
    parser.add_argument("--seed", type=int, default=20260913)
    parser.add_argument("--shuffle-buffer", type=int, default=10_000)
    parser.add_argument("--resume", action="store_true", help="continue an interrupted public report")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--cache", type=Path, default=COZY / ".hf_cache")
    args = parser.parse_args()
    if args.mode == "record":
        run_record(args)
    elif args.mode == "public":
        run_public(args)
    else:
        if not args.manifest:
            parser.error("manifest mode requires --manifest")
        run_manifest(args)


if __name__ == "__main__":
    main()
