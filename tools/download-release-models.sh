#!/usr/bin/env bash
# Download and verify release models into the user-local Linux model directory.
set -euo pipefail
manifest_url="${1:-https://github.com/SaptodeepSarkar/ArchFlow/releases/latest/download/android-models.json}"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/vaani/cleanup"
mkdir -p "$dest"
python3 - "$manifest_url" "$dest" <<'PY'
import hashlib, json, pathlib, re, sys, tempfile, urllib.parse, urllib.request
manifest_url, dest = sys.argv[1], pathlib.Path(sys.argv[2])
if urllib.parse.urlparse(manifest_url).scheme != "https":
    raise SystemExit("model catalog must be loaded over HTTPS")
with urllib.request.urlopen(manifest_url, timeout=30) as response:
    catalog = json.load(response)
if not isinstance(catalog, dict) or not isinstance(catalog.get("models"), list):
    raise SystemExit("invalid model catalog")
for item in catalog["models"]:
    if not isinstance(item, dict) or item.get("kind") != "formatter_v6":
        continue
    url = item.get("url", "")
    parsed = urllib.parse.urlparse(url)
    size = item.get("size_bytes")
    checksum = item.get("sha256", "")
    ident = item.get("id", "unknown")
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit(f"invalid HTTPS model URL for {ident}")
    if type(size) is not int or not 1 <= size <= 1_073_741_824:
        raise SystemExit(f"invalid model size for {ident}")
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
        raise SystemExit(f"invalid model checksum for {ident}")
    target = dest / "model.v6tg"
    temp = None
    try:
        digest = hashlib.sha256()
        received = 0
        with tempfile.NamedTemporaryFile(dir=dest, delete=False) as tmp:
            temp = pathlib.Path(tmp.name)
            with urllib.request.urlopen(url, timeout=120) as source:
                while chunk := source.read(1024 * 1024):
                    received += len(chunk)
                    if received > size:
                        raise SystemExit(f"model download exceeded declared size for {ident}")
                    tmp.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest().lower() != checksum.lower() or received != size:
            raise SystemExit(f"verification failed for {ident}")
        temp.replace(target)
        print(f"installed {ident} -> {target}")
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
PY
