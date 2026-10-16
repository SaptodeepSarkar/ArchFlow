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

## Formatter LLM endpoint

`VAANI_LLM_ENDPOINT` (environment, default `http://127.0.0.1:8081`) points at
any OpenAI-compatible chat server. The formatter sends the raw transcript
there and the reply is what gets typed. With no server answering, the built-in
rule engine formats instead, so dictation never depends on a model being up.

```sh
llama-server -m models/qwen2.5-1.5b-instruct-q4_k_m.gguf --port 8081 -ngl 99 -c 2048
```
