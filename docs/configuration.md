# Configuration

Copy `config.example.toml` to `~/.config/vaani/config.toml` (schema_version = 1).
Live-edit via UI or CLI (`vaani config-get`, `vaani config-set <key> <value>`)
with a strict key whitelist — see `Config::set_key`.

New configs default to automatic typing. Existing V5-era configs that explicitly
saved `copy-only` keep that choice; restore the typing behavior with
`vaani config-set insertion.mode automatic`.

| Key | Values | Tradeoff |
|---|---|---|
| general.residency_profile | economy (default) / balanced / ready | Economy exits sidecars after an operation; Balanced keeps supported sidecars warm for at least 60 seconds; Ready keeps them warm for up to 10 minutes. |
| general.review_before_insertion | bool | Stricter control; window match ≠ same cursor field |
| audio.device_selector | "" or stable source name | "" = PipeWire default each session; never numeric node ids |
| audio.worker_threads | 1–16 (4) | Responsiveness vs CPU |
| recognition.model | tiny/base/base.en/small/cozy/v5 | Final transcript model; v5 = local V5 Whisper-derived CT2 candidate |
| recognition.live_model | tiny/base/base.en/small/cozy/v5 | Preview-tick model; v5/cozy work through the resident faster-whisper server |
| recognition.server_idle_secs | 0–600 (0) | Sidecar TTL for Balanced/Ready; Economy always uses 0. |
| recognition.language | en/hi/bn | Explicit — auto-detect fails on short utterances |
| recognition.translate_to_en | bool | Opt-in translation; default preserves spoken language |
| recognition.device | cpu/cuda | CUDA only with user GPU build; failure falls back to CPU visibly |
| insertion.mode | automatic/review/copy-only | automatic types after a final focus check; copy-only keeps text on the clipboard |
| insertion.app_overrides | UI or `insertion.app_override` as `app-id=mode` (`none` removes) | Terminals default copy-only (multiline can execute!); overrides are substring matches |
| cleanup.model_path/cleanup.adapter_path | paths | Base Qwen3-0.6B directory plus explicit LoRA adapter directory for the always-on local formatter |
| cleanup.python_path | path | Optional one-shot formatter fallback; the daemon otherwise resolves its installed helper |
| cleanup.vocabulary | comma list (append; empty clears) | Names/terms fed to the recognizer prompt; always-on local polish (fillers, false starts, duplicate phrases) needs no endpoint |

The current trained Indian-English STT export is named `cozy_stt_public_indian_v2`.
Curated selectable vocabulary packs are in `models/vocabulary/`. Print a
config-ready selection with `python3 tools/vocabulary-pack.py engineering
acronyms --max 80` and copy the result into `[cleanup]`. This is decoder
context, not training data, so difficult terms can be selected per task
without enlarging the model. It is a recognition hint, not a guarantee; the
audio still has to support the term.
| privacy.save_history | bool (off) | Retention + delete controls when enabled |

## UWSM / session integration

If `graphical-session.target` is unmanaged by your Hyprland launch, enable with:
`systemctl --user enable --now vaanid.service`, or under UWSM add
`systemctl --user import-environment WAYLAND_DISPLAY XDG_RUNTIME_DIR` to the
session env (only required display/session vars — never credentials or the
whole environment). Do not enable lingering for dictation.
