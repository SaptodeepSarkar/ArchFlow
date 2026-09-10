# Vaani — local-first voice dictation for Arch + Hyprland

Working name. Independent app; "Wispr Flow–style" describes the interaction only.
English first; Hindi/Bengali model selection built in (accuracy to be measured).

Focus a text field → `Super+Alt+Space` → speak → `Super+Alt+Space` →
transcribe → insert (or explicit copy). No account, telemetry, cloud,
history, or always-listening mic.

## Quick start (this laptop)

```sh
# 1. build
cargo build --release

# 2. install to ~/.local/bin + user unit + hypr include (touches only vaani paths)
./install.sh

# 3. first-run setup: choose/download model, mic test, insertion test
vaani settings        # or: python3 tools/model-setup.py --model base
vaani doctor

# 4. dictate
vaani toggle          # start; again to stop. vaani cancel aborts.
```

Hyprland: `install.sh` copies `packaging/hyprland/vaani.conf` to
`~/.config/hypr/vaani.conf` — add `source = ~/.config/hypr/vaani.conf` to
`hyprland.conf` yourself (one line, shown, never auto-edited).

## Layout

`crates/vaani-core` protocol/state/VAD · `crates/vaanid` controller ·
`crates/vaani-cli` (`vaani`) · `crates/vaani-worker` (whisper) ·
`ui/` Quickshell overlay+settings · `packaging/` service/desktop/PKGBUILD/binds ·
`models/manifest.toml` · `tools/` setup/scoring/bench · `docs/` · `tests/fixtures`.

## Uninstall

```sh
systemctl --user disable --now vaanid.service
rm -f ~/.local/bin/vaanid ~/.local/bin/vaani ~/.local/bin/vaani-worker \
  ~/.config/systemd/user/vaanid.service \
  ~/.config/hypr/vaani.conf ~/.local/share/applications/vaani.desktop
# config (~/.config/vaani) and models (~/.local/share/vaani/models) are kept
# unless you delete them explicitly.
```

Docs: `docs/ADR-001-environment.md` (verified versions) ·
`architecture.md` · `configuration.md` · `compatibility.md` ·
`performance.md` · `troubleshooting.md` · `manual-checks.md` (remaining proof).
