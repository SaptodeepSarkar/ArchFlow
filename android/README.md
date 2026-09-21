# Vaani for Android

Fresh native Android implementation using Kotlin and Compose. The app shell uses
the cobalt/coral/cloud system in `docs/design-tokens.json`; the keyboard and
optional overlay remain Kotlin services because Android requires them to be
native system surfaces. The primary experience keeps the user's default
keyboard active and uses the Vaani bubble as an overlay.

## Local verification

```sh
./gradlew testDebugUnitTest assembleDebug connectedDebugAndroidTest
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n org.vaani.keyboard/org.vaani.app.MainActivity
```

The rebuilt app keeps the registered Firebase Android identity
`org.vaani.keyboard` and uses the checked-in `google-services.json` client
configuration. The setup flow creates a real anonymous Firebase Auth session;
Google OAuth is not advertised until an Android OAuth client is added in the
Firebase console.

The release APK embeds native whisper.cpp and llama.cpp runtimes
(`arm64-v8a`); model weights are still user-installed and never tracked in
Git. Put a Whisper GGML model at `files/models/stt/ggml-base.bin` and a GGUF
cleanup model at `files/models/formatter/model.gguf`. The IME records 16-kHz
PCM into a private temporary WAV, transcribes locally with Whisper, and runs
the conservative Llama editor before insertion. If either pack is absent or
fails to load, Vaani falls back to Android's offline recognizer and the
deterministic formatter. Model output is accepted only when it preserves the
source words in order.

The Home screen also provides **Install Whisper model** and **Install Llama
cleanup model** actions. They use Android's document picker and copy the
selected file into Vaani's private `files/models/` directory; no broad storage
permission is requested. The ADB commands below remain useful for development
and repeatable test setup.

The onboarding first explains **text-box access** and opens Android's
Accessibility settings. After approval, the **Enable floating button** action
opens the overlay permission page. The always-on-top Vaani bubble can then be
held to dictate from another app while the default keyboard remains active.
The listening bars are driven by microphone RMS callbacks from the active STT
session. When the focused node is editable and not a password field, Vaani
pastes into that node; otherwise it copies the result for a normal paste. If
the overlay service is started before its grant exists, it exits safely without
crashing. The IME remains an optional compatibility surface and is never
required by onboarding.

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
