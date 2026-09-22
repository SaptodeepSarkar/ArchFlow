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
configuration. Account controls live behind the Home menu: email/password and
Google identity are explicit opt-in choices shown immediately after the three
opening splash screens. Choosing either account path—or **Continue without an
account**—starts Vaani's verified model-release job on the available network.
The job
uses HTTPS, SHA-256 verification, a private temporary file, and an atomic move
before a model can run. There is no manual model-picker or replacement action
in the product.

The release APK embeds native whisper.cpp and llama.cpp runtimes
(`arm64-v8a`). It cannot be used until both verified, Android-qualified model
packages have arrived in the private model directory. At the end of onboarding,
the model-preparation screen remains locked until that happens, then Android
posts a “Vaani is ready” notification. The IME records 16-kHz PCM into a
private temporary WAV, transcribes locally with Whisper, and runs the
conservative Llama editor before insertion. Model output is accepted only when
it preserves the source words in order.

The Firestore surface is deliberately limited to signed-in users' vocabulary,
snippets, and replacements at `/users/{uid}/personalization/{recordId}`. The
client cannot write raw dictation, recordings, clipboard text, tokens, or a
free-form profile document; matching rules deny them. The ADB commands below
remain useful for development and repeatable test setup.

After the three opening splash screens, Vaani offers sign-in or local-only use,
then teaches its value, hold/speak/release interaction, in-field behavior, and
language choice before asking for permissions. It then explains **text-box
access** and opens Android's Accessibility settings. The optional **Enable
Vaani control** action opens the overlay permission page. After the models
verify, the Vaani control appears only while an editable, non-password field is
focused; it disappears when focus leaves the field. Press and hold to dictate,
then release to finish, while the default keyboard remains active. Google login
requires the Firebase console's Google provider,
an Android SHA-1 fingerprint, and refreshed `google-services.json`; email
login requires the Email/Password provider. Firestore must be provisioned in
the chosen region and have the checked-in rules deployed before live sync is
available.
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
