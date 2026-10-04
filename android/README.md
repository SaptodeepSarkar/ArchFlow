# Vaani for Android

Fresh native Android implementation using Kotlin and Compose. The app shell uses
a white/sky/apricot palette with an original vector V mark; the keyboard and
optional overlay remain Kotlin services because Android requires them to be
native system surfaces. The primary experience keeps the user's default
keyboard active and uses the Vaani bubble as an overlay.

## Local verification

```sh
./gradlew testDebugUnitTest assembleDebug connectedDebugAndroidTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n org.vaani.keyboard/org.vaani.app.MainActivity
```

The package remains `org.vaani.keyboard`. The Compose app has Home, Models,
Words, Settings and Devices pages. Permissions and model downloads require
explicit user actions. Speech works without an optional formatter. Verified
release downloads and manual document imports preserve the previous model.

Economy loads models on demand and releases them after inference. Optional
retention is capped at 120 seconds. Cancellation rejects stale results; native
JNI inference can finish before resources are released. The overlay and optional
IME share exclusive microphone ownership. Accessibility insertion requires the
original non-password editable target; changing focus cancels that delivery.

Personalization uses Android Keystore AES-GCM with verified legacy migration.
Devices provides authenticated, expiring QR/manual-code transfer over the local
network with receiver approval. Firebase accounts and push synchronization have
been removed. Back up personalization through the supported transfer flow;
Keystore-encrypted files cannot simply be copied to a different device.

See `../docs/NATIVE_APP.md` and `../docs/TESTING_AGENT_PROMPT.md` for architecture
and the outstanding physical-device release gates.

For development, model files can be staged without putting them in the APK:

```sh
adb shell run-as org.vaani.keyboard mkdir -p files/models/stt files/models/formatter
adb push ggml-base.bin /data/local/tmp/ggml-base.bin
adb push model.gguf /data/local/tmp/model.gguf
adb shell run-as org.vaani.keyboard cp /data/local/tmp/ggml-base.bin files/models/stt/ggml-base.bin
adb shell run-as org.vaani.keyboard cp /data/local/tmp/model.gguf files/models/formatter/model.gguf
```

The packaged engines are `dev.ffmpegkit-maintained:whisper-android:1.0.0`
and `dev.ffmpegkit-maintained:llama-android:0.1.1`; both are MIT-licensed
Android bindings around whisper.cpp/llama.cpp. Their free artifacts currently
ship `arm64-v8a`, so the x86_64 emulator verifies UI, permissions, IME,
overlay, fallback behavior, and tests; native model inference must be measured
on an arm64 device or arm64 emulator image.

`src/debug` contains an editor harness for emulator checks. It exposes a safe
single-line field (direct insertion policy) and a multiline field (clipboard
fallback policy) without shipping that test surface in release builds. The
optional overlay uses `AccessibilityBridge` to paste into the current focused
editable node when Android permits it, then falls back to the clipboard for
password, multiline, unavailable, or denied targets. `TextDelivery` is the
shared insert-or-copy boundary and has unit coverage for successful insertion,
failed insertion fallback, copy-only fields, and empty transcripts.
