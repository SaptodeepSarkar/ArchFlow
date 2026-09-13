# Vaani — local-first dictation for Hyprland/Wayland

Vaani records only after activation, transcribes locally, and copies the final
text to the Wayland clipboard by default. Automatic delivery is opt-in per app,
is rechecked against the original focused window, and is never used for
terminals, review sessions, or multiline shell-like text.

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
3. Raw transcription is the default. `cleanup.mode = "clean"` or `"stream"`
   explicitly enables cleanup.
4. `SUPER+J` always copies final text. Other completions follow
   copy-only/review/automatic policy after a final focus check.

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

- [Installation](docs/INSTALL.md)
- [Configuration](docs/configuration.md)
- [Compatibility](docs/compatibility.md)
- [Manual checks](docs/manual-checks.md)
- [Environment ADR](docs/ADR-001-environment.md)

The project has not claimed unmeasured laptop performance or universal Wayland
insertion support. Unsupported environments stay copy-only.

## Android keyboard

The `android/` directory contains a native Vaani `InputMethodService` for
Android phones and tablets. It can be enabled beside Gboard or Samsung
Keyboard and commits cleaned Unicode text into the focused field. The setup
screen opens Android's keyboard settings and exposes the cleanup preference.

Open `android/` in Android Studio with JDK 17 and SDK 35 to build and install
the debug APK. Android requests the platform on-device speech recognizer when
available (`EXTRA_PREFER_OFFLINE`); devices without an offline recognizer are
reported clearly. A JNI whisper.cpp engine and a bundled quantized LLM remain
future model adapters, so no model weights are shipped in this repository.
