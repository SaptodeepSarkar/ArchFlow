# Vaani — local-first voice dictation for Hyprland/Wayland

Press `SUPER+H`, speak, stop speaking — your words are previewed in the box,
then the complete cleaned result is typed into the focused field. Press
`SUPER+J` to finish and copy without typing. No account, no telemetry,
no cloud, no history, no always-listening mic. English, Hindi (`hi`) and
Bengali (`bn`) model selection built in.

Caelestia is optional. Vaani runs as its own Quickshell application on Arch Linux
with Hyprland; it does not require anyone's personal dotfiles.

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

## Architecture — how a dictation session works

```
SUPER+H pressed
  │
  ├─ Recording starts immediately (no wait)
  ├─ STT model loads to VRAM in background (~8 s)
  ├─ LLM cleanup model loads to VRAM in background (~8 s)
  ├─ Overlay (Quickshell) spawns — shows waveform + transcript
  │
  ├─ While speaking: word-by-word live preview (never inserted)
  ├─ VAD auto-stop on silence, or SUPER+J to finish to clipboard
  │
  ├─ Cleanup via already-loaded LLM (no cold start)
  │
  ├─ If SUPER+J was pressed: save cleaned text to clipboard, box vanishes
  │   → wait 90 s → drop LLM + STT models from VRAM → idle
  │
  └─ If SUPER+J NOT pressed: stream token-by-token via wtype
      ├─ Deliver only after cleanup; input locking depends on compositor support
      ├─ Type each word via virtual keyboard (30 ms delay between tokens)
      ├─ Offer final text to clipboard
      ├─ Release keyboard, kill overlay
      └─ Wait 90 s → drop models from VRAM → idle
```

| Shortcut | Action |
|---|---|
| `SUPER+H` | Start preview dictation / discard mid-session |
| `SUPER+J` | Stop, clean, and save to clipboard without typing |
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
`IDLE → STARTING → RECORDING → TRANSCRIBING → CLEANING → READY → INSERTING → IDLE`.
Capture is a bounded `pw-record` stream (20 ms blocks, 120 s cap, nothing
written to disk). A short-lived `vaani-worker` transcribes via pinned
whisper.cpp, then exits (Economy profile).

**Startup (SUPER+H):** Recording starts immediately — no wait for models.
The STT and LLM cleanup models load to VRAM in the background while
the user is speaking. By the time they finish, both models are resident
and ready. The overlay spawns and shows word-by-word live preview.

**Finish (auto VAD silence or SUPER+J):**
- Normal (no SUPER+J): cleanup runs on the already-loaded LLM, then
  the cleaned text is streamed token-by-token through the virtual
  keyboard (`wtype`). No target-app key events are sent before cleanup.
  After streaming, the overlay vanishes, and models stay in VRAM for 90
  seconds before being freed.
- SUPER+J pressed: cleanup runs, cleaned text saves to clipboard,
  overlay vanishes immediately — no streaming. Models freed after 90 s.

Insertion is the final cleaned text streamed through the Wayland virtual
keyboard after a focus recheck; terminals receive single-line output too.
Multiline shell-like text remains clipboard-only to avoid accidental execution.
Silence inserts nothing. The Quickshell overlay is event-driven and exits when idle.

Details: `docs/architecture.md` · `docs/configuration.md` ·
`docs/compatibility.md` · `docs/performance.md` ·
`docs/troubleshooting.md` · agent guide `AGENTS.md`.

## Configure

Copy `config.example.toml` → `~/.config/vaani/config.toml`, or use
`vaani config-get` / `vaani config-set <key> <value>` (validated).
Key options: `recognition.model` (tiny/base/base.en/small/cozy),
`recognition.live_model` (fast preview model, keep whisper.cpp),
`recognition.language` (en/hi/bn), `insertion.mode`
(automatic/review/copy-only), `general.auto_stop_secs`,
`recognition.server_idle_secs` (90 s VRAM free-after-inactivity).

## Model sizes

| Component | Disk | VRAM (loaded) |
|---|---|---|
| Qwen3-0.6B base | ~1.5 GB | ~2.6 GB (bfloat16) |
| `llm-v1` LoRA adapter | ~78 MB | ~80 MB |
| Total resident | — | ~2.7 GB |
| STT (faster-whisper) | ~90 MB | ~2.6 GB |

Models stay in VRAM for `server_idle_secs` (default 90 s), then are
reaped. The cleanup LLM starts loading on SUPER+H in parallel with
microphone capture so it is ready by finish time — no cold-start wait
after Super+J.

## Models: stock whisper vs fine-tuned cozy

Audio flow: 16 kHz blocks → energy VAD + hangover → end-of-speech auto-stop
→ bounded 30 s segments with overlap → per-segment inference → prefix
reconciliation → filler-word strip (uh/um/er/mmm) → clipboard + popup.
Lists/bullets restructuring is performed by the default `cleanup.mode = "stream"` local-LLM step
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

**Streaming pipeline:** On SUPERR+H the cleanup LLM starts loading in
parallel with microphone capture (~8 s cold). By the time the user
finishes speaking, the model is resident. Cleanup runs instantly.
The cleaned text is streamed token-by-token through the virtual
keyboard (wtype, 30 ms between tokens) with the physical keyboard
frozen during streaming. After streaming, the keyboard releases,
the overlay vanishes, and the model stays in VRAM for
`recognition.server_idle_secs` (90 s default). If unused after that,
both the LLM and STT models are dropped from VRAM. Pressing
`SUPER+J` during recording skips keyboard streaming entirely and saves the
cleaned text directly to the clipboard.

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
