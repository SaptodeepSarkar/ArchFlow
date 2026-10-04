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

Vaani ships two independently buildable surfaces. See
[Delivery surfaces](docs/RELEASES.md) for the Android APK build/publish path
and the native Linux installation path.

On Arch + Hyprland install Rust, GTK4, libadwaita, gtk4-layer-shell, OpenSSL,
a Secret Service keyring and the existing audio/clipboard dependencies, then:

```sh
git clone https://github.com/SaptodeepSarkar/ArchFlow vaani
cd vaani
./install.sh
./tools/setup-stt.sh
systemctl --user enable --now vaanid.service
```

The launcher entry is installed as **Vaani Desktop**. Open it to reach settings;
its launcher actions can start/stop the user service or enable it at login.
To remove the user-local installation while keeping personal config and models:

```sh
./uninstall.sh
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

Linux now uses a Rust GTK4/libadwaita application. Its Home, Settings,
Personalize, Models and Devices pages communicate with the Rust backend.
Settings validate values and preserve existing TOML comments and unknown fields.
See [native installation and architecture](docs/NATIVE_APP.md).

Android keeps Kotlin/Compose, the floating accessibility bubble and optional
IME. Models are installed explicitly from the Models page; startup does not
load or download weights. Economy unloads model handles after use; Balanced
retains them for at most 120 seconds. Personalization is encrypted with Android
Keystore or Linux Secret Service. Missing keys fail closed and preserve files.

Devices pairs through a two-minute, single-use QR invitation and certificate-
pinned TLS 1.3 on the local network. Transfers remain staged until the receiver
approves the merge. Vocabulary, snippets/links and replacements retain stable
IDs and deletion records. Portable language/retention preferences are optional
approved snapshots. Accounts, Firebase and push sync have been removed.

Build Android using JDK 17 and SDK 35. Real microphone, editor, battery and
cross-device checks remain required before release; cloud tests do not establish
physical-device performance. Give a tester [this prompt](docs/TESTING_AGENT_PROMPT.md).

Run the Android checks locally with:

```sh
cd android
./gradlew testDebugUnitTest assembleDebug connectedDebugAndroidTest
```

## Build and model workspaces

Use the root `Makefile` to keep desktop and Android work separate:

```sh
make desktop-debug    # Rust daemon/CLI/native GTK4 desktop surface
make android-debug    # Kotlin/Compose APK only
make test-desktop
make test-android
```

All future STT and formatter/LLM datasets use the ignored, shared contract in
[`data/shared/`](data/shared/README.md). Training wrappers and their stable
commands live in [`pipelines/`](pipelines/README.md); the older specialized
scripts remain in `tools/` as implementation details and experiment history.

The Android unit suite covers model-output guarding, field detection, and the
insert-or-copy delivery boundary. The API 35 instrumented suite covers the
product onboarding flow, keyboard handoff demo, and private model-pack import;
the debug editor harness provides a repeatable ADB surface for manually
checking Accessibility paste and clipboard fallback. The overlay listening
visualizer follows live RMS callbacks and safely no-ops when its Android
permission has not been granted.
