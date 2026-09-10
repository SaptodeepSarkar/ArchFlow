# native/worker — whisper.cpp integration

`vaani-worker` (crates/vaani-worker) is the only process that loads models.

- One-shot protocol: argv selects model/language/threads; raw f32-LE mono
  16 kHz PCM arrives on stdin; exactly one JSON line leaves on stdout.
- It shells to a pinned `whisper-cli` build (see WHISPER_PIN) with a verified
  ggml model, else runs silence-safe `cpu-stub` (inserts nothing, labelled).
- Never loads CUDA into the idle controller; CUDA only here and only when
  `VAANI_CUDA=1` with a user-selected GPU binary present.
- Temp wav files exist ONLY inside this short-lived process and are removed
  immediately; production audio transport is the inherited stdin pipe.

Build whisper.cpp (pinned) — reproducible inputs, documented versions:

```sh
git clone --branch v1.7.6 --depth 1 https://github.com/ggml-org/whisper.cpp native/worker/upstream
cmake -S native/worker/upstream -B native/worker/build -DWHISPER_BUILD_TESTS=OFF
cmake --build native/worker/build -j"$(nproc)"
sudo install -m755 native/worker/build/bin/whisper-cli /usr/local/bin/whisper-cli
```
