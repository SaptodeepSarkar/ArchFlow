# Arch Voice Flow — implementation prompt

Copy everything below into your coding agent. This is a proposed engineering specification, not a claim that the software or its performance has already been tested. “Wispr Flow–style” describes the interaction; this is an independent application. Working name: **Vaani** (a placeholder, not a verified unique brand).

## 1. Your assignment

Act as a senior Linux desktop and speech systems engineer. Build a working, local-first voice dictation application for Arch Linux with Hyprland on Wayland. Prioritize reliable dictation, very low inactive memory use, and a polished compact UI. Deliver real implementation, packaging, documentation, and evidence from tests. Do not stop at mockups or architecture diagrams.

Read the repository instructions first. Inspect the actual machine and installed dependency versions before writing version-sensitive integration code. If you are operating in a remote container, distinguish that environment from the user's laptop. Never report remote-container results as laptop measurements.

Target hardware: Intel Core i5-12450HX, 16 GB RAM, NVIDIA RTX 3050 Laptop GPU with 6 GB VRAM. Target session: Arch Linux, Hyprland, PipeWire/WirePlumber, potentially an existing Quickshell/Celestial desktop. Verify these assumptions locally. English is the initial acceptance language; provide explicit multilingual model selection for Hindi and Bengali. Mixed-language accuracy must be measured, not promised.

Do not replace the user's desktop shell or modify global audio settings. The app must operate independently of any existing rice.

## 2. Product behavior and scope

The primary flow is: focus a text field → press shortcut → speak → press shortcut again → transcribe → optionally clean up → insert the final text if the configured insertion adapter and focus checks permit it.

Required features:

- Toggle dictation; add hold-to-talk after the toggle path works.
- A small non-focus-stealing recording indicator with actual microphone activity.
- Local transcription with explicit model and language controls.
- Raw dictation as the dependable default; optional conservative text cleanup.
- Unicode output, cancellation, clear errors, and recovery of uninserted text.
- Configurable shortcuts and per-application insertion policies.
- An on-demand settings window and microphone test.
- No account, telemetry, cloud processing, persistent transcript history, or always-listening microphone by default.

Excluded from the initial release: wake words, meeting recording, speaker diarization, autonomous computer control, RAG, screen capture, silent reading of application contents, and automatic sending/executing of dictated text. Do not expand the project into a general assistant.

## 3. Chosen technology stack

Use this stack unless a measured compatibility blocker requires a documented change:

| Layer | Choice | Purpose |
| --- | --- | --- |
| Background controller and CLI | Rust, stable toolchain | Small native processes, explicit ownership, reliable IPC and lifecycle |
| Async control I/O | Tokio with only needed features | Wait on sockets and events without busy polling |
| Configuration and messages | TOML; serde and JSON | Human-editable settings and versioned control messages |
| UI | Quickshell with Qt 6/QML and Qt Quick Controls | Native Wayland overlay and settings, compatible with the user's desktop style |
| Audio | PipeWire client through maintained bindings or a small reviewed native bridge | Direct capture and device lifecycle management |
| Local recognition | whisper.cpp in a separate native worker | CPU baseline, optional separately built CUDA worker |
| Local transport | Unix domain sockets; framed binary audio transport | No TCP server required |
| Lifecycle | systemd user service | Per-user supervision, bounded restarts, clean process teardown |
| Text insertion | Capability-tested Hyprland adapter plus Wayland clipboard | Practical first target with explicit fallback |
| Optional cleanup | Existing explicitly configured local inference endpoint | No mandatory extra model or server |

Do not add Electron, Chromium, a web server, PyTorch, or an always-running Python runtime to the default path. Development scripts may use Python. Do not put recognition or model loading in QML or the daemon. Use native dependencies with pinned versions and reproducible build inputs. Verify the selected Rust bindings and Quickshell APIs instead of inventing methods.

## 4. Processes and ownership

Implement four logical components:

1. `vaanid`: authoritative state machine, configuration, IPC, capture coordination, focus checks, and worker supervision. The only required long-lived application process.
2. `vaani`: short-lived CLI. Exposes `toggle`, `start`, `stop`, `cancel`, `status --json`, `settings`, `doctor`, and explicit copy/recovery actions. Commands use structured IPC, never shell text containing dictated content.
3. `vaani-worker`: local inference process containing whisper.cpp. Spawn only on dictation activation; terminate according to the selected residency profile. Never dynamically load CUDA into the idle controller.
4. Quickshell UI: a separate app-owned configuration, launched on demand. Overlay and settings may share one UI process while either is needed. Exit it when neither is needed; closing the overlay alone must not destroy an open settings window.

