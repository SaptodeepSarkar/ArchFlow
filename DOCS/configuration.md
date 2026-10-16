# Configuration (`vaani.conf`)

Lives at `~/.config/vaani/vaani.conf`. Parsed once at boot. Sample:

```conf
hotkey = SUPER+H
ui_words = 4
stt_model = small.en
stt_fallback_model = base.en
llm_model = qwen2.5-1.5B-q4
prefer_device = auto
idle_timeout_s = 120

[names]
saptodeep = Saptodeep Sarkar

[links]
github = https://github.com/SaptodeepSarkar
```

Rules: unknown keys are ignored with a warning, never a crash. Missing file means all defaults. `[names]` and `[links]` match whole spoken phrases, longest match wins.
