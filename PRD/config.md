# PRD — Config (`vaani.conf`)

Single file, parsed once by the key service at boot. All timeouts, UI counts, and model picks come from here; no hardcoded values in helpers.

| Key | Meaning | Default |
|---|---|---|
| `hotkey` | Global trigger combo | `SUPER+H` |
| `ui_words` | Trailing words shown in pill | `4` |
| `stt_model` | STT model id | `small.en` |
| `stt_fallback_model` | Weak-hardware STT | `base.en` |
| `llm_model` | Formatter model id | `qwen2.5-1.5B-q4` |
| `prefer_device` | `dgpu`, `igpu`, or `auto` | `auto` |
| `idle_timeout_s` | Offload helpers after N idle seconds | `120` |
| `names` | `spoken = typed` pairs, one per line section | — |
| `links` | `spoken = url` pairs, one per line section | — |

See `DOCS/configuration.md` for a complete sample file.
