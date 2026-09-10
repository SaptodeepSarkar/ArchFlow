# Performance budgets (design targets — measure, don't promise)

Economy settled-idle (10 s after helpers exit): controller RSS ≤ 30 MiB
(goal < 20), avg CPU < 0.1% of one core over 60 s, no stream/worker/CUDA
context/timers/polling, no routine disk writes. Report tree RSS+PSS, shared
vs file-backed vs page cache separately; clipboard helper separately.

UI: 150 ms warm / 400 ms cold appearance. Capture readiness 250 ms.
No subsecond transcription promise.

## How to measure (this machine)

```sh
cargo build --release
./target/release/vaanid &            # or the user service
vaani doctor
bash tools/measure-idle.sh           # idle RSS/CPU/leak report
python3 tools/bench.py --n 20 --secs 5   # p50/p95 stop-to-text
python3 tools/wer.py --ref tests/fixtures/en.ref --hyp out.txt --lang en
```

Report with: sample count, p50/p95, CPU/GPU backend, model, threads, power
mode, cold vs warm. Targets missed are reported honestly.
GPU measured only during explicit benchmarks — no background VRAM polling
(the dGPU must not wake for UI rendering or timers).

## Status on this box (2026-09-10)

Unit/protocol/VAD/reconcile tests: 20+ passing. Laptop end-to-end numbers
pending model download (`tools/model-setup.py --model base`) + mic access.
Nothing here is presented as a measured benchmark until those runs exist.

## First real numbers (2026-09-11, whisper.cpp v1.7.6 CPU, ggml base, 4 threads, i5-12450HX)

- `samples/jfk.wav` (11 s, 16 kHz mono) piped to vaani-worker: **1.6 s**,
  transcript matches reference (punctuation only differs). Single sample —
  a fixture check, NOT a benchmark.
- Room loopback (speakers → laptop mic → toggle → stop → paste): 14 s audio,
  stop-to-text **3175 ms** (inference 3174 ms), dispatch **4 ms**, end state
  IDLE. Transcript fragmentary ("Hello. What? …") — acoustic loopback through
  EasyEffects echo-cancellation, not model error; direct-pipe test above is
  the STT evidence. Real-voice numbers pending manual checks.
