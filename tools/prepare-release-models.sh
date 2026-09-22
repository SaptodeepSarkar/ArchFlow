#!/usr/bin/env bash
# Stage model assets and create the manifest uploaded with a GitHub release.
# Large weights never belong in Git. Every required path must be supplied by
# the release operator, otherwise this script fails before publishing.
set -euo pipefail

out="${1:-dist/models}"
release_tag="${RELEASE_TAG:?set RELEASE_TAG to the tag being published}"
android_stt="${ANDROID_STT_MODEL:?set ANDROID_STT_MODEL to ggml-base.bin}"
android_formatter="${ANDROID_FORMATTER_MODEL:?set ANDROID_FORMATTER_MODEL to the Android formatter GGUF}"
v6_tagger="${V6_TAGGER_MODEL:?set V6_TAGGER_MODEL to model.v6tg}"

for path in "$android_stt" "$android_formatter" "$v6_tagger"; do
  test -s "$path" || { echo "missing or empty model: $path" >&2; exit 1; }
done
mkdir -p "$out"
cp "$android_stt" "$out/ggml-base.bin"
cp "$android_formatter" "$out/vaani-v5-formatter-q8.gguf"
cp "$v6_tagger" "$out/vaani-v6-tagger.v6tg"

python3 - "$out" "$release_tag" > "$out/android-models.json" <<'PY'
import hashlib, json, pathlib, sys
root, tag = pathlib.Path(sys.argv[1]), sys.argv[2]
def asset(name, ident, kind, runtime, note):
    path = root / name
    return {"id": ident, "kind": kind, "runtime": runtime,
            "android_compatible": kind in {"stt", "formatter_v6"} or ident.endswith("android"),
            "filename": name,
            "url": f"https://github.com/SaptodeepSarkar/ArchFlow/releases/download/{tag}/{name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size, "license": "See model card", "note": note}
print(json.dumps({"schema_version": 2, "models": [
    asset("ggml-base.bin", "whisper-base-android", "stt", "whisper-ggml", "Android V5 baseline."),
    asset("vaani-v5-formatter-q8.gguf", "vaani-v5-formatter-q8-android", "formatter", "llama-gguf", "Android V5 fallback formatter."),
    asset("vaani-v6-tagger.v6tg", "vaani-v6-tagger", "formatter_v6", "vaani-v6-tagger", "Shared V6 source-grounded formatter."),
]}, indent=2))
PY
echo "staged model assets and $out/android-models.json"
