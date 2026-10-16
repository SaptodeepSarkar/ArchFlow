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

## Model servers: who loads and unloads them

The two fine-tuned models are HTTP servers. Point the daemon at their launchers
and it owns them: the speech server is spawned when a run starts (the mic is
already live, so it loads while you speak), the formatter when the run reaches
formatting, and each is killed once `idle_timeout_s` (`idle_timeout_secs` in an
older installer's file) has passed with no run. No model memory is held between
dictations, and the two never load at the same instant to race for it.

| variable | what it points at |
|---|---|
| `VAANI_STT_REFINE_SERVER` | `packaging/serve-refine-stt.sh`; its presence is what makes the daemon own the re-decode server |
| `VAANI_LLM_SERVER` | `packaging/serve-formatter.sh`; its presence is what makes the daemon own the formatter |

Unset either one and that server is not owned: whatever you started by hand keeps
serving, exactly as before. A port that already answers is never spawned over and
never killed by the daemon.

The port a server is told to bind comes from the endpoint Vaani will actually
call (`VAANI_STT_REFINE_ENDPOINT`, `VAANI_LLM_ENDPOINT`), so what is owned is what
is used. A cold server is waited for at the point of use, with a bounded budget;
past it the existing fallbacks answer instead (the streaming words, the rule
engine), so a slow or broken server costs accuracy, never the utterance.
