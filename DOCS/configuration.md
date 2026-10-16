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
end_of_speech_ms = 2000

[names]
saptodeep = Saptodeep Sarkar

[links]
github = https://github.com/SaptodeepSarkar
```

Rules: unknown keys are ignored with a warning, never a crash. Missing file means all defaults. `[names]` and `[links]` match whole spoken phrases, longest match wins.

Keys must sit **above** the first `[section]` header. Anything inside an
unrecognised section is ignored (with a warning in
`journalctl --user -u vaani-key.service`), which is the usual reason an edited
setting does nothing.

## End of speech

`end_of_speech_ms` (default `2000`) is how long the decoder must produce
nothing before the run ends and the text is typed. Raise it if Vaani cuts you
off mid-thought; lower it if the text appears too late after you stop talking.
The decoder's own output is the speech signal (the mic sits behind a
noise-suppression chain with a hot floor), so this is a hangover on *new
words*, not a level threshold.

## Formatter LLM endpoint

`VAANI_LLM_ENDPOINT` (environment, default `http://127.0.0.1:8081`) points at
any OpenAI-compatible chat server. The formatter sends the raw transcript
there and the reply is what gets typed. With no server answering, the built-in
rule engine formats instead, so dictation never depends on a model being up.

```sh
llama-server -m models/qwen2.5-1.5b-instruct-q4_k_m.gguf --port 8081 -ngl 99 -c 2048
```