Audio capture can live in a dedicated thread in the controller, with its stream created only for active recording. Keep real-time audio callbacks separate from async control and inference work. Use bounded transport to the worker, with backpressure that cannot block the audio callback.

Start capture and model loading concurrently. Before capture is actually active, show “Starting microphone…” rather than “Listening.” Do not pretend speech before stream activation was recorded. If capture works while the model loads, retain the beginning of the utterance in bounded memory.

A worker crash must leave the controller operational. A UI crash during recording must stop capture and preserve recoverable audio in memory only; do not continue recording invisibly. Never replay capture or insertion after a controller restart.

## 5. Resource policy

Default to the **Economy** profile. These are design budgets to measure, not guaranteed benchmark results.

| Profile | Recognition residency | UI residency | Tradeoff |
| --- | --- | --- | --- |
| Economy, default | Exit worker after each completed/cancelled operation | Exit when overlay/settings no longer needed | Lowest inactive RAM; model loads again next time |
| Balanced | Keep worker for 60 seconds after activity | Same on-demand UI behavior | Faster repeated dictation; temporary extra RAM |
| Ready | Keep selected model resident while explicitly enabled | Same on-demand UI behavior | Lowest repeat startup latency; sustained model memory |

Economy settled-idle targets, measured 10 seconds after all transient UI/clipboard helpers exit:

- Controller RSS at or below 30 MiB, with an optimization goal below 20 MiB.
- Average controller CPU below 0.1% of one core across a 60-second idle sample.
- No active recording stream, inference worker, CUDA context, render timer, or status polling loop.
- No routine disk writes at idle.

Measure aggregate process-tree RSS and PSS where available; distinguish shared memory, file-backed pages, model page cache, and actual application residency. Report any surviving clipboard helper separately. Process exit does not imply Linux immediately drops cached model files. Never use `drop_caches`, disable swap, or alter global VM settings to make memory numbers look better.

Measure cold model startup, warm startup, microphone readiness, stop-to-final-text latency, insertion dispatch latency, peak RAM, and active VRAM separately. UI appearance target: 150 ms warm / 400 ms cold; capture readiness target: 250 ms. These are aspirations until measured. No unconditional subsecond transcription promise.

CPU inference is the default. Begin with four worker threads, make it configurable, and benchmark responsiveness. CUDA is optional, only after a user-selected GPU build is available. Do not wake the dedicated GPU merely to render the UI or check VRAM in a background timer. At activation, handle GPU allocation failure gracefully. A CPU fallback should use a suitable model and show the change.

## 6. Model selection and transcription

Use multilingual Whisper `base` as the initial economical model option; offer `base.en` for users choosing English-only operation and `small` for an accuracy-focused option. A first-run user choice must precede model download. These model names are choices to benchmark, not evidence that their accuracy is sufficient.

Use the model format supported by the pinned whisper.cpp build. Do not assume an arbitrary GGUF or Ollama model can be loaded. Display download size, estimated runtime memory as an estimate, model source, checksum, and license. Download to a temporary file, verify it, then rename atomically. Do not bundle large model weights into the package.

Start with complete-utterance transcription on stop, maximum 120 seconds. This is the first dependable vertical slice. Whisper is not inherently a true streaming recognizer. If incremental previews are added later, label them provisional and document the chunk/overlap method. Never insert unstable partial text into another application.

For longer dictation, use bounded speech segments with overlap and tested reconciliation, not repeated full-buffer inference on every audio frame. Handle punctuation, duplicate words at boundaries, mixed scripts, and final-segment flushing explicitly. Do not ship extended duration until those cases pass.

Silence must produce no inserted text. Use a tested VAD and recognition diagnostics, but do not present heuristic scores as calibrated confidence probabilities. VAD executes only during active dictation. Allow an explicit language setting because automatic language detection can fail on short utterances. Preserve the spoken language; translation and transliteration are separate opt-in modes.

## 7. Audio handling

Capture through the user's existing PipeWire graph. Select the default input at the beginning of each session, or a configured device by a stable property where possible. Do not persist transient numeric node IDs as permanent device identity.

Negotiate the actual device format, downmix safely, and resample to the recognizer's expected mono 16 kHz stream. Use a real streaming resampler. Treat 16 kHz as a recognizer input requirement, not an assumption about microphone hardware.

