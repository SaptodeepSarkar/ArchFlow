# Vaani — local-first voice dictation for Hyprland/Wayland

Press `SUPER+H`, speak, stop speaking — your words are typed into the
focused field. Press `SUPER+H` mid-way to discard. No account, no telemetry,
no cloud, no history, no always-listening mic. English, Hindi (`hi`) and
Bengali (`bn`) model selection built in.

Independent app; "Wispr Flow–style" describes the interaction only.

## Install (any Arch + Hyprland machine)

Prerequisites (all official repos): `pipewire wireplumber wl-clipboard
hyprland quickshell qt6-base qt6-declarative curl cmake git rustup`

```sh
git clone https://github.com/SaptodeepSarkar/ArchFlow vaani && cd vaani

# 1. binaries (debug) — add --release for daily use
cargo build --release

# 2. user-local install: ~/.local/bin, user unit, example files.
#    Touches ONLY vaani-owned paths. No sudo, no system upgrade.
./install.sh

# 3. local speech recognition (one-shot, ~5 min, ~350 MB in ~/.local)
./tools/setup-stt.sh

# 4. start the per-user service
systemctl --user enable --now vaanid.service

# 5. shortcuts — pick the section matching your Hyprland setup:
#    Lua-driven (e.g. caelestia dots): append packaging/hyprland/vaani.lua
#    to your keybinds file, then reload the compositor config.
#    Classic hyprland.conf: add `source = ~/.config/hypr/vaani.conf`.
vaani doctor     # capability probe — all lines should be true except cuda
vaani settings   # model, mic test, insertion test
```

Press `SUPER+H` in any text field and speak. Stop speaking → the overlay
shows *Transcribing* → text is typed in. Nothing focused (or a terminal)?
It lands on the clipboard instead, with the reason shown. `SUPER+H` while
recording/transcribing discards the utterance.

| Shortcut | Action |
|---|---|
| `SUPER+H` | Start live dictation / discard mid-session |
| `SUPER+ALT+SPACE` | Toggle (transcribe on second press) |
| `SUPER+ALT+ESC` | Discard active operation |
| `SUPER+ALT+S` | Settings · `SUPER+ALT+C` copy pending text |

## How it works (60 seconds)

`vaanid` (user service) owns a state machine
`IDLE → STARTING → RECORDING → TRANSCRIBING → READY → INSERTING → IDLE`.
Capture is a bounded `pw-record` stream (20 ms blocks, 120 s cap, nothing
written to disk). A short-lived `vaani-worker` transcribes via pinned
whisper.cpp, then exits (Economy profile). Insertion = clipboard offer +
compositor paste dispatch with a focus recheck; terminals are copy-only by
policy (pasting shell-like text could execute it). Silence inserts nothing.
The Quickshell overlay is event-driven and exits when idle.

Details: `docs/architecture.md` · `docs/configuration.md` ·
`docs/compatibility.md` · `docs/performance.md` ·
`docs/troubleshooting.md` · agent guide `AGENTS.md`.

## Configure

Copy `config.example.toml` → `~/.config/vaani/config.toml`, or use
`vaani config-get` / `vaani config-set <key> <value>` (validated).
Key options: `recognition.model` (tiny/base/base.en/small),
`recognition.language` (en/hi/bn), `insertion.mode`
(automatic/review/copy-only), `general.auto_stop_secs`.

## Uninstall

```sh
systemctl --user disable --now vaanid.service
rm -f ~/.local/bin/vaanid ~/.local/bin/vaani ~/.local/bin/vaani-worker \
  ~/.local/bin/whisper-cli \
  ~/.config/systemd/user/vaanid.service \
  ~/.config/hypr/vaani.conf ~/.local/share/applications/vaani.desktop
rm -rf ~/.config/quickshell/vaani
# Kept by design unless you delete them: ~/.config/vaani,
# ~/.local/share/vaani/models
```
