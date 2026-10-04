#!/usr/bin/env bash
# CPU-only, pinned runtimes; no audio, weights or GPU libraries in the idle GUI.
set -euo pipefail
runtime_root="${1:-.vaani/native-runtimes}"
mkdir -p "$runtime_root/bin"
build_runtime() {
  local name="$1" source_url="$2" revision="$3" target="$4"
  local source_path="$runtime_root/$name"
  if [ ! -d "$source_path/.git" ]; then git init "$source_path"; fi
  git -C "$source_path" fetch --depth=1 "$source_url" "$revision"
  git -C "$source_path" checkout --detach "$revision"
  test "$(git -C "$source_path" rev-parse HEAD)" = "$revision"
  cmake -S "$source_path" -B "$source_path/build" -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_CUDA=OFF -DGGML_VULKAN=OFF -DGGML_BLAS=OFF -DLLAMA_CURL=OFF -DWHISPER_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DWHISPER_BUILD_TESTS=OFF
  cmake --build "$source_path/build" --target "$target" -j "${VAANI_BUILD_JOBS:-4}"
  install -m755 "$source_path/build/bin/$target" "$runtime_root/bin/$target"
}
build_runtime whisper https://github.com/ggml-org/whisper.cpp.git a8d002cfd879315632a579e73f0148d06959de36 whisper-cli
build_runtime llama https://github.com/ggml-org/llama.cpp.git 703f9e32c4eb3166f8d63007c26e31a1466c21af llama-cli
# Small private-pipe helpers enable short retention without any TCP listener.
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
for backend in whisper llama; do
  c++ -O2 -std=c++17 -I"$runtime_root/$backend/include" -I"$runtime_root/$backend/ggml/include" -I"$runtime_root/llama/vendor/nlohmann" \
    "$repo_root/native/worker/$backend-session.cpp" -o "$runtime_root/bin/vaani-$backend-session" \
    "$runtime_root/$backend/build/src/lib$backend.a" "$runtime_root/$backend/build/ggml/src/libggml.a" \
    "$runtime_root/$backend/build/ggml/src/libggml-cpu.a" "$runtime_root/$backend/build/ggml/src/libggml-base.a" -fopenmp -pthread -ldl -lm
 done
