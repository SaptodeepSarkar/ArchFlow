# Vaani — local-first dictation for Hyprland/Wayland

[![Verify](https://github.com/SaptodeepSarkar/ArchFlow/actions/workflows/verify.yml/badge.svg?branch=feat/ecosystem-core-integration)](https://github.com/SaptodeepSarkar/ArchFlow/actions/workflows/verify.yml)

Vaani records only after activation, transcribes locally, and types the final
text into the original focused Wayland app by default. Delivery is rechecked
against that window. Vaani uses visibly progressive virtual-keyboard text
entry and never sends Enter, so terminal execution remains in the user's
hands. Review and explicit copy-only sessions remain copy-only.

No account, telemetry, cloud processing, persistent transcript history, or
always-listening microphone is required. English, Hindi (`hi`), and Bengali
(`bn`) are supported by the selected local model.

## Install

On Arch + Hyprland, install the documented dependencies, then:

```sh
git clone https://github.com/SaptodeepSarkar/ArchFlow vaani
cd vaani
./install.sh
./tools/setup-stt.sh
systemctl --user enable --now vaanid.service
```

Add the installed app-owned Hyprland include:

```ini
source = ~/.config/hypr/vaani.conf
```

Run `vaani doctor` to inspect available capabilities. CUDA is optional; use
`./tools/setup-stt.sh --cuda` only after installing a compatible toolkit.

## Session flow

1. `SUPER+H` starts a live-preview session; preview words remain in the overlay.
2. Silence or `SUPER+J` stops capture. Final STT transcribes the complete
   utterance; long recordings use bounded overlapping segments.
3. Every non-empty final transcript goes through the local, source-grounded
   formatter. If the model is unavailable or its output fails the safety
   guard, Vaani retains the recognizer output rather than risking a rewrite.
4. Automatic completions type into the original focused app after a final
   focus check. `SUPER+J` is the explicit “save to clipboard” action; terminal
   windows, review mode, and unsafe focus changes remain copy-only.

`SUPER+ALT+SPACE` toggles regular dictation, `SUPER+ALT+ESC` cancels, and
`SUPER+ALT+C` copies pending text.

## Resource policy

Economy is the default: workers exit after each operation and no inference
sidecar is retained. Balanced and Ready may retain supported sidecars for
`recognition.server_idle_secs`; they remain explicit choices. The UI is
on-demand and exits when idle.

## Packaging

Build a local Arch package with:

```sh
./tools/package-local.sh
```

The package installs binaries, sidecar scripts, the user unit, QML files, and
an app-owned Hyprland include. It does not include model weights.

## Documentation

- [Documentation index](docs/README.md)
- [Installation](docs/INSTALL.md)
- [Configuration](docs/configuration.md)
- [Compatibility](docs/compatibility.md)
- [Manual checks](docs/manual-checks.md)
- [Environment ADR](docs/ADR-001-environment.md)

Automatic typing is the default for supported Wayland apps. Set
`insertion.mode = "copy-only"` when clipboard-first behavior is preferred.
The project has not claimed universal Wayland insertion support; unsupported
environments stay copy-only.

## Android keyboard

The `android/` directory is a fresh Kotlin/Compose Android client. Vaani is
overlay-first: Gboard, Samsung Keyboard, or the user's existing keyboard stays
active normally, while a hold-to-speak Vaani bubble floats above the current
app. Android Accessibility text-box access lets the bubble paste into the
focused editable field; password or unavailable fields fall back to the
clipboard. The native `InputMethodService` remains an optional compatibility
surface, not a requirement for using Vaani.

On Linux, `vaani settings` opens the same guided setup shape: local-first or
optional account sync, microphone check, personal vocabulary, model choice,
residency/unload policy, and shortcut configuration. The setup is persisted in
`~/.config/vaani/config.toml`; the full settings window remains available later.

Open `android/` in Android Studio with JDK 17 and SDK 35 to build and install
the debug APK. The onboarding uses the original Vaani editorial artwork and
opens the real Android Accessibility and overlay permission surfaces. Firebase Auth is
wired to the existing `org.vaani.keyboard` project registration. The APK
embeds whisper.cpp and llama.cpp runtimes while keeping STT/LLM weights out of
Git; user-installed model packs run privately from `files/models/`, with safe
deterministic fallbacks when a pack is absent. The Home screen can import both
packs through Android's document picker. It also exposes the floating
Vaani button; Android's overlay settings must be approved before it can appear
above another app. The keyboard inspects the focused `EditorInfo` to detect
password/multiline fields and automatically downgrades those targets to
clipboard-only delivery. See
[`android/README.md`](android/README.md) for model paths and ADB staging.

Every push and pull request runs Rust formatting/tests, website syntax checks,
Android unit/APK verification, and Android instrumented tests on an API 35
emulator. Run the corresponding Android check locally with:

```sh
cd android
./gradlew testDebugUnitTest assembleDebug connectedDebugAndroidTest
```

The Android unit suite covers model-output guarding, field detection, and the
insert-or-copy delivery boundary. The API 35 instrumented suite covers the
product onboarding flow, keyboard handoff demo, and private model-pack import;
the debug editor harness provides a repeatable ADB surface for manually
checking Accessibility paste and clipboard fallback. The overlay listening
visualizer follows live RMS callbacks and safely no-ops when its Android
permission has not been granted.
