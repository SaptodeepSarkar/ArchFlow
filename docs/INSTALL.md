# Vaani installation and operation

Vaani is a user-local Wayland dictation daemon for Hyprland. It captures
16 kHz mono audio through PipeWire, shows a Quickshell preview, runs final
speech recognition, optionally cleans the complete transcript with a local
LLM, then follows the configured copy-only/review/automatic delivery policy.

## Requirements

The verified target environment is Arch Linux, Hyprland 0.56.2, PipeWire,
Quickshell 0.3.1, wl-clipboard 2.3.0, and an XDG user session. Required
packages are `pipewire wireplumber wl-clipboard wtype hyprland quickshell
qt6-base qt6-declarative curl cmake git rustup python`.

Real STT additionally needs the pinned whisper.cpp build and a model. CUDA is
optional; the verified GPU path is NVIDIA CUDA on compute capability 8.6.
The cleanup LLM needs Python 3, PyTorch/Transformers dependencies, the Qwen
base model, and a LoRA adapter.

## Install from GitHub

```sh
git clone https://github.com/SaptodeepSarkar/ArchFlow.git
cd ArchFlow
./install.sh
# ./install.sh --with-trained-models  # if output/ contains your local models
./tools/setup-stt.sh              # CPU STT + base whisper model
# ./tools/setup-stt.sh --cuda     # optional CUDA STT build
systemctl --user enable --now vaanid.service
```

Add one of these app-owned shortcut files to the user's Hyprland setup:

```ini
source = ~/.config/hypr/vaani.conf
```

or source `~/.config/hypr/vaani.lua` from a Lua-enabled Hyprland setup. Reload
Hyprland after changing bindings. `install.sh` never edits unrelated dotfiles.

## Locally trained cleanup models

The repository ignores `training/cleanup-llm/output/` because the artifacts
are large and may contain private training results. When that directory is
present, install the deployable artifacts with:

```sh
./tools/install-trained-models.sh
```

This installs `base-model` and the final `llm-v1` adapter under
`~/.local/share/vaani/cleanup/`. It excludes checkpoints, optimizer state,
trainer state, logs, and intermediate adapters. The daemon auto-detects these
paths. To distribute them to other people, publish the artifacts separately
with checksums and add an explicit download step; do not silently put private
or multi-gigabyte weights in the source repository.

The training tree currently contains the Qwen base and these adapter stages:
`lora-smoke-v1`, `lora-sft`, `dpo-sft`, and final `llm-v1`. `llm-v1` is the
runtime adapter. Accuracy is currently imperfect and is expected to improve
with additional training; cleanup remains conservative and falls back to the
raw transcript if model startup or validation fails.

## Exact runtime flow

1. `SUPER+H` invokes `vaani live-toggle`.
2. The daemon records the focused window identity and starts `pw-record`.
3. Quickshell opens a bottom-centered overlay: 320×94 px card, 18 px radius,
   14 px internal margin, waveform plus at most five recent preview words.
4. STT preview ticks update the overlay only. No target application receives
   preview text or clipboard changes.
5. Silence VAD ends capture, or `SUPER+J` ends it manually.
6. Final STT processes the complete utterance; preview text is never merged
   into final text.
7. In opt-in `stream` mode the local LLM cleans the final text.
8. Focus is checked again. If it changed, the result is copied and not typed.
9. Automatic mode types after one final focus check. Copy-only and review
   sessions offer final text on the clipboard; terminals remain copy-only.
10. The overlay closes and the daemon returns to `IDLE`.
11. Economy exits helpers after each operation. Balanced/Ready may reap
   supported sidecars after `server_idle_secs`.

`SUPER+J` performs steps 1–8, copies the final result, closes the overlay,
and skips automatic delivery. Terminals and multiline shell-like text remain
clipboard-only for safety.

## Input-freeze boundary

Hyprland 0.56.2 exposes no supported user-level global physical-keyboard
disable that can coexist with a virtual keyboard targeting another surface.
The pointer/touchpad curtain is implemented during `INSERTING`. Physical
keyboard events cannot be swallowed without also swallowing `wtype`'s output;
implementing that requires compositor/plugin or privileged evdev support and
is intentionally not faked by Vaani.

## Diagnostics

```sh
vaani doctor
vaani status --json
journalctl --user -u vaanid.service -f
hyprctl binds
hyprctl devices -j
```

Logs contain state, timings, backend names, and bounded errors—not audio,
transcripts, clipboard contents, or window titles.