Use approximately 20 ms processing blocks, preallocated callback buffers, and bounded queues. No disk I/O, model inference, JSON serialization, blocking locks, or expensive allocations in the real-time callback. Float32 mono at 16 kHz for 120 seconds is approximately 7.68 MB of audio payload; account for copies and intermediate buffers separately.

Keep audio in memory by default. If transport needs a shared object, prefer an inherited pipe/socket or supported anonymous memory mechanism. Avoid temporary WAV files as the production architecture. Do not encode PCM in JSON/base64.

Do not restart PipeWire, pipewire-pulse, WirePlumber, EasyEffects, or desktop portals. Do not modify default input/output devices, Bluetooth profiles, gain, or sample-rate configuration. Allow an existing EasyEffects virtual source to be selected. Do not build a second global denoising chain automatically.

If an active input disappears, stop and report “Microphone disconnected”; preserve captured content for an explicit recovery action. Do not silently change microphones halfway through an utterance. Recover future sessions after PipeWire reconnects using event-driven notifications and bounded backoff. On stop/cancel, close the recording stream immediately, independently of transcription completion.

## 8. UI specification

Create a restrained, native-feeling interface. Use an original visual identity rather than copying Wispr branding.

Recording overlay:

- Bottom-center on the monitor containing the starting target window; fall back to active monitor.
- Approximately 300 × 56 logical pixels, 24 px above the usable lower edge, with adaptive placement around reserved panels.
- Rounded 18 px corners, opaque charcoal `#17181D`, foreground `#F5F5F7`, muted text `#B7BAC5`, lavender accent `#B9A3FF`, warning `#FFD18A`, error `#FF8C9B`.
- Use actual audio amplitude in a compact waveform, a timer, a state label, and accessible stop/cancel controls.
- Text labels: “Starting microphone…”, “Listening”, “Transcribing…”, “Cleaning up…”, “Text ready”, and specific errors.
- No permanent idle pill, blur shader, bouncing decoration, or hidden looping animation. Waveform updates at most 30 Hz while recording; stop animation when hidden. Respect reduced motion.
- Use layer-shell with no exclusive zone and no keyboard focus for the passive overlay. Verify the exact installed Quickshell API. Pointer interaction is allowed where it does not acquire keyboard focus.
- Do not use keyboard focus grabs to capture global shortcuts. Explicit review/settings opens a normal focusable window and disables automatic insertion for that operation.
- A settings switch can hide transcript previews, useful during screen sharing. This does not claim the compositor can exclude the overlay from every capture method.

Settings window:

- Approximately 760 × 560 logical pixels, resizable, with five pages: General, Audio, Recognition, Shortcuts, Privacy & Diagnostics.
- Include residency profile, model/language, CPU/GPU choice, input device test, shortcut status, insertion mode, app overrides, cleanup configuration, and opt-in history controls.
- Show plain-language tradeoffs beside settings. For example: “Unload after each dictation: saves memory; the next recording needs to load the model.”
- Use system fonts with Hindi/Bengali fallback, proper shaping, scalable text, accessible names, keyboard navigation, adequate contrast, and fractional-scale testing.
- Keep setup short: choose/download model, test mic, test insertion in a harmless text box, then show shortcuts. Report missing capabilities instead of pretending setup succeeded.

## 9. Shortcuts and their semantics

Proposed defaults; detect conflicts against the actual Hyprland configuration and let the user change them:

| Shortcut | Action |
| --- | --- |
| Super + Alt + Space | Toggle dictation |
| Super + Alt + V | Hold-to-talk, optional after release semantics are tested |
| Super + Alt + Escape | Cancel active operation |
| Super + Alt + S | Open settings |
| Super + Alt + C | Explicitly copy pending final transcript |

Use compositor bindings to invoke the CLI; no raw `/dev/input` keyboard listener and no input-group membership requirement. The overlay must not intercept ordinary typing. Escape works locally in a focused settings/review window; do not permanently steal global Escape.

Generate version-correct Hyprland binding snippets after checking installed documentation. Do not assume examples from a different release still parse. Keep snippets in an app-owned include file; show the precise change required rather than replacing the user's config. Do not install duplicate bindings. Do not register recording shortcuts for the locked screen.

Ignore key-repeat for toggle/start. Hold-to-talk starts on press and stops on release. Test releasing modifiers before the main key, interrupted key sequences, compositor reloads, and lost release events. If the compositor cannot provide reliable release matching, ship toggle mode and mark hold mode unavailable. Never let a missing key-up leave the mic recording indefinitely; enforce the session limit.

