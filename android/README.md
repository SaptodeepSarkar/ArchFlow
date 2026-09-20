# Vaani for Android

Fresh native Android implementation using Kotlin and Compose. The app shell uses
the cobalt/coral/cloud system in `docs/design-tokens.json`; the keyboard and
optional overlay remain Kotlin services because Android requires them to be
native system surfaces.

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
optional overlay copies dictated output instead of pretending it can inspect or
inject into another app's focused field.
