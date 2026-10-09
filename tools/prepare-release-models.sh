#!/usr/bin/env bash
# Stage model assets and create the manifest uploaded with a GitHub release.
# Large weights never belong in Git. Every required path must be supplied by
# the release operator, otherwise this script fails before publishing.
set -euo pipefail

out="${1:-dist/models}"
release_tag="${RELEASE_TAG:?set RELEASE_TAG to the tag being published}"
android_stt="${ANDROID_STT_MODEL:?set ANDROID_STT_MODEL to ggml-base.bin}"
android_v6_stt="${ANDROID_V6_STT_MODEL:-}"
android_formatter="${ANDROID_FORMATTER_MODEL:?set ANDROID_FORMATTER_MODEL to the Android formatter GGUF}"
v6_tagger="${V6_TAGGER_MODEL:-}"

[[ "$release_tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || {
  echo "invalid release tag: $release_tag" >&2
  exit 1
}
IFS=. read -r major minor patch <<< "${release_tag#v}"
if (( ${#major} > 4 || ${#minor} > 3 || ${#patch} > 3 || minor > 999 || patch > 999 || major > 2100 || (major == 2100 && (minor != 0 || patch != 0)) )); then
  echo "release version exceeds the supported Android versionCode range: $release_tag" >&2
  exit 1
fi
if (( major == 0 && minor == 0 && patch == 0 )); then
  echo "release version must produce a positive Android versionCode" >&2
  exit 1
fi

for path in "$android_stt" "$android_formatter"; do
  test -s "$path" || { echo "missing or empty model: $path" >&2; exit 1; }
done
if [ -n "$android_v6_stt" ]; then
  test -s "$android_v6_stt" || { echo "missing or empty V6 STT model: $android_v6_stt" >&2; exit 1; }
fi
if [ -n "$v6_tagger" ]; then
  test -s "$v6_tagger" || { echo "missing or empty V6 formatter candidate: $v6_tagger" >&2; exit 1; }
fi
mkdir -p "$out"
rm -f "$out/ggml-v6.bin" "$out/vaani-v6-tagger.v6tg"
cp "$android_stt" "$out/ggml-base.bin"
if [ -n "$android_v6_stt" ]; then cp "$android_v6_stt" "$out/ggml-v6.bin"; fi
cp "$android_formatter" "$out/vaani-v5-formatter-q8.gguf"
if [ -n "$v6_tagger" ]; then cp "$v6_tagger" "$out/vaani-v6-tagger.v6tg"; fi

python3 - "$out" "$release_tag" > "$out/android-models.json" <<'PY'
import hashlib, json, pathlib, sys
root, tag = pathlib.Path(sys.argv[1]), sys.argv[2]
def asset(name, ident, kind, runtime, note):
    path = root / name
    return {"id": ident, "kind": kind, "runtime": runtime,
            "android_compatible": kind in {"stt", "stt_v6"} or ident.endswith("android"),
            "filename": name,
            "url": f"https://github.com/SaptodeepSarkar/ArchFlow/releases/download/{tag}/{name}",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size, "license": "See model card", "note": note}
models = [
    asset("ggml-base.bin", "whisper-base-android", "stt", "whisper-ggml", "Android V5 baseline."),
    asset("vaani-v5-formatter-q8.gguf", "vaani-v5-formatter-q8-android", "formatter", "llama-gguf", "Android V5 fallback formatter."),
]
if (root / "vaani-v6-tagger.v6tg").is_file():
    models.append(asset("vaani-v6-tagger.v6tg", "vaani-v6-tagger", "formatter_v6", "vaani-v6-tagger", "Shared V6 formatter candidate; not Android-qualified."))
if (root / "ggml-v6.bin").is_file():
    models.insert(1, asset("ggml-v6.bin", "whisper-v6-android-candidate", "stt_v6", "whisper-ggml", "V6 candidate; staged beside Base pending qualification."))
print(json.dumps({"schema_version": 2, "models": models}, indent=2))
PY
echo "staged model assets and $out/android-models.json"