## 10. Wayland insertion: treat this as a core engineering problem

Do not assume X11 tools can type into native Wayland clients. Do not claim universal editable-field detection, universal password-field detection, or atomic “type into the original cursor” behavior.

Build a `TextInserter` interface returning one of: unsupported, copy-ready, dispatch-attempted, failed, or confirmed-by-an-app-specific-adapter. A successful key event dispatch is not proof an app accepted the text.

Initial Hyprland adapter:

1. Record target window identity and application identifier at dictation start using supported compositor IPC; avoid retaining window titles or document contents.
2. At completion, check the target still exists and has focus. If focus changed, show “Text ready — target changed” and keep the result for explicit copy/review. Do not force focus back automatically.
3. A window match cannot prove the cursor stayed in the same field. Expose “review before insertion” for users who need stricter control, and explain this remaining limitation.
4. In configured automatic mode, offer the final UTF-8 plain text on the Wayland clipboard and use a verified compositor key-dispatch capability for the selected application's paste chord. Resolve held shortcut modifiers safely before dispatch; abort to copy-only if their state cannot be established reliably. Never guess with a blind sleep and hope it worked.
5. Test `Ctrl+V` behavior in ordinary applications; configure terminal adapters separately. Clipboard insertion is not direct IME insertion.
6. Recheck focus immediately before dispatch. Document the unavoidable race between the check and delivery where no atomic API exists. Report “Paste requested” rather than “Inserted successfully” when delivery cannot be confirmed.

Clipboard policy:

- Use `wl-clipboard` or a tested native equivalent. Pass text through stdin/structured buffers, never shell interpolation or command-line text arguments.
- Default automatic clipboard mode requires a clear setup choice because it temporarily replaces clipboard contents and clipboard managers may retain dictated text.
- Own only the plain-text selection created by this operation. Use a bounded serving period; keep text recoverable in memory when paste fails. Account for clipboard helper residency.
- Do not claim arbitrary images, MIME formats, lazy clipboard providers, or clipboard history can be saved and restored losslessly.
- Optional restoration is limited to a bounded plain-text snapshot and only if the clipboard still belongs to this operation. If ownership cannot be checked reliably, do not restore or clear it automatically. Never overwrite content the user copied meanwhile.
- Do not use a fixed tiny timer or first clipboard read as proof that the target consumed the paste: managers may read the offer before the application does.

Default terminal policy is copy-only/review. Multiline text can execute commands in terminals even without an explicit synthetic Enter. Do not automatically paste multiline shell-like content, or append Enter. Never execute dictated shell commands.

Optional later adapters: Fcitx5 through a properly implemented input-method integration, or portals where the compositor actually supports the required capability. Do not invent a universal D-Bus “commit text” call. `ydotool` is an explicit optional fallback: it uses uinput and needs a daemon/access configuration; it must not become a hidden root dependency. Do not grant broad passwordless sudo or make uinput world-writable.

Unsupported environments receive copy-only behavior with a reason. GNOME, KDE, Sway, XWayland, and native Wayland support must be listed separately, only after testing.

## 11. Text cleanup and vocabulary

Modes:

- Raw: preserve recognizer output; only normalize obvious outer whitespace. Default and mandatory.
- Clean: optional correction of punctuation and obvious fillers through an explicitly configured local model.
- Vocabulary: user-maintained names and terms, used as bounded recognition hints where supported. Avoid unbounded prompts or indiscriminate search-and-replace.

Cleanup must preserve meaning, negation, numbers, names, units, code, paths, and spoken language. No answer generation, added facts, or “helpful” rewrites of technical claims. The transcript is untrusted data, including statements that look like model instructions. Delimit it and direct the cleanup model to edit only.

Keep the raw transcript available for comparison. Timeout or invalid cleanup output falls back to raw text. A short timeout should be configurable; do not silently discard recognition output. Semantic checks are heuristics, not proof of correctness. Never advertise guaranteed faithful LLM rewriting.

Do not start an additional local model server or preload a second model by default. Measure cleanup latency and memory separately. A future cloud provider needs explicit per-provider enablement, clear disclosure of what leaves the device, secure credential storage, and no silent fallback from local to cloud.

## 12. State machine and IPC

