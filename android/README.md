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

Speech uses Android's installed on-device recognizer with offline preference.
User-local STT and formatter model packs may live under the app's private
`files/models/` directory; weights are never tracked in Git. The current
formatter is a deterministic safety fallback and does not claim to be an
embedded LLM. The native model interfaces are deliberately kept separate so a
validated local runtime can be added without weakening content-safety rules.

`src/debug` contains an editor harness for emulator checks. It exposes a safe
single-line field (direct insertion policy) and a multiline field (clipboard
fallback policy) without shipping that test surface in release builds. The
optional overlay copies dictated output instead of pretending it can inspect or
inject into another app's focused field.
