# Phase 1: baseline and Android safety

Historical phase-1 checkpoint (before GUI/sync migration): safety implementation and cloud build/JVM verification complete; emulator interaction and physical-device completion gates are pending. GUI, Firebase and personalization data formats are unchanged.

## Changes to review together

- Shared session gate rejects duplicate STT results and invalidates callbacks, formatter delivery and delayed UI resets after cancellation/replacement.
- Process-wide ownership makes starting overlay dictation cancel any IME capture/formatting, and vice versa, before the new session starts. Ownership is released on completion and teardown.
- Overlay delivery holds a lease on the original accessibility editor. Switching away and back invalidates it; a still-current result uses clipboard fallback if the target cannot safely accept paste.
- Accessibility paste requires a refreshed, focused, editable, non-password node. Removed SET_TEXT fallback that rewrote the complete field without respecting selection.
- IME captures its original input connection and field policy, invalidates on input changes and cancels on input-view/input completion.
- Audio capture uses synchronized idempotent ownership and nonblocking reads; cancellation and coroutine cleanup cannot release the same recorder twice. Cancellation is distinct from recognition failure.
- Whisper/LLM cancellation is checked before/after blocking native calls. A native operation may still finish internally before its model can be safely released; coroutine cancellation is not claimed to interrupt JNI computation.
- Android recognizer is destroyed on result/error as well as cancellation. RMS updates are limited to 20Hz during native recording. Own accessibility events skip window scans; keyboard bounds refresh only on window events; unchanged focus observations no longer notify listeners.

## Measurements and limits

Verified in this cloud workspace on 4 October 2026:

- `testDebugUnitTest`: 28 executed, 0 failures/errors/skips, including 10 new session/target/ownership/resource regression tests and expanded event-policy coverage.
- `assembleDebug`: passed. ARM64 `libwhisper.so` and `libllama.so` are present in the resulting debug APK.
- `compileDebugAndroidTestKotlin`: passed; instrumented tests compiled but were not run.
- `git diff --check` and profiling-script shell syntax validation: passed.
- Build used Gradle 8.9, Temurin JDK 17, SDK 35 and the environment's Java CA trust store/proxy. Download verification and TLS validation remained enabled. Existing source deprecation warnings remain.
- Graphify refresh could not run because the graphify executable is unavailable in this workspace.

No physical phone, microphone, GPU or target Wayland session is attached to this cloud workspace. Android battery reduction, physical microphone teardown timing, JNI cancellation behavior and editor interaction remain unmeasured. Do not treat JVM tests or cloud CPU measurements as battery evidence.

The unchanged Linux daemon was sampled in this cloud container on 4 October 2026 for 10.001 seconds in IDLE, after a successful CLI status request. Resident memory was 6,340 KiB initially and 6,396 KiB finally. Measured process CPU tick delta was zero (below the sampling resolution, not proof of no work). This excludes child pgrep CPU and does not demonstrate target-laptop power consumption. No microphone or model inference was exercised. The existing 2-second hyprlock process polling and fail-open lock detection remain known work for a separately tested Linux safety change.

## Reproduce Android checks

Use JDK 17, Android SDK 35 and the repository's Gradle 8.9 toolchain:

```sh
cd android
./gradlew testDebugUnitTest assembleDebug
```

If the configured wrapper mirror is unavailable, use an independently checksum-verified official Gradle 8.9 distribution without editing the repository wrapper. A network proxy requires supported Java proxy/trust configuration; never bypass TLS validation. Cloud SDK/Gradle caches must use writable locations. The focused gate/ownership regression tests are `DictationSessionGateTest`.

## Physical-device profiling protocol

1. Use the same named phone, OS/build, model artifacts, inference settings, battery level range, temperature and connectivity for baseline and candidate. Record APK commit/hash; version names alone do not distinguish these builds. Keep test data synthetic.
2. Install baseline and candidate sequentially without clearing user data. Preserve/export personalization before replacing an APK; use compatible signatures. Do not downgrade encrypted/migrated storage in later phases.
3. Sample: local-only idle with accessibility disabled; accessibility enabled but overlay inactive; editing in another app with overlay available; 10 identical dictation sessions; cancel during recording/loading/STT/formatting; hide IME; switch fields during formatting; lock/unlock; background/foreground. Separate model downloads and cloud sync from the idle comparisons.
4. From the repository root run `bash tools/profile-android-phase1.sh idle 60` (or another workload label). Select a device with `ANDROID_SERIAL` if necessary. The script reads memory/CPU/microphone/battery snapshots without resetting global battery statistics or collecting field text. Results stay in ignored `.vaani/phase1-profile/`. Raw battery snapshots contain other application identifiers; review before sharing.
5. Use 30–60 minute idle intervals and repeated controlled active workloads for energy conclusions, ideally with Perfetto/Android power profiling supported by the device. The snapshot script is supporting evidence, not an energy attribution tool. Record per-app CPU, wakeups, network, PSS/peak memory, microphone lifetime, cold/warm load and final-result latency. Repeat trials and report variance and thermal conditions.
6. On the laptop measure the equivalent idle and dictation workloads with the actual Hyprland/PipeWire/model configuration. Record CPU including helpers, memory/VRAM, wakeups and supported energy counters. Report laptop results separately from cloud measurements.

## Required manual safety scenarios

- Cancel during each pipeline stage: no text insertion, clipboard write, late UI transition or second result. Native model disposal occurs after in-flight native work safely completes.
- Start in field A, move to B while formatting: never paste into B. Switch A→B→A: the old target lease remains invalid. Blur/lock may explicitly cancel the session, in which case no clipboard write is expected.
- Change caret/selection in the original field: paste uses the editor's normal selection behavior; unsupported paste copies rather than replacing the whole document.
- Password/noneditable field, missing permission, corrupt model, recognizer error, rapid retry and duplicate result: safe failure, no recorder/recognizer retained after terminal cleanup.
- Hide or replace the IME during recording and formatting: session invalidated and capture released. Old completion cannot write through a new input connection.
- Run overlay and optional IME separately, then verify ownership preemption prevents concurrent capture when moving between them. The arbitration logic has regression coverage, but Android service/microphone interaction still requires device validation.

Do not proceed to GUI migration or Firebase removal until physical baseline and these safety paths have been verified, or the user explicitly revises that gate. Keep numerical results, passed/failed/skipped tests and unrun scenarios distinct.

The user subsequently authorized completing implementation and handing physical
validation to a testing agent. Later-phase cloud results are recorded in
`../redesign/README.md`; the missing physical measurements remain release gates.