Define lifecycle states: IDLE, STARTING, RECORDING, TRANSCRIBING, CLEANING, READY, INSERTING, CANCELLED, ERROR. Model residency is a separate state from dictation lifecycle; Balanced may have a warm worker while dictation is IDLE.

Each operation gets a unique session ID. Only the controller can authorize transitions and insertion. Late worker results for cancelled or previous sessions are discarded. `stop` is idempotent and stops capture immediately; `cancel` invalidates all pending results. Duplicate commands must not duplicate insertion. While busy transcribing, reject new recording with a clear state response in the first release instead of silently queueing audio jobs.

Separate framed control messages from framed binary audio. Put the control socket under `$XDG_RUNTIME_DIR/vaani/` with directory mode 0700 and socket mode 0600; validate same-user peers where supported. Define protocol version, request ID, session ID, message size limits, errors, subscription semantics, and reconnect handling. Serialize socket writes through a single owner.

Use events for state/amplitude updates. No 10 ms status polling, no permanent `hyprctl` subprocess loop, no QML timer spawning commands to fetch state. Initial subscriber connection receives a state snapshot before later events. Drop/coalesce obsolete amplitude updates under load.

Bound queued requests, audio, transcript size, model hints, and pending result retention. Default pending final text expiry: five minutes in memory; offer explicit copy before expiry. Default audio retention ends after successful transcription or cancellation. Error recovery can retain audio briefly, with visible discard/retry controls and a bounded expiry.

## 13. Background service and privacy

Provide a systemd **user** unit, not a root service. Use a simple foreground controller, `Restart=on-failure`, bounded restart rate, and process-group cleanup. Resolve binary paths correctly for the chosen install prefix. Validate the unit using the installed systemd tooling. Treat hardening settings as compatibility-tested choices; do not block Wayland, PipeWire, or an explicitly enabled GPU worker accidentally.

Tie startup and shutdown to the actual graphical session. Do not assume `graphical-session.target` is managed by every Hyprland launch method. Detect UWSM or the relevant session setup and document one suitable integration. If importing environment values is needed, import only required display/session variables from the active session. Never import credentials or blindly copy the whole environment. Do not enable user lingering just for dictation.

Do not poll or record before activation. On session lock, suspend, logout, or compositor disconnect: cancel capture, prevent insertion, and invalidate active work. If trustworthy lock-state detection is unavailable, disable automatic insertion for that integration and document it. Unlocked state must be re-established before the next recording.

Use XDG locations: config in `$XDG_CONFIG_HOME/vaani`, model data in `$XDG_DATA_HOME/vaani/models`, optional state in `$XDG_STATE_HOME/vaani`, disposable files in `$XDG_CACHE_HOME/vaani`, runtime sockets in `$XDG_RUNTIME_DIR/vaani`. Apply standard XDG fallbacks where appropriate; do not invent a shared `/tmp` socket fallback when runtime security cannot be established.

Logs contain state, timings, bounded error details, and version information by default. No raw audio, transcripts, clipboard contents, credentials, or window titles. History is off by default; enabling it needs retention and delete controls. Notifications should not expose dictated content. Explain that memory-only handling is not a guarantee against swap, crash dumps, or other software running as the same user.

## 14. Repository and delivery

Use a small workspace, for example:

- `crates/core`: configuration, protocol, state transitions.
- `crates/daemon`: orchestration, capture, supervision, insertion.
- `crates/cli`: commands and diagnostics.
- `native/worker`: pinned whisper.cpp integration and worker protocol.
- `ui`: independent Quickshell configuration and components.
- `packaging`: user unit, desktop entry, Arch PKGBUILD, Hyprland include example.
- `tests`: state/IPC/integration tests and approved audio fixtures.
- `docs`: architecture, configuration, compatibility, performance, troubleshooting.

Keep interfaces focused. Do not build a general plugin framework before two real implementations need it. Include a lockfile, model manifest, example TOML config with schema version, license information, and exact reproducible build commands.

Deliver a working PKGBUILD; verify dependency package names against the current Arch repositories/AUR and distinguish official dependencies from AUR dependencies. No `curl | sh`, no automatic system upgrade, and no edits to unrelated user dotfiles. Model downloads belong to first-run setup, not package build or install hooks. Uninstall removes app-owned installation files and leaves user configuration/models unless explicitly requested otherwise.

## 15. Implementation sequence

Proceed in this order and complete each usable slice before expanding:

