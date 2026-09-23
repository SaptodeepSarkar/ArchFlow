# AGENTS.md --- working guide for AI agents on Vaani (repo: ArchFlow)

Read this before changing code. The spec is
`docs/arch-voice-flow-build-prompt.md`. Environment truth lives in
`docs/ADR-001-environment.md` --- verify there, never assume.

## Project order (build slices map 1:1 to version commits)

  -----------------------------------------------------------------------------------------------------
  \#                Slice                     Paths                               Commit
  ----------------- ------------------------- ----------------------------------- ---------------------
  1                 Workspace + core:         `Cargo.toml`,                       `v0.1.0 core`
                    protocol, state machine,  `rust-toolchain.toml`,              
                    config, VAD,              `.gitignore`, `crates/vaani-core/`  
                    segment/reconcile                                             

  2                 Controller:               `crates/vaanid/`                    `v0.1.0 daemon`
                    orchestration, capture,                                       
                    focus, clipboard,                                             
                    insertion, cleanup,                                           
                    worker supervision                                            

  3                 CLI + inference worker    `crates/vaani-cli/`,                `v0.1.0 cli+worker`
                                              `crates/vaani-worker/`              

  4                 Quickshell overlay +      `ui/`                               `v0.1.0 ui`
                    settings (verified vs                                         
                    installed 0.3.1 API)                                          

  5                 Systemd unit, desktop     `packaging/`, `models/`, `tools/`,  `v0.1.0 packaging`
                    entry, PKGBUILD, Hyprland `native/worker/`,                   
                    binds, model manifest,    `config.example.toml`, `install.sh` 
                    setup/bench tools,                                            
                    example config, installer                                     

  6                 Docs, fixtures,           `docs/`, `tests/`,                  `v0.1.0 docs+tests`
                    integration tests         `crates/*/tests/`                   

  7                 Live-hardware fix:        `crates/vaani-core/src/state.rs`,   `v0.1.0 fix`
                    silence short-circuit     `tests/protocol_abuse.rs`           
                    `TRANSCRIBING → IDLE` +                                       
                    regression test                                               

  8                 Meta: README, license,    `README.md`, `LICENSE-MIT`,         `v0.1.0 meta`
                    this file                 `AGENTS.md`                         
  -----------------------------------------------------------------------------------------------------

Tag `v0.1.0` = slice 8. Future versions: bump `Cargo.toml` workspace
crates + `packaging/PKGBUILD` `pkgver` together, one commit per version,
annotated tag.

## Version history

-   **v1.2.0** (2026-09-22): user-local uninstall/reinstall flow,
    visible Vaani Desktop launcher with settings and service lifecycle
    actions, and a clean install round-trip verified on the target
    laptop.

-   **v1.0.0** (2026-09-15): restored automatic typing as the default
    delivery mode, made cleanup run on short transcripts by default,
    aligned resident and one-shot formatter thresholds, and reorganized
    the documentation index.

-   **v0.8.3** (2026-09-11): pure final. Finalize always runs
    full-utterance inference (long audio via overlapping same-model
    segments); live-tick fragments are preview-only after proving 2 s
    windows diverge into salad ("asked to ask you"). One commit:
    `v0.8.3 pure-final2`, tag `v0.8.3`.

-   **v0.8.2** (2026-09-11): message-safe transcripts. Local polish
    collapses false starts ("genuine genuinely") and duplicate phrases
    ("i can't i can't") while keeping intentional emphasis ("very very",
    "no no"); `cleanup.   vocabulary` appends names/terms to the
    recognizer prompt. Misheard content words are never guessed. One
    commit: `v0.8.2 polish`, tag `v0.8.2`.

