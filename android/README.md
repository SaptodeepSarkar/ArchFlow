# Vaani Keyboard for Android

This is the Android client/container for ArchFlow. It is an Android `InputMethodService`, so it can be selected beside Gboard or Samsung Keyboard and can commit Unicode text directly into the focused editor.

## Build and install

Open `android/` in Android Studio (JDK 17, Android SDK 35), or run:

```sh
./gradlew :app:assembleDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Launch **Vaani Keyboard**, enable it in system keyboard settings, then select it from any text field. Grant microphone permission when requested.

## Local-first model boundary

`VoicePipeline.kt` requests Android's on-device speech recognizer (`EXTRA_PREFER_OFFLINE=true`). Device manufacturers may not provide an offline model; the app reports that condition rather than silently using a network service. The `SttEngine` interface is the seam for a future NDK whisper.cpp/ggml build using the same bounded PCM contract as `vaani-worker`.

Cleanup is intentionally conservative and local: whitespace and sentence capitalization only, with raw STT as the fallback. It does not guess content or send transcripts to a cloud endpoint. A future bundled quantized editor can implement a `CleanupEngine` beside `ConservativeCleanup`; model weights are not checked into this repository.

## V5 handoff status

The V5 desktop STT candidate is a user-local CTranslate2 directory, not an
Android asset:

`~/.local/share/vaani/models/v5-stt-whisper-v5-supervised-200-ct2`

It is approximately 245 MB (`int8_float16`), measured at 5.492% corpus WER
and about 516 MiB VRAM during desktop CUDA inference. It has not been bundled
into this APK and has no Android latency, RAM, battery, or thermal result yet.
The Android implementation must add a native offline `PcmSttEngine` (for
example through an ONNX/ggml-compatible export) and benchmark it on a physical
device before this artifact can replace `OnDeviceSttEngine`.

The Android IME cannot connect to the Linux daemon's Unix socket across OS boundaries. The two clients therefore share the privacy and model contract, not a live desktop socket. No transcript is placed in logs, intents, or command arguments.

## UI/UX implementation status

The app has a Material Compose four-step onboarding flow, a readiness-led
Home/Settings shell, explicit dictation states, and insertion-failure recovery.
The future coexisting overlay remains intentionally unimplemented until its
Android integration and privacy contract are approved.