1. Inspect environment and repository; write a short architecture decision record with verified dependency versions and limitations.
2. Prove the three uncertain integrations: a non-focus-stealing overlay; bounded PipeWire capture; Unicode clipboard/paste behavior in a harmless Wayland text field. If a capability fails, implement copy-only operation and record the blocker.
3. Build controller/CLI/state machine, one-shot CPU transcription, and the toggle path end to end.
4. Add UI states, microphone test, model setup, focus-aware insertion policy, and pending result recovery.
5. Add cancellation races, session teardown, device-loss recovery, Economy worker exit, and measured resource reporting.
6. Add settings, packaging, documentation, and tested shortcut snippets.
7. Only then add Balanced/Ready residency, optional CUDA, hold-to-talk, cleanup, and incremental previews in that order where feasible. Clearly identify unimplemented optional features; do not disguise stubs as complete features.

Do not request confirmation for routine reversible coding work. Show concrete diffs before any external activation that needs consent. If lacking the actual desktop/audio environment, still implement and run meaningful unit/protocol tests, then provide exact remaining manual checks. Do not fabricate successful hardware testing.

## 16. Acceptance tests and evidence

Test the behaviors that can lose text, record unexpectedly, or insert in the wrong place:

- Toggle start/stop, key repeat, very fast press/release, cancellation during startup/inference/cleanup/insertion preparation, and late stale results.
- Silence, low-volume speech, background noise, names, negation, numbers, English/Hindi/Bengali scripts, and 5/30/120-second utterances.
- Microphone unplug, default-device change between sessions, PipeWire restart during capture, model failure, worker crash, UI crash, and model download interruption/checksum mismatch.
- Original target closes; focus changes; cursor moves within the same window; settings opened during processing; screen locks; machine suspends; logout occurs.
- Firefox/native Wayland text areas, a GTK or Qt editor, VS Code in its tested backend, and a terminal in copy-only mode. Record actual versions and XWayland/native status.
- Unicode, multiline content, clipboard manager interference, user clipboard change during processing, non-text prior clipboard, held modifiers, and insertion failure. Verify no accidental Enter and no repeated paste.
- 20 successive dictations followed by idle: no orphaned workers, leaked audio streams, accumulating memory, or active GPU context in Economy.
- Test malformed/oversized IPC, stale sockets, duplicate clients, and incompatible protocol versions.

Report word error rate for an appropriately annotated English fixture set and character error rate where suitable for Hindi/Bengali; state dataset size and limitations. Report names/numbers/negations separately. Use approved non-sensitive samples. Never call one successful sentence an accuracy benchmark.

For latency report sample count and p50/p95, with CPU/GPU backend, model, model quantization, threads, power mode, and cold versus warm conditions. Report targets missed honestly. Capture process memory with `/proc`/equivalent tooling and GPU measurements only during the explicit benchmark, not continuous production polling.

Final deliverables: working source; build/install/uninstall instructions; example configuration; unit and integration results; screenshots of actual UI states; tested compatibility table; measured resource report; and an explicit list of incomplete or environment-blocked items. A screenshot alone is not a functioning app.

## 17. Primary references and verification notes

Consult these upstream references and installed documentation while implementing. Versions and URLs can change; verify the selected release. This prompt's process boundaries, budgets, defaults, and UX are proposed design decisions, not upstream guarantees.

- [Wispr Flow](https://wisprflow.ai/) — reference interaction: dictation, formatting, and vocabulary; do not copy its branding or assume its platform guarantees apply here.
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp) — model formats, CPU/GPU build support, VAD and inference examples. Model memory and active latency depend on the actual build and configuration.
- [Quickshell WlrLayershell](https://quickshell.org/docs/v0.2.0/types/Quickshell.Wayland/WlrLayershell/) — layer-shell properties; this is versioned documentation and must match the installation.
- [Quickshell Socket](https://quickshell.org/docs/v0.2.0/types/Quickshell.Io/Socket/) — local socket client integration for event-driven UI.
- [wl-clipboard](https://github.com/bugaevc/wl-clipboard) — Wayland clipboard utilities; clipboard ownership is distinct from synthetic key delivery.
- [ydotool](https://github.com/ReimuNotMoe/ydotool) — optional uinput-based fallback and its daemon requirements.
- [PipeWire documentation](https://docs.pipewire.org/) — stream negotiation, capture, device events, callback constraints.

Hyprland binding/dispatch syntax and systemd unit options must be verified against the installed versions. Their documentation pages could not be reliably retrieved while preparing this prompt, so no unverified ready-to-run binding or service snippet is presented as authoritative.
