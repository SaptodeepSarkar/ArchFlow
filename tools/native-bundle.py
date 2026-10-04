#!/usr/bin/env python3
"""Build/install bounded, checksummed Linux bundles without replacing user data."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
BINARIES = ("vaanid", "vaani", "vaani-worker", "vaani-desktop", "vaani-linux")
RUNTIMES = ("whisper-cli", "llama-cli", "vaani-whisper-session", "vaani-llama-session")
SCRIPTS = {"fw-transcribe.py": "crates/vaani-worker/fw-transcribe.py", "fw-server.py": "crates/vaani-worker/fw-server.py", "vaani_inject.py": "training/cleanup-llm/scripts/vaani_inject.py", "llm-server.py": "training/cleanup-llm/scripts/llm-server.py"}
MAX_BUNDLE = 8 * 1024**3

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def build(args):
    payload = {}
    for name in BINARIES:
        payload["bin/" + name] = ROOT / "target/release" / name
    for name, source in SCRIPTS.items(): payload["bin/" + name] = ROOT / source
    payload["share/vaani/linux-models.json"] = ROOT / "models/linux-models.json"
    for name in RUNTIMES:
        path = Path(args.runtime) / name
        if not path.is_file():
            raise ValueError(f"Missing runtime: {name}; build pinned CPU runtimes first")
        payload["bin/" + name] = path
    for name, path in {
        "share/vaani/config.example.toml": ROOT / "config.example.toml",
        "share/applications/vaani.desktop": ROOT / "packaging/vaani.desktop",
        "share/icons/hicolor/scalable/apps/vaani.svg": ROOT / "brand/vaani-mark.svg",
        "systemd/vaanid.service": ROOT / "packaging/vaanid.service",
    }.items():
        payload[name] = path
    if args.models:
        for path in Path(args.models).rglob("*"):
            if path.is_file() and not path.is_symlink():
                payload["share/vaani/" + path.relative_to(args.models).as_posix()] = path
    manifest = {"schema": 1, "architecture": platform.machine(), "files": []}
    with tarfile.open(args.output, "w:gz") as archive:
        for name, path in sorted(payload.items()):
            manifest["files"].append({"path": name, "bytes": path.stat().st_size, "sha256": digest(path)})
            archive.add(path, arcname=name, recursive=False)
        body = json.dumps(manifest, sort_keys=True).encode()
        info = tarfile.TarInfo("manifest.json"); info.size = len(body); info.mode = 0o644
        archive.addfile(info, io.BytesIO(body))
    output = Path(args.output)
    output.with_suffix(output.suffix + ".sha256").write_text(digest(output) + "\n")
    print(f"Built {output}; distribute its SHA256 through a trusted release channel.")

def install(args):
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    binaries = Path(os.environ.get("VAANI_BIN_ROOT", str(Path.home() / ".local/bin")))
    with tempfile.TemporaryDirectory(prefix="vaani-install-") as temporary:
        stage = Path(temporary)
        if args.source.startswith("https://"):
            bundle = stage / "download.tar.gz"
            with urllib.request.urlopen(args.source, timeout=60) as response, bundle.open("wb") as output:
                count = 0
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > MAX_BUNDLE: raise ValueError("Bundle download exceeds limit")
                    output.write(chunk)
        else:
            bundle = Path(args.source)
        if bundle.stat().st_size > MAX_BUNDLE or digest(bundle) != args.sha256.lower():
            raise ValueError("Bundle checksum/size mismatch; nothing installed")
        with tarfile.open(bundle) as archive:
            members = archive.getmembers()
            if len(members) > 10000: raise ValueError("Too many bundle entries")
            names = set(); count = 0
            for member in members:
                path = PurePosixPath(member.name)
                if member.name in names or path.is_absolute() or ".." in path.parts or not member.isfile():
                    raise ValueError("Unsafe/duplicate bundle entry")
                names.add(member.name); count += member.size
                if count > MAX_BUNDLE: raise ValueError("Expanded bundle exceeds limit")
            metadata = archive.extractfile("manifest.json").read(1024 * 1024 + 1)
            if len(metadata) > 1024 * 1024: raise ValueError("Manifest exceeds limit")
            manifest = json.loads(metadata)
            if manifest["schema"] != 1 or manifest["architecture"] != platform.machine():
                raise ValueError("Unsupported bundle schema/architecture")
            files = manifest["files"]
            if len(files) != len(names) - 1 or {f["path"] for f in files} != names - {"manifest.json"}:
                raise ValueError("Manifest does not describe all payload files")
            for item in files:
                path = stage / "payload" / item["path"]; path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(item["path"]) as source, path.open("wb") as output:
                    shutil.copyfileobj(source, output)
                if path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
                    raise ValueError("Payload verification failed")
                path.chmod(0o755 if item["path"].startswith("bin/") else 0o644)
        for name in BINARIES + RUNTIMES:
            path = stage / "payload/bin" / name
            if not path.is_file(): raise ValueError(f"Missing required binary {name}")
            result = subprocess.run(["ldd", str(path)], capture_output=True, text=True)
            if "not found" in result.stdout + result.stderr:
                raise ValueError(f"Install missing distribution runtime libraries first: {name}")
        if args.verify_only:
            print("Bundle hashes, architecture, layout and runtime libraries verified; nothing installed.")
            return
        # Preflight succeeded. Keep previous Vaani files for rollback; never overwrite config/models.
        changed = []
        try:
            for item in files:
                relative = item["path"]
                allowed = relative in {"bin/" + name for name in BINARIES + RUNTIMES + tuple(SCRIPTS)} or relative in {"share/applications/vaani.desktop", "share/icons/hicolor/scalable/apps/vaani.svg", "systemd/vaanid.service"} or relative.startswith("share/vaani/")
                if not allowed: raise ValueError("Bundle tries to write outside Vaani-owned destinations")
                if relative.startswith("bin/"): destination = binaries / relative[4:]
                elif relative == "systemd/vaanid.service": destination = config / "systemd/user/vaanid.service"
                elif relative.startswith("share/"): destination = data / relative[6:]
                else: raise ValueError("Unknown destination")
                if relative.startswith("share/vaani/") and destination.exists(): continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                backup = stage / "rollback" / relative
                existed = destination.exists()
                if existed:
                    backup.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(destination, backup)
                changed.append((destination, backup, existed))
                source = stage / "payload" / relative
                with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
                    temporary_path = Path(output.name)
                    if relative == "systemd/vaanid.service":
                        content = source.read_bytes()
                        escaped = str(binaries / "vaanid").replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
                        content = content.replace(b"/usr/bin/vaanid", ('"' + escaped + '"').encode())
                        output.write(content)
                    else:
                        with source.open("rb") as stream: shutil.copyfileobj(stream, output)
                    output.flush(); os.fsync(output.fileno())
                temporary_path.chmod(source.stat().st_mode & 0o777); temporary_path.replace(destination)
            config_file = config / "vaani/config.toml"
            if not config_file.exists():
                config_file.parent.mkdir(parents=True, exist_ok=True)
                with config_file.open("x") as output: output.write((ROOT / "config.example.toml").read_text() if (ROOT / "config.example.toml").exists() else (data / "vaani/config.example.toml").read_text())
                config_file.chmod(0o600)
        except Exception:
            for destination, backup, existed in reversed(changed):
                if existed: shutil.copy2(backup, destination)
                else: destination.unlink(missing_ok=True)
            raise
        print("Installed native Vaani. Add the binary directory to PATH; run systemctl --user daemon-reload.")
        print("Start Vaani, install verified models, then explicitly enable the dictation service.")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pack = sub.add_parser("build"); pack.add_argument("--runtime", required=True); pack.add_argument("--models"); pack.add_argument("--output", required=True)
    setup = sub.add_parser("install"); setup.add_argument("source"); setup.add_argument("--sha256", required=True); setup.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    (build if args.action == "build" else install)(args)
if __name__ == "__main__": main()