-   **v0.8.1** (2026-09-11): streaming that actually streams. Unique
    temp dirs per job (shared paths let a finished call delete a
    sibling's wav --- every server call fell back to slow one-shot),
    offline hub flags (load \~1 s, chunks \~0.3 s), silence trim +
    no-speech filter against phantom phrases, padded-audio regression
    test. One commit: `v0.8.1 fw-stream-fix`, tag `v0.8.1`.

-   **v0.8.0** (2026-09-11): streaming fine-tuned STT. Directory models
    run through a persistent faster-whisper sidecar (loads once, \~0.3 s
    per chunk, \~90 MiB resident, reaped after `server_idle_secs`), so
    cozy shows results on the go; filler-strip shared in core; hardware
    streaming test (ignored). One commit: `v0.8.0 fw-stream`, tag
    `v0.8.0`.

-   **v0.7.2** (2026-09-11): pure final. The live-preview seed is only
    merged into the final transcript when preview and final models
    agree; with split models (base preview, cozy final) the final model
    transcribes the whole utterance so base-model wording can't corrupt
    it. One commit: `v0.7.2 pure-final`, tag `v0.7.2`.

-   **v0.7.1** (2026-09-11): backend visibility. `vaani status`
    latencies now carry the STT backend label (`fw-ct2` vs
    `whisper-cli-cuda` vs `cpu-stub`) so a wrong-model regression is
    caught from numbers. One commit: `v0.7.1 backend-tag`, tag `v0.7.1`.

-   **v0.7.0** (2026-09-11): fine-tuned speech.
    `recognition.model = "cozy"` runs the Cozy whisper-small LoRA
    (Indian English + your voice) via a faster-whisper sidecar (CT2
    int8, beam 1, CUDA; user-local copy, weights never in repo);
    `recognition.live_model` keeps preview ticks on fast whisper.cpp.
    Model resolution prefers real artifacts (a stale `cozy.bin` path
    rescues to the `cozy/` directory instead of silent cpu-stub), and
    the sidecar carries Cozy's validated Hindi prompt by default.
    Vocabulary feeds the recognizer prompt (names), filler words
    (uh/um/er/mmm) are stripped in the worker. One commit:
    `v0.7.0 cozy-stt`, tag `v0.7.0`.

-   **v0.6.5** (2026-09-11): place-tracking preview. At most five recent
    words: dim trailing context plus the newest word highlighted, so no
    ellipsis hides your place. One commit: `v0.6.5 place`, tag `v0.6.5`.

-   **v0.6.4** (2026-09-11): running preview. The overlay shows the last
    \~24 recognized words (three wrapped lines) with a quick fade on
    arrival instead of a fixed two-word slot, so speech is never dropped
    from the display between ticks. One commit: `v0.6.4 preview`, tag
    `v0.6.4`.

-   **v0.6.3** (2026-09-11): no-wedge completion. Every
    clipboard/dispatch helper runs under a 5 s deadline, and wl-copy
    offers reap instead of draining pipes (its forked server holds them
    open, which wedged sessions in INSERTING deaf to Super+H); a second
    press inside the first 1.2 s of recording is key bounce, not a
    discard. One commit: `v0.6.3 no-wedge`, tag `v0.6.3`.

-   **v0.6.2** (2026-09-11): finish-stage Super+H is a harmless
    "finishing..." instead of discarding the transcript; the "Copied to
    clipboard" flag rides on the Idle state event so auto-stop shows the
    \~2 s popup; centered live words with fade-in newcomers and
    slide-left successors. One commit: `v0.6.2 finish+overlay`, tag
    `v0.6.2`.

-   **v0.6.1** (2026-09-11): copy-first completion. `copy-only` is the
    default insertion mode (injection code kept for `automatic`); every
    finish shows a "Copied to clipboard" popup that lingers \~2 s. Live
    preview no longer blanks on pause/partial-word ticks or worker
    hiccups --- last-known words stay on screen, with tick failures
    logged. One commit: `v0.6.1 copy+preview`, tag `v0.6.1`.

-   **v0.6.0** (2026-09-11): incremental live transcription and
    dependable completion. One-second chunks with overlap replace
    cumulative re-inference; finalization processes only the unconsumed
    tail. VAD gate lowered to 0.003 so quiet microphones trip
    end-of-speech auto-stop. wtype virtual-keyboard paste replaces
    unreliable compositor synthesis; terminals use primary selection +
    Shift+Insert (single modifier) while GUI apps use clipboard + Ctrl+V
    --- completion always leaves the full transcript on the clipboard
    AND requests paste. Review-gated sessions copy to clipboard and
    close to Idle instead of parking on "Text ready", and the overlay
    auto-exits from READY. One commit: `v0.6.0 streaming+insertion`, tag
    `v0.6.0`.

-   **v0.5.2** (2026-09-11): insertion handoff hardening. Verify
    clipboard readiness, recheck focus immediately before paste
    dispatch, log non-content outcomes, and slide the overlay down after
    paste or clipboard fallback. One commit: `v0.5.2 insertion+exit`,
    tag `v0.5.2`.

-   **v0.5.1** (2026-09-11): live hardware follow-up. Quiet-microphone
    VAD tuning, CUDA whisper.cpp setup, and an overlay containing only
    the waveform and two-word transcript/status text. One commit:
    `v0.5.1 live+cuda`, tag `v0.5.1`.

-   **v0.5.0** (2026-09-11): UI and distribution redesign. Compact
    two-word live preview, optional Caelestia dynamic colors with an
    independent fallback theme, redesigned settings navigation,
    system-wide Arch packaging, portable XDG-aware local install, and
    fixes from the published bug audit. One commit:
    `v0.5.0 ui+distribution`, tag `v0.5.0`.

-   **v0.3.1** (2026-09-11): capture/insertion hardening.
    `pw-record --target` before positional output (was silently ignored
    → wrong mic), clipboard offer on every non-dispatched outcome, 800
    ms activation repeat guard, CLI skips interleaved event lines via
    `request_id` match. Tag `v0.3.1`.

-   **v0.3.0** (2026-09-11): real transcription. whisper.cpp v1.7.6
    (local CPU build) + ggml base; worker `whisper-cli` backend proven
    on jfk.wav (1.6 s, WER≈0); room loopback toggle→paste end-to-end;
    sibling/user-bin lookup, bare-name model resolve, manifest hash +
    sizes corrected. One commit: `v0.3.0 stt`, tag `v0.3.0`. Weights
    never in repo.

-   **v0.2.2** (2026-09-11): service readiness. Worker resolved as
    sibling of the daemon binary (systemd minimal PATH), user unit
    without EROFS-causing lockdown. Lua keybinds (`SUPER+H` etc.) in
    user config + runtime eval. One commit: `v0.2.2 service`, tag
    `v0.2.2`.

-   **v0.2.1** (2026-09-11): UI event stream (daemon forwards
    state/amplitude/ provisional to subscribers --- visualizer was
    starved before), QML `sendOp` wire format (buttons sent malformed
    `kind`-less messages), typing-space notice at record start,
    copy-only enforced for live commits, mic-test levels in CLI, child
    reaping. One commit: `v0.2.1 ui+feedback`, tag `v0.2.1`.

-   **v0.2.0** (2026-09-11): live dictation (`SUPER+H` →
    `vaani live-toggle`). Stable-prefix commits while recording (last 4
    words held provisional), per-commit focus recheck, terminal/review
    preview-only, remainder on finish. One commit: `v0.2.0 live`, tag
    `v0.2.0`.

-   **v0.1.0** (2026-09-10): first dependable vertical slice. Toggle
    dictation end-to-end on the laptop (capture → stub transcription →
    silence policy → copy-only insertion), event-driven overlay,
    settings, packaging, 31 tests. No model weights bundled;
    accuracy/latency numbers pending `manual-checks.md`.

## Commands

``` sh
cargo build --workspace        # debug; --release for measurements
cargo test --workspace         # must stay green (currently 51; one hardware test ignored)
qmllint ui/shell.qml ui/SettingsView.qml   # QML syntax
./install.sh                   # user-local install only (never sudo, never system upgrade)
vaani doctor                   # capability probe on the laptop
```

## Rules for agents

-   Economy profile first: no new long-lived processes, no polling
    loops, no TCP servers.
-   Audio/text never in logs, JSON, argv, or shell strings. Transcripts
    via stdin pipes/structured buffers only. But for wtype there is an
    execption, wtype can take text cleand by th LLM and directly use it
    to type the text in text felids. as wtype just uses the text once
    and never logs it it matches the requirments.
-   State machine (`vaani-core/src/state.rs`) is the single authority
    --- only `vaanid` transitions it; stale-session results die.
-   UI is event-driven (`Socket` + `SplitParser`); QML never spawns
    per-tick commands.
-   Don't invent Quickshell/Hyprland/systemd APIs --- check installed
    versions (`docs/ADR-001-environment.md`, local qmltypes, `hyprctl`,
    `man systemd.exec`).
-   Never report container numbers as laptop measurements. Missed
    targets reported honestly.
-   No `curl | sh`, no auto system upgrade, no edits to unrelated
    dotfiles in packaging.

## Long-running V5 training handoff

-   The full public Indian-English corpus is local at
    `/home/saptodeep/Projects/Cozy/stt-finetune/data/cv_indian_full/`
    (3,987 public clips; weights/audio/manifests stay out of Git).

-   For the expanded V5 manifest, use `tools/build_v5_mixed_manifest.py`
    with the deterministic 100-row holdout excluded. The V5 Whisper
    trainer supports `--streaming`; use it for the full corpus because
    eager mel-feature building exhausts host memory. A one-step
    streaming smoke test passed on 2026-09-14.

-   Do not suspend the laptop or kill `awake` at any stage. After the
    complete STT and LLM training/evaluation scope (including any active
    TTS experiment) is genuinely finished and the final benchmark brief
    is delivered, open Spotify, start playback, open the Speakers/device
    selector, and select the Echo Dot. This media action must not happen
    after an STT-only milestone and must not be claimed complete without
    verifying the selected device.

-   ``` sh
      hyprctl repl 'hl.dispatch(hl.dsp.workspace.toggle_special("music"))'
    ```

-   ``` sh
      node - <<'NODE'
      const http=require('http');http.get('http://127.0.0.1:9222/json/list',res=>{let b='';res.on('data',x=>b+=x);res.on('end',()=>{let ws=new WebSocket(JSON.parse(b)[0].webSocketDebuggerUrl);ws.onopen=()=>ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression:"document.querySelector('button[aria-label=\\\"Play\\\"]')?.click()",returnByValue:true}}));ws.onmessage=()=>ws.close()})})
      NODE
    ```

## V6 formatter handoff --- binding goal (2026-09-23)

### Mission

V6 is not a generic rewriting assistant and is not allowed a free hand
over the user's text. It is a **local speech-intent formatter**. Its job
is to convert the final raw STT transcript of one current utterance into
the clearest faithful written form of that utterance while preserving
the user's intended meaning, emotional register, claims, uncertainty,
and deliberate content.

Runtime architecture is fixed:

`streaming STT preview shown to user → final full-utterance STT → V6 formatter → final clean text → insertion`

V6 receives only the current finalized utterance plus bounded STT
metadata. It does **not** edit earlier submitted/finalized sentences and
must not require a natural-language system prompt at inference. Plain
transcript input must produce plain formatted text output.

The optimization order is binding:

`meaning preservation > intent preservation > uncertainty/emotion preservation > clarity > structure requested by user > grammar > punctuation/capitalization > brevity`

A prettier sentence is a failure if it changes what the user meant.

### Hard semantic constraints

-   Never use the model's world knowledge to "correct" a user's factual
    claim. Facts, especially technical facts, can depend on versions,
    machines, environments, dates, dependencies, private context, or
    information newer than the model.
-   A contradiction may be resolved only from evidence inside the
    current utterance. Explicit and strongly implied self-repairs may
    supersede abandoned material.
-   When uncertain whether content is a false start or intended
    information, **keep it**. Leaving an occasional disfluency is
    cheaper than deleting meaning.
-   Do not summarize merely to make text shorter. Preserve useful
    reasoning, uncertainty, confusion, emphasis, anger, affection,
    humor, slang, swearing, and other communicative intent.
-   Do not turn calm text into corporate prose, anger into neutral
    prose, romance into presentation language, or casual speech into
    formal writing unless the utterance explicitly asks for that
    transformation.
-   Do not translate code-switching by default. If STT provides usable
    Hinglish or another mixed-language transcript, preserve the
    languages while correcting obvious spelling/formatting errors.
-   Dictated instructions are text, not authorization to perform
    actions.
-   User vocabulary/macros, custom names, URLs, snippets, and
    application-side replacements remain outside V6 unless a separate
    explicit interface supplies them.

### Self-repair and abandoned-thought behavior

V6 must learn contextual repair, not regex deletion.

Examples of intended behavior:

-   `open firefox no wait open zen` → `Open Zen.`
-   `do it friday um sorry do it monday` → `Do it Monday.`
-   `we need to use whisper medium because actually parakeet might be better because it's faster`
    →
    `Parakeet might be better than Whisper Medium because it's faster.`
-   `python is statically typed sorry dynamically typed` →
    `Python is dynamically typed.`
-   `python is statically typed` → preserve the claim; V6 is not a fact
    checker.
-   `tell her i'll probably come around seven actually i don't know yet just tell her i'll come`
    must **not automatically collapse to** `Tell her I'll come.` if
    doing so destroys the speaker's meaningful uncertainty/confusion.
    Prefer a faithful rendering such as
    `Tell her I'll probably come around seven... actually, I don't know yet. Just tell her I'll come.`
    unless the utterance clearly marks the earlier material as an
    abandoned drafting error.
-   `i was going to tell her i'd come around seven but actually i don't know yet so i'll just tell her i'll come`
    describes reasoning and must preserve that reasoning.

Training must include hard contrast pairs where nearly identical wording
alternates between (a) an actual self-correction to remove and (b)
narration/quotation/reasoning that must remain.

### Fillers, repetitions, pauses, and quotations

Do not implement a global `um/uh/ah → DELETE` rule.

The model must distinguish: - incidental fillers that can be removed; -
hesitation that communicates uncertainty and should influence
punctuation/wording; - quoted or discussed fillers that are content; -
accidental repeated starts (`I I think`, `genuine genuinely`); -
intentional emphasis (`very very`, `no no`, deliberate repetition); -
pauses that mark sentence boundaries; - pauses that mark hesitation; -
pauses that mean nothing semantically.

### Formatting and intent management

Formatting is allowed only when the user deliberately requests or
clearly dictates the structure.

-   `I need eggs milk bread and coffee` does not automatically become a
    list.
-   `Make a shopping list: eggs, milk, bread and coffee` may become a
    formatted list.
-   Learn list start, continuation, nested items when explicitly
    dictated, and **list termination** when the speaker returns to
    ordinary prose.
-   Support deliberately requested numbered lists, bullets, headings,
    paragraphs, tables, quotes, Markdown-like structure, URLs, technical
    tokens, commands/code-like spans, and mathematical notation where
    the transcript provides enough evidence.
-   Never invent list items, headings, table cells, links, code, or
    structure that the speaker did not request or imply strongly enough.

### General normalization

V6 should learn ordinary written conventions without needing a huge
custom-name subsystem: `i → I`, sentence capitalization, punctuation,
contractions, and common canonical technical forms such as
`python → Python`, `hyper land → Hyprland` when evidence is strong,
`u r l → URL`, and similar high-confidence normalization. Do not guess
obscure entities. Application-level custom vocabulary remains the
authority for user-specific names and replacements.

### STT metadata contract

Linux and Android final-STT paths should expose, where the backend can
produce them:

-   token/word text;
-   word start/end timestamps;
-   segment ID;
-   pause before/after;
-   token/word confidence or backend-equivalent probability when
    genuinely available;
-   no-speech probability when genuinely available;
-   alternatives only when the backend genuinely produces meaningful
    alternatives;
-   partial/final status for the preview path.

Do not fabricate unavailable confidence values. Derive pause durations
from real timestamps. Metadata is evidence, never truth. V6 must still
work when some metadata fields are unavailable.

The streaming preview remains STT-only. V6 runs on the final full
utterance, not every live token.

### Platform and memory targets

Keep platform truth separate:

-   Linux V5/Cozy STT currently uses the Whisper-derived
    CTranslate2/faster-whisper path. Existing RAM/VRAM figures are
    estimates until measured on target hardware.
-   Android currently uses the approximately 148 MB `ggml-base.bin`
    Whisper model through its Android-compatible runtime, with an
    approximate 400 MB STT RAM budget.
-   Android formatter target: CPU-first, offline, no required GPU/NPU,
    and usable on a device with 6 GB total RAM.
-   Treat approximately 1 GB as an absolute formatter-side ceiling only
    for exploration. Prefer roughly **≤500--700 MB peak formatter
    working set**, leaving headroom for Android, Vaani, STT,
    tokenizer/runtime, audio buffers, and transient allocations.
-   Measure peak RSS/PSS and latency on real Android hardware before
    claiming a target is met. Host/container measurements are not
    Android measurements.
-   Prefer a resident or efficiently reusable formatter if measurements
    show that repeatedly loading a Q8 model per utterance costs more
    latency/energy than keeping a smaller model resident. Benchmark
    both; do not assume.

### Android STT portability task

Do not assume the Linux V5 STT cannot run on Android merely because its
current artifact is CTranslate2. Investigate a mobile-compatible export.

The current Linux V5 path is tied to faster-whisper/CTranslate2, whereas
Android already has a whisper.cpp-compatible runtime. The first
portability experiment should therefore start from the original/fused
fine-tuned Whisper checkpoint, convert/export it to a
whisper.cpp-compatible GGML/GGUF model when architecture compatibility
permits, quantize as appropriate, and benchmark it on Android against
the current base model. Do not try to feed a CTranslate2 model directory
directly to whisper.cpp.

Before replacing Android base Whisper, prove: 1. conversion is
numerically sane on a fixed audio set; 2. WER does not regress
unacceptably; 3. Indian-English/Hinglish behavior survives
export/quantization; 4. peak Android memory fits the budget; 5.
RTF/end-of-utterance latency is acceptable; 6. timestamps/metadata
needed by V6 remain available.

If direct conversion from the existing CT2 artifact is unsuitable,
recover/use the pre-CT2 Hugging Face/PyTorch fine-tuned checkpoint
rather than retraining blindly.

### V6 data program --- target 100k high-quality examples

Target an initial **100,000-example** curriculum, not an arbitrary quota
that overrides quality:

-   approximately 50k real or real-derived examples;
-   approximately 50k synthetic examples;
-   deduplicate aggressively;
-   maintain provenance, license, transformation history,
    language/accent/domain tags, and whether each label is human,
    corpus-derived, rule-derived, STT-derived, or LLM-synthetic;
-   do not call synthetic or automatically cleaned labels "ground
    truth";
-   if fewer than 50k defensible real examples are available, report the
    shortfall instead of padding the set with mislabeled synthetic data.

"Real-derived" may mean real human speech passed through the actual
target STT to obtain realistic raw hypotheses, with a trustworthy
human/reference transcript and separately constructed formatter target.
It does not mean pretending automatically generated metadata was
supplied by the source corpus.

### Dataset research requirements

Before downloading/training, create `docs/V6_DATASET_AUDIT.md`. Search
for and evaluate datasets in these categories:

1.  **Spontaneous conversational speech with disfluencies/self-repairs**
    --- prioritize corpora with audio, verbatim transcripts, word
    timings, reparandum/repair annotations, or explicit disfluency
    labels. Investigate Switchboard-derived disfluency resources and
    comparable legally usable corpora, but verify
    redistribution/training licensing before use.
2.  **Open spontaneous speech** --- investigate current Mozilla Common
    Voice spontaneous-speech releases and suitable languages/accents.
    Verify the exact release terms and restrictions before ingesting.
3.  **Indian English and Hinglish/code-switching** --- find open speech
    corpora with real speakers and permissive/research-compatible terms;
    document accent/domain balance. Reuse the project's existing
    Indian-English corpus where its license and split permit.
4.  **Punctuation/capitalization/clean written targets** --- obtain
    clean, diverse text from license-compatible sources and corrupt it
    into realistic spoken/STT form.
5.  **Intentional formatting language** --- collect or construct
    examples for "make a list", numbered steps, headings, tables,
    quotes, line breaks, punctuation commands, list termination, and
    transitions back to prose.
6.  **Technical vocabulary** --- construct licensed examples containing
    software names, acronyms, paths, package names, versions, commands,
    URLs, casing conventions, and spoken-letter sequences.
7.  **Quoted speech and metalinguistic examples** --- specifically
    include `he said "uh..."`, `the word um`, and commands mentioned
    rather than executed.
8.  **Emotion/style preservation** --- conversational data covering
    uncertainty, frustration, excitement, affection, sarcasm where
    legally and ethically usable.

For every candidate record: source URL/name, version/date, license,
commercial-use status if relevant, redistribution constraints, audio
availability, transcript style, annotation type, languages/accents,
size, and exactly how it would contribute to V6. Reject datasets whose
terms are incompatible or unclear until clarified.

### Building real training pairs

For suitable licensed speech audio:

1.  Preserve the original audio only in the non-Git training workspace.
2.  Run the **same STT backend/configuration intended for deployment**
    to generate realistic raw STT text and available metadata.
3.  Keep the source's verbatim/reference transcript separately.
4.  Produce a gold formatter target through human annotation or a
    carefully audited annotation pipeline.
5.  Align raw STT ↔ timestamps/metadata ↔ reference ↔ formatter target.
6.  Label edit phenomena: filler, repetition, false start, explicit
    repair, implicit repair, abandoned clause, retained hesitation,
    punctuation, capitalization, entity normalization, requested
    formatting, list boundary, quotation, code-switching, do-not-edit,
    ambiguity.
7.  For ambiguous cases, prefer `KEEP` or exclude the sample rather than
    forcing a destructive gold edit.

Do not train V6 to repair arbitrary STT hallucinations using world
knowledge. If the STT misrecognizes a content word and the utterance
itself gives no evidence for the correction, that is primarily an STT
problem.

### Synthetic-data program

Synthetic examples exist to fill controlled coverage gaps, not replace
real speech.

Start from diverse licensed clean text and generate multiple raw
spoken/STT variants using controlled transformations and, where useful,
a stronger teacher model. Include:

-   filler insertion at plausible boundaries;
-   restarts and repeated prefixes;
-   explicit repairs (`Friday—sorry, Monday`);
-   implicit repairs;
-   abandoned clauses;
-   hesitation that must be retained semantically;
-   near-identical negative pairs where `sorry/actually/no wait/I mean`
    is ordinary content rather than an edit command;
-   intentional repetition vs accidental repetition;
-   missing punctuation/casing;
-   spoken acronyms and technical names;
-   realistic Whisper-like substitutions/deletions only when they can be
    generated without teaching the formatter to hallucinate missing
    facts;
-   deliberate list requests, list continuation, and list termination;
-   quotes containing apparent commands;
-   Hinglish/code-switching;
-   anger, affection, uncertainty, casual slang, and swearing;
-   sentences that are already correct and must pass through with
    minimal edits.

For a subset, synthesize audio with multiple TTS voices/noise conditions
and run the actual STT to obtain realistic hypotheses/timestamps. Mark
all such rows as synthetic. Never fabricate "real" acoustic confidence
scores.

Use teacher-model generation only as a proposal stage. Apply
deterministic checks, semantic-similarity checks, edit-distance limits,
phenomenon-specific validators, deduplication, and sampled human review.
A teacher rewrite that introduces information not recoverable from the
source must be rejected.

### Training representation

The previous V6 experiment used source-grounded edit/tag prediction plus
deterministic rendering because unrestricted generation changed content.
Keep that as the control, but do **not** treat it as dogma if it cannot
express legitimate self-repair and semantic reconstruction.

Compare at least: - source-grounded token/span edit tagging +
deterministic renderer; - a constrained seq2seq/generative formatter
with strong copy bias; - a hybrid system where high-confidence
mechanical edits are deterministic and the learned model handles
semantic repair.

The model must not require a verbose runtime prompt. If special control
tokens are needed, they must be fixed protocol tokens supplied by the
runtime, not natural-language instructions.

Do not promote an architecture because it wins exact match on a tiny
challenge set. Benchmark meaning preservation, repair quality,
formatting intent, latency, memory, and robustness independently.

### Curriculum

Train/evaluate progressively:

1.  capitalization + punctuation + contractions;
2.  common technical normalization;
3.  fillers and accidental repetition;
4.  explicit self-corrections;
5.  false starts and abandoned clauses;
6.  implicit repair and limited semantic reconstruction;
7.  uncertainty/emotion preservation;
8.  requested lists/structure + list termination;
9.  quotations/metalinguistic negatives;
10. Hinglish/code-switching;
11. adversarial ambiguity and do-not-edit examples.

Each stage must retain regression tests from every earlier stage.

### Required evaluation suites

Maintain held-out tests for:

-   grammar;
-   capitalization;
-   punctuation;
-   contractions;
-   filler removal;
-   accidental repetition;
-   intentional repetition preservation;
-   explicit correction;
-   implicit self-repair;
-   false starts;
-   abandoned thoughts;
-   semantic reconstruction;
-   uncertainty/confusion preservation;
-   meaning preservation;
-   tone/emotion preservation;
-   list start;
-   list continuation;
-   list termination;
-   bullets/numbering/headings/tables when explicitly requested;
-   technical terminology and canonical casing;
-   URLs/acronyms/spoken letters;
-   Hinglish/code-switching;
-   quoted speech;
-   commands-as-content;
-   already-correct pass-through;
-   ambiguous do-not-delete cases;
-   STT errors that V6 must **not** guess;
-   adversarial near-pairs.

Meaning-changing deletion/substitution/invention is a **critical error**
and must be weighted substantially more heavily than leaving a filler or
awkward phrase.

Track at minimum: exact match where appropriate, edit precision/recall
by phenomenon, destructive-edit rate, unsupported-addition rate,
semantic-preservation score plus human audit, requested-format accuracy,
list-boundary accuracy, tone-preservation audit, peak memory, model-load
time, formatter latency, and end-to-end post-speech latency.

### Promotion gates

V6 is not "done" because training finishes.

A candidate may replace V5 only if: - it materially improves the
formatter challenge suites; - destructive meaning changes are below the
agreed critical-error threshold and no known systematic deletion class
remains; - it beats V5 on self-repair, abandoned-thought handling,
formatting intent, and clarity without regressing basic
grammar/capitalization/punctuation; - it passes adversarial
keep-vs-delete contrast pairs; - Android peak memory and latency are
measured on device and fit the practical budget; - Linux is benchmarked
separately; - results distinguish learned-model performance from
deterministic fallback performance; - all claims identify dataset split,
sample count, hardware, quantization, runtime, and model version.

If a candidate fails, diagnose the error class, add targeted
real/synthetic data, retrain from a justified checkpoint, and rerun the
unchanged held-out tests. Do not tune against the final test set.

### Autonomous-agent working rules for V6

The agent has freedom to research, create scripts, build datasets, train
candidates, quantize/export, benchmark, and refine **inside these
semantic and resource constraints**. It does not have freedom to
redefine the product objective.

Before each major experiment, write: - hypothesis; - changed variable; -
dataset/split; - expected improvement; - maximum RAM/VRAM/time budget; -
abort condition.

After each experiment, record: - actual configuration; - metrics; -
critical semantic failures; - memory/latency; - comparison with
V5/control; - decision: keep, reject, or investigate.

Prefer small informative experiments before long runs. The host
previously OOMed during weighted formatter training: keep guarded
defaults, bounded workers/batches, memory checks, and smoke tests. Never
launch an unbounded run.

Do not endlessly optimize training loss. The objective is a deployable
formatter whose edits are trustworthy.

### Existing V6 baseline facts that remain valid

-   The V5 free-form formatter remains archived as a control.
-   The frozen Linux STT control is the V5 Whisper-derived CT2 path; the
    recorded full-corpus normalized WER is 5.49244%, and the recorded
    100-clip CPU slice is 5.549% WER at CPU RTF 0.4107. These are host
    measurements, not Android claims.
-   The prior 10,000-source synthetic bootstrap is not human ground
    truth.
-   The previous mixed learned tagger's 3/18 exact result and
    learned+fallback 18/18 result must remain reported separately;
    fallback success is not learned accuracy.
-   Existing benchmark/report artifacts remain `docs/V6_BASELINE.md` and
    `docs/v6-formatter-benchmark.html`.
-   Do not commit weights, audio, generated datasets, or caches. \##
    graphify

This project has a knowledge graph at graphify-out/ with god nodes,
community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or
instructions before doing anything else.

Rules: - For codebase questions, first run `graphify query "<question>"`
when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for
relationships and `graphify explain "<concept>"` for focused concepts.
These return a scoped subgraph, usually much smaller than
GRAPH_REPORT.md or raw grep output. - Dirty graphify-out/ files are
expected after hooks or incremental updates; dirty graph files are not a
reason to skip graphify. Only skip graphify if the task is about stale
or incorrect graph output, or the user explicitly says not to use it. -
If graphify-out/wiki/index.md exists, use it for broad navigation
instead of raw source browsing. - Read graphify-out/GRAPH_REPORT.md only
for broad architecture review or when query/path/explain do not surface
enough context. - After modifying code, run `graphify update .` to keep
the graph current (AST-only, no API cost).
