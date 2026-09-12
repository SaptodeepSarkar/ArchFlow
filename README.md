# Vaani — local-first voice dictation for Hyprland/Wayland

Press `SUPER+H`, speak, stop speaking — your words are typed into the
focused field. Press `SUPER+H` mid-way to discard. No account, no telemetry,
no cloud, no history, no always-listening mic. English, Hindi (`hi`) and
Bengali (`bn`) model selection built in.

Caelestia is optional. Vaani runs as its own Quickshell application on Arch Linux
with Hyprland; it does not require anyone’s personal dotfiles.

Independent app; "Wispr Flow–style" describes the interaction only.

## Install (any Arch + Hyprland machine)

Prerequisites (all official repos): `pipewire wireplumber wl-clipboard wtype
hyprland quickshell qt6-base qt6-declarative curl cmake git rustup python`

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
vaani settings   # recognition settings, mic test and diagnostics
```

NVIDIA CUDA is optional. With the CUDA toolkit installed, run
`./tools/setup-stt.sh --cuda`, select CUDA in settings, and restart the user
service. Vaani keeps a separate `whisper-cli-cuda` binary and loads it only
during transcription.

Press `SUPER+H` in any text field and speak. Stop speaking → the overlay
shows *Transcribing* → *Copied to clipboard* (lingers ~2 s so it can be
read), and the transcript is on the clipboard for pasting. Nothing is typed
into apps by default; set `insertion.mode = "automatic"` to paste via wtype
instead. `SUPER+H` mid-recording discards the utterance (not in the first
second — that's key bounce while the overlay appears — and never once
transcription has started).

| Shortcut | Action |
|---|---|
| `SUPER+H` | Start live dictation / discard mid-session |
| `SUPER+ALT+SPACE` | Toggle (transcribe on second press) |
| `SUPER+ALT+ESC` | Discard active operation |
| `SUPER+ALT+S` | Settings · `SUPER+ALT+C` copy pending text |

## System-wide Arch package

Build a package containing the current checkout as a regular user:

```sh
./tools/package-local.sh
```

The script prints its temporary build directory. Install the resulting
`vaani-*.pkg.tar.zst` using your package manager. Binaries go to `/usr/bin`,
the user unit to `/usr/lib/systemd/user`, and UI assets to
`/usr/share/quickshell/vaani`. No Caelestia dependency is included. Enable
`vaanid.service` separately for each user and configure their shortcuts.
Remove an older user-local Vaani install first if you want to avoid PATH,
user-unit and UI overrides shadowing the system package.

The GitHub archive recipe is `packaging/PKGBUILD`; release maintainers must
pin its source checksum before distributing it. Changes in this checkout
are not automatically published to GitHub. This is an Arch Linux package,
not a promise of compatibility with every Linux desktop.

## UI and dynamic colors

The compact overlay contains only the microphone visualizer and text. It shows
at most five recent words: dim trailing context plus the newest word
highlighted, so you always see your place. Updates arrive every recognition
chunk plus inference time — roughly every two seconds — not predictions of
words you have not spoken. Any shown word can still be corrected by
recognition; display position does not mean the word was inserted.
Chunks overlap by one second and are reconciled into a cumulative transcript.
The preview holds the last-known words across pauses and worker hiccups
instead of blanking. Finalization transcribes only the unconsumed tail instead
of the complete long recording again (long audio is additionally split into
bounded 30-second segments, never full-buffer re-inference per frame).
A successful completion copies the full transcript to the clipboard and shows
a confirmation popup.
After the confirmation, the overlay slides below the screen
edge and exits. The result stays available through
`vaani recover` until its configured expiry.

Overlay and settings follow `$XDG_STATE_HOME/caelestia/scheme.json` (default
`~/.local/state/caelestia/scheme.json`). Updates use file notifications.
Missing or invalid schemes use Vaani's built-in palette. No Caelestia imports,
processes or installation are required. `VAANI_THEME_FILE` can select another
file with the same `colours` schema; set it in the daemon environment.

See [the bug audit](docs/bug-audit-2026-09-11.md) for fixes, remaining bugs and
validation limits.

## How it works (60 seconds)

`vaanid` (user service) owns a state machine
`IDLE → STARTING → RECORDING → TRANSCRIBING → READY → INSERTING → IDLE`.
Capture is a bounded `pw-record` stream (20 ms blocks, 120 s cap, nothing
written to disk). A short-lived `vaani-worker` transcribes via pinned
whisper.cpp, then exits (Economy profile). Insertion = clipboard offer, plus
an opt-in paste dispatch (`insertion.mode = "automatic"`: wtype virtual
keyboard, or Hyprland shortcut fallback) with a focus recheck; terminals
paste from the primary selection via Shift+Insert. Silence inserts nothing.
The Quickshell overlay is event-driven and exits when idle.

Details: `docs/architecture.md` · `docs/configuration.md` ·
`docs/compatibility.md` · `docs/performance.md` ·
`docs/troubleshooting.md` · agent guide `AGENTS.md`.

## Configure

Copy `config.example.toml` → `~/.config/vaani/config.toml`, or use
`vaani config-get` / `vaani config-set <key> <value>` (validated).
Key options: `recognition.model` (tiny/base/base.en/small/cozy),
`recognition.live_model` (fast preview model, keep whisper.cpp),
`recognition.language` (en/hi/bn), `insertion.mode`
(automatic/review/copy-only), `general.auto_stop_secs`.

## Models: stock whisper vs fine-tuned cozy

Audio flow: 16 kHz blocks → energy VAD + hangover → end-of-speech auto-stop
→ bounded 30 s segments with overlap → per-segment inference → prefix
reconciliation → filler-word strip (uh/um/er/mmm) → clipboard + popup.
Lists/bullets restructuring is the opt-in `cleanup.mode = "stream"` local-LLM step
(frozen Qwen3-0.6B plus the source-grounded `llm-v1` LoRA adapter); names and domain terms ride `cleanup.vocabulary` into the
recognizer's initial prompt (`--prompt` / `initial_prompt`), which is how
Whisper learns your nouns without retraining.

`recognition.model = "cozy"` switches completion to your fine-tuned
Whisper-small (LoRA on your voice + Indian English, exported CTranslate2
int8 from Cozy's `stt-finetune`, copied user-local to
`~/.local/share/vaani/models/cozy/` — weights never enter this repo). It runs
through faster-whisper on CUDA with Cozy's validated settings (beam 1,
int8_float16, Hindi-word prompt); the live preview keeps using tiny/base so
it stays at ~2 s updates. Stock ggml models still download via
`tools/model-setup.py`.

Streaming: directory models run through a persistent sidecar that loads once
(~1 s) and then answers chunks in ~0.3 s, so the fine-tuned model can show
results on the go. It holds ~90 MiB VRAM while resident and is reaped after
`recognition.server_idle_secs` (90 s default, 0 = one-shot per call) — idle
Vaani still holds zero VRAM.

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
