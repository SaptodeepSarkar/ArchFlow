"""Hash-only run identity for reproducible V6 STT continuation."""
import hashlib
import json
from pathlib import Path
import sqlite3


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_identity(manifests, sqlite_manifests, model, code, settings, adapters=()):
    audio = set()
    input_hashes = {}
    for path in manifests:
        input_hashes[str(path.resolve())] = digest_file(path)
        for line in path.read_text().splitlines():
            if line.strip():
                audio.add(Path(json.loads(line)["audio_path"]).resolve())
    for path in sqlite_manifests:
        input_hashes[str(path.resolve())] = digest_file(path)
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            audio.update(Path(row[0]).resolve() for row in
                         connection.execute("SELECT audio_path FROM examples"))
        finally:
            connection.close()
    audio_digest = hashlib.sha256()
    for path in sorted(audio):
        audio_digest.update(str(path).encode())
        audio_digest.update(b"\0")
        audio_digest.update(bytes.fromhex(digest_file(path)))
    model_files = sorted(path for path in model.rglob("*") if path.is_file()
                         and path.suffix in {".json", ".safetensors", ".bin", ".txt", ".model"})
    if not model_files or not audio:
        raise ValueError("model assets and training audio must be nonempty")
    for adapter in adapters:
        assets = sorted(path for path in adapter.rglob("*") if path.is_file()
                        and path.suffix in {".json", ".safetensors", ".bin"})
        if not assets:
            raise ValueError("initial adapter assets are missing")
        model_files.extend(assets)
    return {"schema_version": 1, "settings": settings, "input_hashes": input_hashes,
            "audio_files": len(audio), "audio_sha256": audio_digest.hexdigest(),
            "model_hashes": {str(path.resolve()): digest_file(path) for path in model_files},
            "code_hashes": {str(path.resolve()): digest_file(path) for path in code}}


def verify_or_create(out, identity, resume=None):
    record = out / "v6-run-manifest.json"
    if resume is not None:
        checkpoint = resume.resolve()
        if (checkpoint.parent != out.resolve()
                or not checkpoint.name.startswith("checkpoint-")
                or any(not (checkpoint / name).is_file() for name in
                       ("trainer_state.json", "optimizer.pt", "scheduler.pt", "rng_state.pth"))
                or not any((checkpoint / name).is_file() for name in
                           ("adapter_model.safetensors", "adapter_model.bin"))):
            raise ValueError("resume requires a checkpoint inside this run")
        if not record.is_file() or json.loads(record.read_text()) != identity:
            raise ValueError("resume data/model/code/settings differ from the original run")
    else:
        if out.exists():
            raise ValueError("refusing existing V6 STT run directory")
        out.mkdir(parents=True)
        with record.open("x") as stream:
            stream.write(json.dumps(identity, indent=2, sort_keys=True) + "\n")
