# Redesign cloud verification — 4 October 2026

Implementation is available for review, not yet certified for a physical-device
release. The user authorized continuing after the phase-1 safety checkpoint and
handing device validation to a separate testing agent. No GitHub push was made.

| Check | Result |
| --- | --- |
| Rust workspace tests | 99 passed, 0 failed, 1 ignored |
| Android JVM tests | 32 passed, 0 failed; includes Java → Rust TLS transfer |
| Android build | debug APK assembled; instrumentation sources compiled, not run |
| Bundle safety tests | 4 passed: corruption, traversal, config preservation, rollback |
| Native runtimes | pinned CPU Whisper/llama builds completed |
| Release bundle | final payload preflight passed and installed into an isolated temporary prefix |
| GTK | release build and Xvfb smoke; X11 screenshot inspected |
| Physical Android/Linux | unavailable; battery, microphone, Wayland, full device-pair matrix unrun |

Whisper's public `jfk.wav` sample (11 seconds) produced nonempty, identical
transcripts through the same private-pipe worker on two successive requests:
3.611 seconds cold wall time / 3,005 ms inference, then 2.780 seconds warm wall
time / 2,776 ms inference. This is one cloud CPU trial per condition, without
energy measurement or statistical significance. Model SHA-256 matched the
published catalog. Neither sample text nor captured user dictation is logged.

The verified 386,405,344-byte published GGUF formatter also returned nonempty
output through its native helper: 1.544 seconds wall / 1,333 ms inference, one
synthetic request. This checks runtime compatibility, not formatter quality.

Native retention has an exclusive process lease, bounded private frames and a
60-second per-request timeout. Economy destroys/reaps the process before the
operation returns; optional idle expiry is capped at 120 seconds. A fake-worker
regression checks reuse, expiry and Economy disposal. Native cancellation and
Android JNI disposal can wait for an active operation to finish. The older
CT2/Python reaper has 30-second granularity, with threshold adjusted to respect
the overall retention ceiling; its exact timing still needs device measurement.

Remaining release checks: real microphone/editor interaction and cancellation,
physical idle/active power comparisons, Secret Service/Keystore failure and
migration interruption, camera/QR interaction, both directions of every device
pair, target-distribution online/offline installs, and actual Wayland overlay
behavior. Linux supports QR-image import and manual invitation paste; live camera
capture is not implemented. Portable preferences are approved snapshots rather
than clocked merge records; partial preference/record failures must be tested.
Graphify is unavailable, so its graph was not refreshed.

Run the handoff in `../../TESTING_AGENT_PROMPT.md`. Report failed and unrun gates
explicitly; cloud/JVM successes must not become physical-device passes.
