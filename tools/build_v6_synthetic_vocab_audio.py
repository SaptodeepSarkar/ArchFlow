#!/usr/bin/env python3
"""Create self-authored V6 vocabulary audio with local Kokoro TTS.

The generated SQLite manifest is intentionally local-only. It contains source
targets needed for acoustic training but the tool never writes transcript text
to stdout, JSON reports, shell arguments, or repository files.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sqlite3
import tempfile
import wave
from pathlib import Path

from v6_synthetic_vocab_provenance import provenance_record, sha256_file


ROOT = Path(__file__).resolve().parents[1]
PACK_ROOT = ROOT / "models" / "vocabulary"
TEMPLATES = (
    "Please explain {term} in the Vaani project.",
    "Check the {term} configuration before deployment.",
    "Could you repeat the {term} result?",
    "I heard {term} during the review yesterday.",
    "The documentation uses {term} in this example.",
    "We should verify {term} before publishing the update.",
    "Did you say {term} or the earlier option?",
    "Put {term} near the top of the notes.",
    "I will ask the team whether {term} is available.",
    "Can you spell {term} for me one more time?",
    "The new build reports a problem with {term}.",
    "I think the audio says {term}, but I'm not sure.",
)


def terms(packs: list[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pack in packs:
        path = PACK_ROOT / f"{pack}.txt"
        if not path.is_file():
            raise SystemExit(f"unknown vocabulary pack: {pack}")
        for raw in path.read_text(encoding="utf-8").splitlines():
            term = raw.strip()
            if term and not term.startswith("#") and term.casefold() not in seen:
                seen.add(term.casefold())
                found.append((pack, term))
    return found


def compatible_kokoro(model: Path, voices: Path, selected_voices: list[str],
                      requested_provider: str):
    # Keep optional audio dependencies lazy so `--help` and pack inspection
    # work with the system Python. The actual synthesis still uses the pinned
    # local Kokoro environment; runtime provider selection is explicit below.
    import numpy as np
    import onnxruntime as ort
    from kokoro_onnx import Kokoro

    # kokoro-onnx 0.4 expects a single NumPy voice bank. Vaani keeps the
    # official per-voice .bin files, so assemble the small requested bank in
    # memory without duplicating model assets.
    voice_files = {name: voices / f"{name}.bin" for name in selected_voices}
    missing = [name for name, path in voice_files.items() if not path.is_file()]
    if missing:
        raise SystemExit(f"missing requested voice assets: {len(missing)}")
    styles = {}
    for name, path in voice_files.items():
        raw = np.fromfile(path, dtype=np.float32)
        if not raw.size or raw.size % 256:
            raise SystemExit("invalid local voice asset shape")
        styles[name] = raw.reshape(-1, 256)
    # The installed API accepts a .npy voice bank, while the packaged Vaani
    # assets are raw float32 style matrices. Create only a short-lived bridge
    # file, then retain the selected styles in memory.
    descriptor, bridge = tempfile.mkstemp(prefix="vaani-kokoro-", suffix=".npy")
    os.close(descriptor)
    try:
        np.save(bridge, next(iter(styles.values())))
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        available = ort.get_available_providers()
        if requested_provider == "cuda":
            if "CUDAExecutionProvider" not in available:
                raise SystemExit("CUDAExecutionProvider is unavailable in this ONNX Runtime")
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        elif requested_provider == "cpu":
            providers = ["CPUExecutionProvider"]
        else:
            providers = (["CUDAExecutionProvider", "CPUExecutionProvider"]
                         if "CUDAExecutionProvider" in available
                         else ["CPUExecutionProvider"])
        try:
            session = ort.InferenceSession(str(model), sess_options=options,
                                           providers=providers)
        except Exception:
            if requested_provider != "auto" or providers == ["CPUExecutionProvider"]:
                raise
            # Automatic mode can still build reproducible CPU data on hosts
            # where the CUDA package exists but its shared libraries do not.
            session = ort.InferenceSession(str(model), sess_options=options,
                                           providers=["CPUExecutionProvider"])
        tts = Kokoro.from_session(session, bridge)
    finally:
        Path(bridge).unlink(missing_ok=True)
    tts.voices = styles
    session = tts.sess

    class SessionCompat:
        def get_providers(self):
            return session.get_providers()

        def get_inputs(self):
            return session.get_inputs()

        def run(self, names, inputs):
            inputs = dict(inputs)
            if "speed" in inputs:
                inputs["speed"] = np.asarray(inputs["speed"], dtype=np.float32)
            if "style" in inputs and np.asarray(inputs["style"]).ndim == 1:
                inputs["style"] = np.asarray(inputs["style"], dtype=np.float32)[None, :]
            return session.run(names, inputs)

    tts.sess = SessionCompat()
    return tts, np, ort.__version__


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--voices", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--packs", nargs="+", default=["acronyms", "mobile-stt"])
    parser.add_argument("--voices-list", nargs="+", default=["af_sarah", "am_adam"])
    parser.add_argument("--execution-provider", choices=("auto", "cuda", "cpu"),
                        default="auto",
                        help="prefer CUDA when available; explicit cuda fails rather than silently using CPU")
    parser.add_argument("--max-terms", type=int, default=0,
                        help="0 means every term in the selected packs")
    args = parser.parse_args()
    selected = terms(args.packs)
    if args.max_terms:
        selected = selected[:args.max_terms]
    if not selected:
        raise SystemExit("no vocabulary terms selected")
    tts, np, runtime_version = compatible_kokoro(
        args.model, args.voices, args.voices_list, args.execution_provider)
    audio_dir = args.out / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    database = args.out / "manifest.sqlite3"
    db = sqlite3.connect(database)
    db.execute("""CREATE TABLE IF NOT EXISTS examples (
        id TEXT PRIMARY KEY, audio_path TEXT NOT NULL, target_text TEXT NOT NULL,
        term_pack TEXT NOT NULL, term_sha256 TEXT NOT NULL, template_index INTEGER NOT NULL,
        voice TEXT NOT NULL, sample_rate INTEGER NOT NULL, audio_sha256 TEXT NOT NULL,
        provenance TEXT NOT NULL)""")
    model_sha = sha256_file(args.model)
    voice_hashes = {
        name: sha256_file(args.voices / f"{name}.bin")
        for name in args.voices_list
    }
    try:
        package_version = importlib.metadata.version("kokoro-onnx")
    except importlib.metadata.PackageNotFoundError:
        package_version = "unreported"
    created, skipped, samples = 0, 0, 0
    for pack, term in selected:
        for template_index, template in enumerate(TEMPLATES):
            text = template.format(term=term)
            for voice_name in args.voices_list:
                identity = hashlib.sha256(f"v6-synthetic-vocab-v1\0{pack}\0{term}\0{template_index}\0{voice_name}".encode()).hexdigest()
                output = audio_dir / f"{identity}.wav"
                existing = db.execute(
                    "SELECT audio_sha256, provenance, target_text, sample_rate "
                    "FROM examples WHERE id = ?",
                    (identity,),
                ).fetchone()
                if existing and output.is_file():
                    expected_provenance = provenance_record(
                        model_sha256=model_sha, voice_asset_sha256=voice_hashes[voice_name],
                        voice_id=voice_name, template_index=template_index,
                        sample_rate=existing[3],
                        runtime_version=runtime_version, package_version=package_version,
                        execution_provider=tts.sess.get_providers()[0],
                    )
                    if (existing[1] == expected_provenance and existing[2] == text
                            and sha256_file(output) == existing[0]):
                        skipped += 1
                        continue
                audio, sample_rate = tts.create(text, voice=voice_name, speed=1.0)
                pcm = np.clip(np.asarray(audio), -1.0, 1.0)
                pcm = (pcm * 32767.0).astype("<i2")
                with wave.open(str(output), "wb") as handle:
                    handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(sample_rate)
                    handle.writeframes(pcm.tobytes())
                digest = hashlib.sha256(output.read_bytes()).hexdigest()
                provenance = provenance_record(
                    model_sha256=model_sha, voice_asset_sha256=voice_hashes[voice_name],
                    voice_id=voice_name,
                    template_index=template_index, sample_rate=sample_rate,
                    runtime_version=runtime_version, package_version=package_version,
                    execution_provider=tts.sess.get_providers()[0],
                )
                db.execute("INSERT OR REPLACE INTO examples VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                           (identity, str(output), text, pack, hashlib.sha256(term.encode()).hexdigest(),
                            template_index, voice_name, sample_rate, digest,
                            provenance))
                # A vocabulary build is intentionally long-running. Commit
                # every completed clip so an interruption resumes safely and
                # never leaves valid audio without its provenance record.
                db.commit()
                created += 1; samples += len(pcm)
    db.commit(); db.close()
    print(json.dumps({"schema_version": 1, "created": created, "skipped": skipped,
                      "terms": len(selected), "templates": len(TEMPLATES),
                      "voices": len(args.voices_list), "audio_samples": samples}, sort_keys=True))


if __name__ == "__main__":
    main()
