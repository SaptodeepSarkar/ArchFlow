#!/usr/bin/env bash
# Download and verify release models into the user-local Linux model directory.
set -euo pipefail
manifest_url="${1:-https://github.com/SaptodeepSarkar/ArchFlow/releases/latest/download/android-models.json}"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/vaani/cleanup"
mkdir -p "$dest"
python3 - "$manifest_url" "$dest" <<'PY'
import hashlib, json, pathlib, sys, tempfile, urllib.request
manifest_url, dest = sys.argv[1], pathlib.Path(sys.argv[2])
catalog = json.load(urllib.request.urlopen(manifest_url, timeout=30))
for item in catalog.get("models", []):
    if item.get("kind") not in {"formatter_v6"}: continue
    target = dest / "model.v6tg"
    with tempfile.NamedTemporaryFile(dir=dest, delete=False) as tmp:
        temp = pathlib.Path(tmp.name)
        with urllib.request.urlopen(item["url"], timeout=120) as source:
            while chunk := source.read(1024 * 1024): tmp.write(chunk)
    digest = hashlib.sha256(temp.read_bytes()).hexdigest()
    if digest.lower() != item["sha256"].lower() or temp.stat().st_size != item["size_bytes"]:
        temp.unlink(missing_ok=True)
        raise SystemExit(f"verification failed for {item['id']}")
    temp.replace(target)
    print(f"installed {item['id']} -> {target}")
PY
