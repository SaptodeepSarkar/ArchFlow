# Configuration

Copy `config.example.toml` to `~/.config/vaani/config.toml` (schema_version = 1).
Live-edit via UI or CLI (`vaani config-get`, `vaani config-set <key> <value>`)
with a strict key whitelist — see `Config::set_key`.

| Key | Values | Tradeoff |
|---|---|---|
| general.residency_profile | economy (default) / balanced / ready | Unload per op saves RAM; next rec loads model again. Balanced/Ready: prefetch-only in v1 |
| general.review_before_insertion | bool | Stricter control; window match ≠ same cursor field |
| audio.device_selector | "" or stable source name | "" = PipeWire default each session; never numeric node ids |
| audio.worker_threads | 1–16 (4) | Responsiveness vs CPU |
| recognition.model | tiny/base/base.en/small/cozy | Final transcript model; cozy = local fine-tuned CT2 (faster-whisper) |
| recognition.live_model | tiny/base/base.en/small/cozy | Preview-tick model; whisper.cpp default, cozy works via resident server (~0.3 s/chunk) |
| recognition.server_idle_secs | 0–600 (90) | Resident faster-whisper TTL; 0 = one-shot per call |
| recognition.language | en/hi/bn | Explicit — auto-detect fails on short utterances |
| recognition.translate_to_en | bool | Opt-in translation; default preserves spoken language |
| recognition.device | cpu/cuda | CUDA only with user GPU build; failure falls back to CPU visibly |
| insertion.mode | automatic/review/copy-only | automatic replaces clipboard temporarily — needs setup consent |
| insertion.app_overrides | map | Terminals default copy-only (multiline can execute!) |
| cleanup.mode | raw/clean/stream | raw dependable; clean needs explicit local endpoint; stream auto-cleans the finished transcript with the local LLM |
| cleanup.model_path/cleanup.adapter_path | paths | Base Qwen3-0.6B dir plus explicit LoRA adapter dir for stream mode |
| cleanup.endpoint/timeout | URL / 2–30 s | No default server; timeout falls back to raw |
| cleanup.vocabulary | comma list (append; empty clears) | Names/terms fed to the recognizer prompt; always-on local polish (fillers, false starts, duplicate phrases) needs no endpoint |
| privacy.save_history | bool (off) | Retention + delete controls when enabled |

## UWSM / session integration

If `graphical-session.target` is unmanaged by your Hyprland launch, enable with:
`systemctl --user enable --now vaanid.service`, or under UWSM add
`systemctl --user import-environment WAYLAND_DISPLAY XDG_RUNTIME_DIR` to the
session env (only required display/session vars — never credentials or the
whole environment). Do not enable lingering for dictation.
