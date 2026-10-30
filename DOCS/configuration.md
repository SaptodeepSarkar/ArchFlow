# Configuration (`vaani.conf`)

Lives at `~/.config/vaani/vaani.conf`. Parsed once at boot. Sample:

```conf
ui_words = 4
stt_model = small.en
stt_fallback_model = base.en
idle_timeout_s = 120
end_of_speech_ms = 2000

[names]
saptodeep = Saptodeep Sarkar

[links]
github = https://github.com/SaptodeepSarkar
```

Rules: unknown keys are ignored with a warning, never a crash. Missing file means all defaults. `[names]` and `[links]` match whole spoken phrases, longest match wins.

`stt_model` is either a bare model name (`small.en`, `base.en`) or an absolute path to a Vosk model directory. A path that does not exist is an error, never a silent fallback to the default model: the config named it, so it is used as-is or the run fails loudly. The same rule applies to `VAANI_STT_MODEL`.

Keys must sit **above** the first `[section]` header. Anything inside an
unrecognised section is ignored (with a warning in
`journalctl --user -u vaani-key.service`), which is the usual reason an edited
setting does nothing.

## End of speech

`end_of_speech_ms` (default `2000`) is how long the mic must stay quiet before
the run ends and the text is typed. Raise it if Vaani cuts you off mid-thought;
lower it if the text appears too late after you stop talking. With a Whisper
`stt_model` the backend's Silero VAD (`V` lines) is the speech signal, so the
hangover starts the instant you actually stop; the fallback signal is the
decoder's own output, which trails the mic by a second or more.

## Environment file

The daemon also reads the installer's env file once at startup: `VAANI_ENV_FILE`,
default `${PREFIX:-$HOME/.local}/vaani-stt.env`. Only `export VAANI_*=` lines are
taken, with no shell expansion, and a variable already set in the environment
wins — the systemd unit and the gates keep control. An empty `VAANI_ENV_FILE`
disables the read; a missing file is normal. That is why a bare `cargo run`
behaves like the installed unit instead of owning no model servers.

## Formatter LLM endpoint

`VAANI_LLM_ENDPOINT` (environment, default `http://127.0.0.1:8082`) points at
any OpenAI-compatible chat server; the default is the tuned formatter that
`packaging/serve-formatter.sh` serves. The formatter sends the raw transcript
there and the reply is what gets typed. With no server answering, the built-in
rule engine formats instead, so dictation never depends on a model being up.

```sh
llama-server -m models/qwen2.5-1.5b-instruct-q4_k_m.gguf --port 8082 -ngl 99 -c 2048
```

To run the daemon from a checkout, `cargo run --bin vaani-key-service` now picks
up the same env file it does under the unit (see "Environment file").

## STT interpreter and the second pass

`VAANI_STT_PYTHON` selects the interpreter that runs the STT backend. When it is set it is final: an interpreter that cannot `import vosk` makes STT fail loudly instead of quietly using another one. Unset, the daemon tries the Kyuma venv and then `python3`.

`stt_model` may name either a Vosk model directory or a CTranslate2 Whisper one, and the backend picks the engine from the directory: `model.bin` present means faster-whisper (CUDA fp16, CPU int8 when CUDA cannot decode), anything else means Vosk. Whisper shows live words by re-decoding the last few seconds of speech as it arrives, and its final decode is what gets typed; trailing silence is cut before decoding, because Whisper invents words for silence. The interpreter must have `faster_whisper` importable for a CT2 directory, and `vosk` for a Vosk one.

The optional re-decode pass is bounded on the client side: `VAANI_STT_REFINE_DEADLINE` (seconds, default `20`) is well under the backend's own 120 s HTTP guard. Past it, or when the pass fails, the daemon keeps the streaming words and types those, so a slow or dead re-decode server costs accuracy, never the utterance.

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
never killed by the daemon. `install.sh` sets `VAANI_LLM_SERVER` for you when the
llama.cpp binary, the base GGUF and the LoRA adapter are all on disk (the paths
`packaging/serve-formatter.sh` already defaults to).

The port a server is told to bind comes from the endpoint Vaani will actually
call (`VAANI_STT_REFINE_ENDPOINT`, `VAANI_LLM_ENDPOINT`), so what is owned is what
is used. A cold server is waited for at the point of use, with a bounded budget;
past it the existing fallbacks answer instead (the streaming words, the rule
engine), so a slow or broken server costs accuracy, never the utterance.
