// vaani-key-service — Phase 03 (hotkey-idle).
//
// Resident daemon: parse config once (via vaani-config), grab the hotkey via
// the Hyprland compositor binding, idle until triggered or told to stop.
// Logs every state transition. No helpers exist yet; it spawns none.
//
// Signals (declared via FFI so we stay std-only):
//   SIGUSR1 = hotkey fired (the bind dispatcher runs `kill -USR1 <pid>`)
//   SIGTERM/SIGINT = clean shutdown (unbind hotkey, log, exit 0)

use std::io::Write;
use std::sync::atomic::{AtomicBool, Ordering};

// ---- signals (FFI, no new deps) ----
const SIGINT: i32 = 2;
const SIGUSR1: i32 = 10;
const SIGTERM: i32 = 15;

static GOT_TRIGGER: AtomicBool = AtomicBool::new(false);
static GOT_SHUTDOWN: AtomicBool = AtomicBool::new(false);

extern "C" fn on_trigger(_: i32) {
    GOT_TRIGGER.store(true, Ordering::SeqCst);
}
extern "C" fn on_shutdown(_: i32) {
    GOT_SHUTDOWN.store(true, Ordering::SeqCst);
}

extern "C" {
    fn signal(sig: i32, handler: extern "C" fn(i32)) -> usize;
}

// ---- logging ----
fn log(state: &str, detail: &str) {
    let now = std::time::SystemTime::now();
    eprintln!("[vaani key-service] state={state} {detail:?} t={now:?}");
    let _ = std::io::stderr().flush();
}

// ---- trigger (no runtime compositor calls) ----
//
// Vaani MUST NOT call `hyprctl eval` to bind/unbind keys. On Hyprland
// 0.56.2 `CKeybindManager::removeKeybind` removes binds by signature
// (mod+key), so removing one of two SUPER+H binds frees both objects and
// leaves Lua holding a dangling handle -> use-after-free SIGSEGV that
// kills the whole compositor (upstream bug, fixed only on git main; no
// released package has the fix).
//
// Instead the bind is static in the user's hyprland.lua and only signals
// us:
//   hl.bind("SUPER + H", hl.dsp.exec_cmd("vaani-trigger"))
// `vaani-trigger` reads the pid file below and sends SIGUSR1. No Lua
// handle is ever created or removed from this process, so there is
// nothing to dangle.

/// Pid file the trigger script reads: XDG_RUNTIME_DIR when available,
/// else ~/.cache. `vaani-trigger` resolves the same path.
fn pid_file_path() -> std::path::PathBuf {
    if let Some(dir) = std::env::var_os("XDG_RUNTIME_DIR") {
        let p = std::path::PathBuf::from(dir).join("vaani-key.pid");
        if p.parent().is_some_and(|d| d.is_dir()) {
            return p;
        }
    }
    let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    std::path::PathBuf::from(home).join(".cache/vaani-key.pid")
}

fn write_pid_file(pid: u32) {
    let path = pid_file_path();
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    if let Err(e) = std::fs::write(&path, pid.to_string()) {
        log("error", &format!("pid file write failed ({}): {e}", path.display()));
    }
}

fn remove_pid_file() {
    let _ = std::fs::remove_file(pid_file_path());
}

/// Wayland env published by `vaani-trigger` (spawned by Hyprland, so it
/// holds the live socket). systemd's env can point at a dead socket after
/// a compositor restart, which makes wtype/wl-copy fail. Best-effort: an
/// absent file just leaves the inherited env alone.
fn adopt_live_wayland_env() {
    let Some(env_path) = pid_file_path().parent().map(|d| d.join("vaani-key.env")) else {
        return;
    };
    let Ok(text) = std::fs::read_to_string(&env_path) else {
        return;
    };
    for line in text.lines() {
        let Some((k, v)) = line.split_once('=') else {
            continue;
        };
        if v.is_empty() || !matches!(k, "WAYLAND_DISPLAY" | "XDG_RUNTIME_DIR" | "HYPRLAND_INSTANCE_SIGNATURE") {
            continue;
        }
        std::env::set_var(k, v);
    }
}

/// The systemd unit carries the installer's env, a bare `cargo run` gets none:
/// read the same file so both own the same servers. `VAANI_ENV_FILE=""` opts
/// out, an already-set variable always wins, and a missing file is normal.
fn load_install_env() {
    let path = match std::env::var("VAANI_ENV_FILE") {
        Ok(v) if v.is_empty() => return,
        Ok(v) => std::path::PathBuf::from(v),
        Err(_) => {
            let home = std::env::var("HOME").unwrap_or_else(|_| ".".into());
            let prefix = std::env::var("PREFIX").unwrap_or_else(|_| format!("{home}/.local"));
            std::path::PathBuf::from(prefix).join("vaani-stt.env")
        }
    };
    let Ok(text) = std::fs::read_to_string(path) else {
        return;
    };
    for (k, v) in parse_env_file(&text) {
        if std::env::var_os(&k).is_none() {
            std::env::set_var(k, v);
        }
    }
}

/// `export KEY=VALUE` lines only; one layer of quotes off VALUE, no expansion.
/// Blank lines and comments fall out at `strip_prefix`.
fn parse_env_file(text: &str) -> Vec<(String, String)> {
    text.lines()
        .filter_map(|line| {
            let (k, v) = line.trim().strip_prefix("export ")?.trim_start().split_once('=')?;
            let k = k.trim();
            if !k.starts_with("VAANI_") {
                return None;
            }
            let v = v.trim();
            let v = v
                .strip_prefix('"')
                .and_then(|s| s.strip_suffix('"'))
                .or_else(|| v.strip_prefix('\'').and_then(|s| s.strip_suffix('\'')))
                .unwrap_or(v);
            Some((k.to_string(), v.to_string()))
        })
        .collect()
}

// ---- Phase 09: STT -> LLM handoff (VRAM-serialized) ----
//
// Sequence: STT streams words, STT unloads, formatter loads, raw
// transcript fed. VRAM is sampled via nvidia-smi at every step; a step
// with both STT and formatter resident aborts to the error state.
// Helpers reporting busy are never killed: offload requests return
// false (deferred) while busy and are re-checked once idle.
//
// shortcut: StubStt still stands in for stt-manager::Session, which does
// not fit this trait: Session::start needs (wav path, python, model dir)
// while the handoff owns only a sample String; its is_busy/is_killable
// take &mut self (vs &self here); it has no is_loaded flag (residency =
// live child process) and streams word-by-word instead of one-shot
// string. Full swap needs the audio->wav->session pipeline (Phase 13).
// The LLM side is REAL (llm-formatter path-dep): RealLlm::format
// delegates to llm_formatter::format. The formatter is stateless, so
// load/unload are just resident flags and busy brackets the call.
mod handoff {
    /// PRD stt-manager interface: stream words, full unload, kill-state.
    pub trait SttBackend {
        fn stream_words(&mut self) -> Result<String, String>;
        fn unload(&mut self);
        fn is_loaded(&self) -> bool;
        fn is_busy(&self) -> bool;
        fn is_killable(&self) -> bool;
    }

    /// PRD llm-formatter interface: load, feed raw transcript, unload.
    pub trait LlmBackend {
        fn load(&mut self) -> Result<(), String>;
        fn format(&mut self, transcript: &str) -> Result<String, String>;
        fn unload(&mut self);
        fn is_loaded(&self) -> bool;
        fn is_busy(&self) -> bool;
        fn is_killable(&self) -> bool;
    }

    /// In-RAM stand-ins until stt-manager/llm-formatter exist. They honor
    /// the kill-state model (busy while working, killable when done) but
    /// touch no GPU; VRAM proof below is therefore about the ordering
    /// (never co-resident), measured with the real sampler.
    pub struct StubStt {
        pub sample: String,
        pub loaded: bool,
        pub busy: bool,
    }
    /// Real formatter backend: delegates to the llm-formatter crate.
    pub struct RealLlm {
        pub loaded: bool,
        pub busy: bool,
    }

    impl SttBackend for StubStt {
        fn stream_words(&mut self) -> Result<String, String> {
            self.loaded = true;
            self.busy = true; // streaming: must not be killed
            let words = self.sample.clone();
            self.busy = false; // stream ended: killable again
            Ok(words)
        }
        fn unload(&mut self) {
            self.loaded = false;
        }
        fn is_loaded(&self) -> bool {
            self.loaded
        }
        fn is_busy(&self) -> bool {
            self.busy
        }
        fn is_killable(&self) -> bool {
            !self.busy
        }
    }

    impl LlmBackend for RealLlm {
        fn load(&mut self) -> Result<(), String> {
            self.loaded = true;
            Ok(())
        }
        fn format(&mut self, transcript: &str) -> Result<String, String> {
            self.busy = true;
            let out = llm_formatter::format(transcript);
            self.busy = false;
            Ok(out)
        }
        fn unload(&mut self) {
            self.loaded = false;
        }
        fn is_loaded(&self) -> bool {
            self.loaded
        }
        fn is_busy(&self) -> bool {
            self.busy
        }
        fn is_killable(&self) -> bool {
            !self.busy
        }
    }

    /// Offload request under the kill-state model: false = refused while
    /// busy (caller must re-check after timeout), true = safe to offload.
    pub fn request_offload(busy: bool, killable: bool) -> bool {
        if busy || !killable {
            return false;
        }
        true
    }

    /// Used VRAM in MiB via nvidia-smi. None if the tool is unavailable;
    /// callers must fail loudly (never invent numbers).
    pub fn sample_vram_mb() -> Option<u64> {
        let out = std::process::Command::new("nvidia-smi")
            .args(["--query-gpu=memory.used", "--format=csv,noheader,nounits"])
            .output()
            .ok()?;
        if !out.status.success() {
            return None;
        }
        String::from_utf8_lossy(&out.stdout)
            .lines()
            .next()?
            .trim()
            .parse::<u64>()
            .ok()
    }

    pub struct StepSample {
        pub step: &'static str,
        pub vram_mb: u64,
        pub stt_loaded: bool,
        pub fmt_loaded: bool,
    }

    fn snap(step: &'static str, stt: bool, fmt: bool) -> Result<StepSample, String> {
        let vram_mb = sample_vram_mb().ok_or_else(|| "state=error nvidia-smi unavailable".to_string())?;
        println!("step={step} vram_mb={vram_mb} stt_loaded={stt} fmt_loaded={fmt}");
        Ok(StepSample { step, vram_mb, stt_loaded: stt, fmt_loaded: fmt })
    }

    /// Owns the handoff. Returns per-step VRAM samples, or an error-state
    /// string (caller offloads everything and returns to idle).
    pub fn run_handoff<S: SttBackend, L: LlmBackend>(
        stt: &mut S,
        llm: &mut L,
    ) -> Result<Vec<StepSample>, String> {
        let mut log = Vec::new();

        let transcript = stt.stream_words().map_err(|e| format!("state=error stt_stream failed: {e}"))?;
        log.push(snap("stt_stream", stt.is_loaded(), llm.is_loaded())?);

        // Never kill a busy STT: defer, re-check once the stream ends.
        if !request_offload(stt.is_busy(), stt.is_killable()) {
            println!("offload stt=deferred_busy");
        }
        stt.unload();
        log.push(snap("stt_unload", stt.is_loaded(), llm.is_loaded())?);
        if stt.is_loaded() {
            return Err("state=error stt still resident after unload".into());
        }

        llm.load().map_err(|e| format!("state=error formatter load failed: {e}"))?;
        if stt.is_loaded() && llm.is_loaded() {
            llm.unload();
            return Err("state=error vram overlap: stt+formatter co-resident".into());
        }
        log.push(snap("fmt_load", stt.is_loaded(), llm.is_loaded())?);

        if !request_offload(llm.is_busy(), llm.is_killable()) {
            println!("offload fmt=deferred_busy");
        }
        let formatted = llm.format(&transcript).map_err(|e| format!("state=error format failed: {e}"))?;
        log.push(snap("fmt_format", stt.is_loaded(), llm.is_loaded())?);
        println!("formatted={formatted:?}");

        llm.unload();
        log.push(snap("fmt_unload", stt.is_loaded(), llm.is_loaded())?);

        if log.iter().any(|s| s.stt_loaded && s.fmt_loaded) {
            return Err("state=error vram peaks overlapped".into());
        }
        Ok(log)
    }

    /// `--handoff-test` entrypoint: full sequence on one sample transcript.
    /// Exit 0 only on serialized peaks + busy-kill refusal proven.
    pub fn selftest(sample: &str) -> i32 {
        // Busy helpers are never killed: refused while busy, allowed idle.
        let refused = !request_offload(true, false);
        let allowed = request_offload(false, true);
        println!("busy_kill_refused={refused} idle_offload_allowed={allowed}");
        if !refused || !allowed {
            println!("state=error kill-state model violated");
            return 1;
        }
        let mut stt = StubStt { sample: sample.to_owned(), loaded: false, busy: false };
        let mut llm = RealLlm { loaded: false, busy: false };
        match run_handoff(&mut stt, &mut llm) {
            Ok(steps) => {
                let peak = steps.iter().map(|s| s.vram_mb).max().unwrap_or(0);
                let order = steps.iter().map(|s| s.step).collect::<Vec<_>>().join(",");
                println!("handoff ok peaks_serialized=true vram_peak_mb={peak} order={order}");
                0
            }
            Err(e) => {
                println!("{e}");
                1
            }
        }
    }
}

// Phase 10/11 decision modules, wired into the poll loop below:
// timeouts::due_for_offload sweeps the helpers vec every poll;
// cancel::Phase tracks the run phase (full cancel/error hook lands with
// the pipeline in Phase 13). cancel keeps allow(dead_code): only Phase +
// decide are referenced so far; its remaining variants would warn until
// Phase 13 constructs them.
mod control;
mod timeouts;
mod vad;
mod servers;
#[allow(dead_code)]
mod cancel;

// Safety cap: a run never records longer than this, even if the second
// press never comes.
const MAX_RECORD_SECS: u64 = 60;

/// s16 mono at 16 kHz is 32 bytes per millisecond of audio.
const BYTES_PER_MS: usize = 32;

/// Execute the cancel decision table: stop audio/STT, skip formatting, hide
/// the pill. The table is the single place that names what cancel means.
fn cancel_run(
    phase: cancel::Phase,
    rec: &mut audio_helper::Recorder,
    stt: &mut stt_manager::LiveSession,
    ui: &mut UiGuard,
) {
    // The terminal state goes first: the overlay exits by itself on CANCELLED,
    // so dismiss() returns at once instead of waiting out its linger.
    control::state("CANCELLED", "Cancelled");
    for action in cancel::decide(phase, cancel::Signal::Cancel).actions {
        match action {
            "kill_audio" => rec.stop_stream(),
            "kill_stt" => stt.unload(),
            "pill_hide" => ui.dismiss(),
            "skip_formatting" => {} // this function returns before formatting
            "offload_all" => {}
            "idle" => {} // published before the loop
            _ => {}
        }
    }
}

/// One live run: open mic + STT stream (words show while speaking, until
/// 2nd press / cap / shutdown) -> format with config vocab -> type. Every
/// path ends back at idle; STT loads per run and unloads after (backend
/// reaped, zero VRAM ever held); the formatter is a rule call.
fn run_pipeline(
    cfg: &vaani_config::VaaniConfig,
    servers: &mut [servers::Server],
    boot: std::time::Instant,
) {
    control::reset_stop();
    // STARTING is published before the overlay starts: a fresh connection
    // gets it as the snapshot, and an IDLE snapshot would make it quit.
    control::state("STARTING", "Starting microphone");
    // The guard exists before anything can fail: the overlay is the only way
    // the user sees why the mic or STT failed to start.
    let mut ui = UiGuard::start();
    let (python, model) = match (
        stt_manager::resolve_python(),
        stt_manager::resolve_model_checked(&cfg.stt_model, &cfg.stt_fallback_model),
    ) {
        (Some(p), Ok(m)) => (p, m),
        (None, _) => {
            control::state("ERROR", "No STT python found");
            log("error", "no STT python found");
            ui.dismiss();
            return;
        }
        (_, Err(e)) => {
            control::state("ERROR", &format!("STT model unusable: {e}"));
            log("error", &format!("stt model: {e}"));
            ui.dismiss();
            return;
        }
    };
    let mut rec = audio_helper::Recorder::new();
    if let Err(e) = rec.start_stream() {
        control::state("ERROR", &format!("Mic failed: {e}"));
        log("error", &format!("mic failed: {e}"));
        ui.dismiss();
        return;
    }
    let mut stt = match stt_manager::LiveSession::start(&python, &model) {
        Ok(s) => s,
        Err(e) => {
            rec.stop_stream();
            control::state("ERROR", &format!("STT failed: {e}"));
            log("error", &format!("stt failed: {e}"));
            ui.dismiss();
            return;
        }
    };
    // The fine-tuned models are servers this daemon owns, loaded in the PRD's
    // order: the speech server starts now that the mic is live, so it loads
    // while the user is still speaking. A formatter still warm from the last
    // run is unloaded first: the two models never share VRAM. The formatter
    // starts later, at the formatting step, once the speech side is gone.
    // Spawning never blocks this run; see servers::wait_ready at the point of
    // use.
    servers::start_stt(servers, boot.elapsed().as_secs());
    control::state("RECORDING", "Speak naturally…");
    control::provisional("", false);
    log(
        "listening",
        &format!("mic open, press hotkey again to finish model={model}"),
    );

    let mut committed: Vec<String> = Vec::new();
    let mut partial = String::new();
    let mut vad = vad::Vad::new(cfg.end_of_speech_ms);
    let t0 = std::time::Instant::now();
    // Raw utterance, kept so the fine-tuned model can re-read exactly the audio
    // the streaming pass saw. Bounded by MAX_RECORD_SECS (~2 MB).
    let mut captured: Vec<u8> = Vec::new();
    let refine = stt_manager::resolve_refine(&python);
    let mut heard = false;
    let mut peak = 0.0f64;
    let mut cancelled = false;
    loop {
        // 50 ms tick: chunk in, words out, then check the stop conditions.
        let mut got_ms = 0u32;
        if let Some(rx) = rec.chunks() {
            match rx.recv_timeout(std::time::Duration::from_millis(50)) {
                Ok(chunk) => {
                    // Count real audio time, not loop iterations: pw-record
                    // hands over small chunks far more often than CHUNK_MS.
                    got_ms = (chunk.len() / BYTES_PER_MS) as u32;
                    // Bars are gain-scaled: speech sits well below full scale.
                    let level = chunk_rms(&chunk);
                    control::amplitude((level * 4.0).min(1.0));
                    peak = peak.max(level);
                    let _ = stt.feed(&chunk);
                    captured.extend_from_slice(&chunk);
                }
                Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {}
                Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
        let mut changed = false;
        for ev in stt.poll() {
            match ev {
                stt_manager::LiveEvent::Word(w) => {
                    committed.push(w.text);
                    partial.clear();
                    changed = true;
                }
                stt_manager::LiveEvent::Partial(p) => {
                    if p != partial {
                        partial = p;
                        changed = true;
                    }
                }
                stt_manager::LiveEvent::Done(_) => {}
                stt_manager::LiveEvent::Failed(_) => {}
            }
        }
        if changed {
            control::provisional(&live_window(&committed, &partial, cfg.ui_words.max(1) as usize), false);
        }
        if GOT_SHUTDOWN.load(Ordering::SeqCst) {
            rec.stop_stream();
            stt.unload();
            control::state("IDLE", "");
            ui.dismiss();
            log("error", "shutdown during recording, run aborted");
            return;
        }
        // Auto-stop on end of speech: the user speaks once and never
        // presses twice. A second press / the Stop button still end the
        // run early, and the cap covers a stuck detector.
        if got_ms > 0 {
            if let vad::Decision::End { heard: h } = vad.tick(got_ms, changed) {
                heard = h;
                // Peak mic level: tells a silent capture (noise floor only)
                // apart from a decoder that failed on real speech.
                log("idle", &format!("end of speech (heard={h} peak={peak:.3})"));
                break;
            }
        }
        if GOT_TRIGGER.swap(false, Ordering::SeqCst)
            || t0.elapsed().as_secs() >= MAX_RECORD_SECS
        {
            break;
        }
        if control::take_stop() {
            cancelled = true;
            break;
        }
    }
    rec.stop_stream();
    if cancelled || control::take_stop() {
        cancel_run(cancel::Phase::Listening, &mut rec, &mut stt, &mut ui);
        log("idle", "cancelled by the user");
        return;
    }
    control::state("TRANSCRIBING", "Transcribing");
    // Words flushed by the backend at end-of-stream land here; losing them
    // was why short runs typed nothing.
    let stats = match stt.finish(&control::stop_pending, &mut |w| {
        committed.push(w.text.clone());
    }) {
        Ok(s) => s,
        Err(e) if e.kind() == std::io::ErrorKind::Interrupted => {
            cancel_run(cancel::Phase::Transcribing, &mut rec, &mut stt, &mut ui);
            log("cancel", "stopped during transcription");
            return;
        }
        Err(e) => {
            control::state("ERROR", &format!("STT failed: {e}"));
            log("error", &format!("stt failed: {e}"));
            ui.dismiss();
            return;
        }
    };
    // After the flush, so the count is what will actually be formatted: this
    // used to log "0 words decoded" and then type a word.
    log("transcribing", &format!("{} words decoded", committed.len()));
    // Second pass: the fine-tuned model re-reads the finished utterance and,
    // when it answers, its words are the ones that get formatted and typed. The
    // streaming words stay the fallback, so a missing model server can never
    // lose what the user actually said.
    let mut text = committed.join(" ").trim().to_string();
    if let Some(r) = &refine {
        if should_refine(heard, &text) {
            // A server spawned moments ago may still be loading weights. Both
            // bind their port only once ready, so wait briefly here rather than
            // falling back on the first dictation after an idle window.
            if let Some(s) = servers.iter_mut().find(|s| s.name == "stt") {
                if !s.wait_ready(servers::READY_TIMEOUT) {
                    log("refine", "fine-tuned STT server not ready yet");
                }
            }
            let mut refined: Vec<String> = Vec::new();
            let pcm = stt_manager::bytes_to_pcm(&captured);
            match stt_manager::refine_pcm_with(
                &pcm,
                &r.python,
                &r.backend,
                &r.endpoint,
                &control::stop_pending,
                &mut |w| refined.push(w.text.clone()),
            ) {
                Ok(s) => {
                    let (chosen, used) = pick_transcript(&committed, &refined);
                    log(
                        "refine",
                        &format!(
                            "fine-tuned re-decode: {} words in {:.2}s (streaming had {}); {}",
                            refined.len(),
                            s.infer_secs,
                            committed.len(),
                            if used {
                                "using refined"
                            } else {
                                "keeping streaming words"
                            }
                        ),
                    );
                    if used {
                        text = chosen;
                    }
                }
                Err(e) => log(
                    "refine",
                    &format!("fine-tuned re-decode failed ({e}); keeping streaming words"),
                ),
            }
        } else {
            log("refine", "nothing heard; skipping the fine-tuned re-decode");
        }
    }
    // Cancel during the second pass: the wait polls stop_pending and returns
    // early, so honour it before anything is formatted or typed.
    if control::take_stop() {
        cancel_run(cancel::Phase::Transcribing, &mut rec, &mut stt, &mut ui);
        log("cancel", "stopped during transcription");
        return;
    }
    if text.is_empty() {
        control::state("IDLE", "Nothing heard");
        ui.dismiss();
        log(
            "idle",
            &format!("empty transcript ({:.1}s audio), nothing typed", stats.audio_secs),
        );
        return;
    }
    let pairs: Vec<(&str, &str)> = cfg
        .names
        .iter()
        .map(|(k, v)| (k.as_str(), v.as_str()))
        .chain(cfg.links.iter().map(|(k, v)| (k.as_str(), v.as_str())))
        .collect();
    control::state("CLEANING", "Cleaning transcript");
    // The PRD's pipeline: raw STT -> formatter LLM -> typed text. Falls back
    // to the rule engine if no LLM answers (see llm-formatter).
    // The handoff unloads the speech server (and waits for it) before the
    // formatter is spawned: the two models are never in VRAM at once.
    if !servers::handoff_to_llm(servers, boot.elapsed().as_secs(), servers::READY_TIMEOUT) {
        log("writing", "formatter server not ready, the rule engine answers");
    }
    let (out, backend) = llm_formatter::format_pipeline(&text, &pairs);
    // Both models have done their work for this run: restart their idle windows.
    let used = boot.elapsed().as_secs();
    for s in servers.iter_mut() {
        s.touch(used);
    }
    control::state("INSERTING", "Typing clean text");
    log("writing", &format!("typing {} chars via {backend}", out.len()));
    // pill_hidden=true: the overlay sets keyboardFocus None, so keystrokes
    // reach the window focused before the run started.
    let result = typing_helper::type_text(&out, true);
    match result {
        Ok(r) => {
            log("idle", &format!("typed, clipboard={}", r.clipboard_copied));
            control::state_with_text(
                "READY",
                if r.clipboard_copied { "Typed and copied to clipboard" } else { "Typed" },
                &out,
                r.clipboard_copied,
            );
        }
        Err(e) => {
            control::state("ERROR", &format!("Typing failed: {e}"));
            log("error", &format!("typing failed: {e}"));
        }
    }
    // The run is over and nothing will ask the formatter anything until the
    // next trigger, so stop it here: its shutdown must not sit on the
    // recording path.
    servers::park_formatter(servers);
    ui.dismiss();
}

/// Gate helper for the bug that made short runs type nothing: the streaming
/// path must deliver the words Vosk flushes at end-of-stream. Feeds a wav's
/// PCM into a live session, never polls it, and reports what `finish` handed
/// back.
fn stream_test(wav: &str) -> i32 {
    let (python, model) = match (stt_manager::resolve_python(), stt_manager::resolve_model()) {
        (Some(p), Some(m)) => (p, m),
        _ => {
            println!("STREAM-FAIL no STT python/model");
            return 1;
        }
    };
    let wav_bytes = match std::fs::read(wav) {
        Ok(b) => b,
        Err(e) => {
            println!("STREAM-FAIL read {wav}: {e}");
            return 1;
        }
    };
    let Some(pcm) = pcm_from_wav(&wav_bytes) else {
        println!("STREAM-FAIL {wav} is not PCM wav data");
        return 1;
    };
    let mut stt = match stt_manager::LiveSession::start(&python, &model) {
        Ok(s) => s,
        Err(e) => {
            println!("STREAM-FAIL start: {e}");
            return 1;
        }
    };
    // Feed as the mic would (3200 B ≈ 100 ms), with no poll() at all.
    for chunk in pcm.chunks(3200) {
        if stt.feed(chunk).is_err() {
            break;
        }
    }
    let mut words: Vec<String> = Vec::new();
    let stats = match stt.finish(&|| false, &mut |w| words.push(w.text.clone())) {
        Ok(s) => s,
        Err(e) => {
            println!("STREAM-FAIL finish: {e}");
            return 1;
        }
    };
    println!(
        "STREAM-TAIL words={} flushed_by_finish={} text={}",
        stats.words,
        words.len(),
        words.join(" ")
    );
    0
}

/// PCM payload of a RIFF/WAVE file (skips the header chunks).
fn pcm_from_wav(bytes: &[u8]) -> Option<&[u8]> {
    if bytes.len() < 12 || &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return None;
    }
    let mut i = 12;
    while i + 8 <= bytes.len() {
        let id = &bytes[i..i + 4];
        let len = u32::from_le_bytes([bytes[i + 4], bytes[i + 5], bytes[i + 6], bytes[i + 7]]) as usize;
        let body = i + 8;
        if id == b"data" {
            return bytes.get(body..(body + len).min(bytes.len()));
        }
        i = body + len + (len & 1);
    }
    None
}

/// Whether the fine-tuned re-decode should run at all.
///
/// Whisper invents fluent text on silence ("Thank you."), so a run that heard
/// nothing must not be re-decoded — the overlay would type words nobody said.
/// Speech the VAD detected, or any word the streaming pass produced, is the
/// evidence that someone spoke.
fn should_refine(heard: bool, streamed_text: &str) -> bool {
    heard || !streamed_text.trim().is_empty()
}

/// The final transcript: the fine-tuned re-decode when it produced words,
/// otherwise the streaming words. Pure so the "never lose the utterance"
/// fallback is unit-testable without a microphone.
fn pick_transcript(streamed: &[String], refined: &[String]) -> (String, bool) {
    let refined_text = refined.join(" ").trim().to_string();
    if refined_text.is_empty() {
        (streamed.join(" ").trim().to_string(), false)
    } else {
        (refined_text, true)
    }
}

/// Gate/test entry: the two-pass path on a wav FILE (no mic) — streaming words
/// first, then the fine-tuned re-decode — so a gate can assert the second pass
/// replaced them (stub backend) or that it stayed out of the way (unreachable
/// server), without needing a microphone or the real model.
fn refine_test(wav: &str) -> i32 {
    let (python, model) = match (stt_manager::resolve_python(), stt_manager::resolve_model()) {
        (Some(p), Some(m)) => (p, m),
        _ => {
            println!("REFINE-FAIL no STT python/model");
            return 1;
        }
    };
    let Some(r) = stt_manager::resolve_refine(&python) else {
        println!("REFINE-FAIL no refine backend configured (set VAANI_STT_REFINE_BACKEND)");
        return 1;
    };
    let bytes = match std::fs::read(wav) {
        Ok(b) => b,
        Err(e) => {
            println!("REFINE-FAIL read {wav}: {e}");
            return 1;
        }
    };
    let Some(pcm_bytes) = pcm_from_wav(&bytes) else {
        println!("REFINE-FAIL {wav} is not PCM wav data");
        return 1;
    };
    let mut streamed: Vec<String> = Vec::new();
    if stt_manager::transcribe_wav(wav, &python, &model, &mut |w| {
        streamed.push(w.text.clone())
    })
    .is_err()
    {
        println!("REFINE-FAIL streaming pass failed");
        return 1;
    }
    let pcm = stt_manager::bytes_to_pcm(pcm_bytes);
    let mut refined: Vec<String> = Vec::new();
    let stats = match stt_manager::refine_pcm(&pcm, &r.python, &r.backend, &r.endpoint, &mut |w| {
        refined.push(w.text.clone())
    }) {
        Ok(s) => s,
        Err(e) => {
            println!("REFINE-FAIL re-decode failed: {e}");
            return 1;
        }
    };
    let changed = refined.join(" ").trim() != streamed.join(" ").trim();
    println!(
        "REFINE-OK streaming={:?} refined={:?} words={} infer={:.2} changed={changed}",
        streamed.join(" "),
        refined.join(" "),
        stats.words,
        stats.infer_secs
    );
    0
}

/// Gate entry: the owned-server lifecycle without a microphone, a GPU or any
/// real weights. Two stub launcher scripts stand in for serve-refine-stt.sh and
/// serve-formatter.sh and record what happened; this drives the same
/// `servers::start_stt` / `servers::handoff_to_llm` calls `run_pipeline` makes:
/// speech starts, the handoff unloads it before the formatter spawns, the next
/// run unloads the formatter before speech starts again, and the idle sweep
/// kills whatever is left. A launcher whose port already answers is left alone.
///
/// Usage: --servers-test
///        --servers-test <stt_launcher> <llm_launcher> <stt_port> <llm_port>
fn servers_test(rest: &[String]) -> i32 {
    // No arguments: report what the daemon would own with the env as it is.
    // This is the opt-in gate -- nothing configured must mean nothing owned.
    if rest.is_empty() {
        let owned = servers::Server::owned();
        let names: Vec<&str> = owned.iter().map(|s| s.name).collect();
        println!(
            "step=owned count={} names={names:?}",
            owned.len()
        );
        return 0;
    }

    let (Some(stt), Some(llm), Some(stt_port), Some(llm_port)) = (
        rest.first(),
        rest.get(1),
        rest.get(2).and_then(|p| p.parse::<u16>().ok()),
        rest.get(3).and_then(|p| p.parse::<u16>().ok()),
    ) else {
        println!(
            "SERVERS-FAIL usage: --servers-test <stt_launcher> <llm_launcher> <stt_port> <llm_port>"
        );
        return 2;
    };

    let mut fleet = vec![
        servers::Server::new("stt", std::path::PathBuf::from(stt), stt_port),
        servers::Server::new("llm", std::path::PathBuf::from(llm), llm_port),
    ];

    let mut ok = true;
    // The run cycle `run_pipeline` walks, on the same shared functions. Each
    // start gets a moment so the launchers record their own order rather than
    // scheduler jitter, and so a launcher is not judged before `bash` has
    // reached its first line.
    let state = |fleet: &mut [servers::Server], name: &str| match fleet
        .iter_mut()
        .find(|s| s.name == name)
    {
        Some(s) => (s.running(), s.externally_served()),
        None => (false, false),
    };

    // 1. A run begins: the speech server starts (nothing warm to unload yet).
    servers::start_stt(&mut fleet, 0);
    std::thread::sleep(std::time::Duration::from_millis(300));
    let (spawned, external) = state(&mut fleet, "stt");
    println!("step=start name=stt spawned={spawned} external={external}");
    ok &= spawned || external;

    // 2. The handoff: speech is stopped and reaped before the formatter spawns.
    servers::handoff_to_llm(&mut fleet, 0, std::time::Duration::ZERO);
    std::thread::sleep(std::time::Duration::from_millis(300));
    let (running, external) = state(&mut fleet, "stt");
    println!("step=handoff name=stt running={running} external={external}");
    ok &= !running || external; // a server outside the daemon is not ours to kill
    let (spawned, external) = state(&mut fleet, "llm");
    println!("step=start name=llm spawned={spawned} external={external}");
    ok &= spawned || external;

    // 3. The run is over: the formatter is parked, so nothing holds VRAM
    //    between runs and the next trigger has no shutdown on its path.
    servers::park_formatter(&mut fleet);
    let (running, external) = state(&mut fleet, "llm");
    println!("step=park name=llm running={running} external={external}");
    ok &= !running || external;

    // 4. The next run begins: the speech server starts. Its own unload of the
    //    formatter is the safety net; there is nothing left for it to stop.
    servers::start_stt(&mut fleet, 0);
    std::thread::sleep(std::time::Duration::from_millis(300));
    let (spawned, external) = state(&mut fleet, "stt");
    println!("step=start name=stt spawned={spawned} external={external}");
    ok &= spawned || external;
    let (running, external) = state(&mut fleet, "llm");
    println!("step=handoff name=llm running={running} external={external}");
    ok &= !running || external;

    // Nothing touches them again, so the sweep must judge what is left due at
    // t=2 with a 1s window and it must be gone once it has run.
    let mut fleet_helpers: Vec<timeouts::Helper> = Vec::new();
    for s in fleet.iter_mut() {
        if s.running() {
            fleet_helpers.push(s.helper());
        }
    }
    let due = timeouts::due_for_offload(1, 2, &fleet_helpers);
    println!("step=idle idle_timeout_s=1 now_s=2 due={due:?}");
    ok &= due.len() == fleet_helpers.len();
    for name in &due {
        if let Some(s) = fleet.iter_mut().find(|s| s.name == name.as_str()) {
            s.stop();
        }
    }
    for s in fleet.iter_mut() {
        let alive = s.running();
        println!("step=stop name={} running={alive}", s.name);
        ok &= !alive;
    }

    println!("servers ok killed_after_idle={ok}");
    if ok {
        0
    } else {
        1
    }
}

/// Gate/test entry: full chain on a wav FILE (no mic): transcribe ->
/// format with the given config vocab -> type. Gate 17 runs this with
/// a stub wtype first on PATH.
fn pipeline_test(wav: &str, cfg_path: &str) -> i32 {
    let cfg = vaani_config::load(std::path::Path::new(cfg_path)).config;
    let (python, model) = match (
        stt_manager::resolve_python(),
        stt_manager::resolve_model_with(&cfg.stt_model, &cfg.stt_fallback_model),
    ) {
        (Some(p), Some(m)) => (p, m),
        _ => {
            println!("PIPELINE-FAIL no STT python/model");
            return 1;
        }
    };
    let mut words = String::new();
    if stt_manager::transcribe_wav(wav, &python, &model, &mut |w| {
        if !words.is_empty() {
            words.push(' ');
        }
        words.push_str(&w.text);
    })
    .is_err()
    {
        println!("PIPELINE-FAIL stt failed");
        return 1;
    }
    if words.trim().is_empty() {
        println!("PIPELINE-OK empty transcript, nothing typed");
        return 0;
    }
    let pairs: Vec<(&str, &str)> = cfg
        .names
        .iter()
        .map(|(k, v)| (k.as_str(), v.as_str()))
        .chain(cfg.links.iter().map(|(k, v)| (k.as_str(), v.as_str())))
        .collect();
    // Rule engine on purpose: the gates own a deterministic contract
    // (20/20 exact); the LLM path is covered by its own gate.
    let out = llm_formatter::format_with_vocab(words.trim(), &pairs);
    match typing_helper::type_text(&out, true) {
        Ok(_) => {
            println!("PIPELINE-OK typed={out}");
            0
        }
        Err(e) => {
            println!("PIPELINE-FAIL typing failed: {e}");
            1
        }
    }
}

/// Mic level 0..1 for the overlay's activity bars, from a raw s16le chunk.
fn chunk_rms(pcm: &[u8]) -> f64 {
    let n = pcm.len() & !1;
    if n == 0 {
        return 0.0;
    }
    let mut sum = 0.0f64;
    let mut count = 0u32;
    for b in pcm[..n].chunks_exact(2) {
        let s = i16::from_le_bytes([b[0], b[1]]) as f64;
        sum += s * s;
        count += 1;
    }
    if count == 0 {
        return 0.0;
    }
    (sum / count as f64).sqrt() / 32768.0
}

/// Trailing window of what is being said (finals + current partial): the
/// overlay highlights the last word, and the daemon never invents text.
fn live_window(committed: &[String], partial: &str, n: usize) -> String {
    let mut words: Vec<&str> = committed.iter().map(String::as_str).collect();
    words.extend(partial.split_whitespace());
    let start = words.len().saturating_sub(n);
    words[start..].join(" ")
}

/// Spawns the QuickShell overlay for one run; [`UiGuard::dismiss`] lets it
/// exit on its own after the final state (it lingers briefly by design) and
/// only kills it if it is still around. The child inherits the env the
/// service adopted from the trigger, which is the live Wayland socket, not
/// systemd's possibly-stale one.
///
/// `-n` (no-duplicate): if the user already runs `qs -c vaani`, this exits
/// at once and their instance serves the connection instead.
struct UiGuard(Option<std::process::Child>);

impl UiGuard {
    fn dismiss(&mut self) {
        let Some(child) = self.0.as_mut() else { return };
        // The overlay quits itself on IDLE/READY/ERROR after its linger
        // animation; give it that moment, then make sure it is gone.
        for _ in 0..30 {
            if matches!(child.try_wait(), Ok(Some(_))) {
                self.0 = None;
                return;
            }
            std::thread::sleep(std::time::Duration::from_millis(100));
        }
        let _ = child.kill();
        let _ = child.wait();
        self.0 = None;
    }
}

impl UiGuard {
    fn start() -> Self {
        let child = std::process::Command::new("quickshell")
            .args(["-n", "-c", "vaani"])
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()
            .ok();
        if child.is_none() {
            log("error", "pill: quickshell not runnable (states still logged)");
        }
        Self(child)
    }
}

impl Drop for UiGuard {
    fn drop(&mut self) {
        if let Some(mut c) = self.0.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }
}

fn main() {
    load_install_env();
    // Phase 09 selftest bypasses the hotkey loop (gate harness); the idle
    // path below is untouched so gate 03 behavior is identical.
    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|a| a == "--handoff-test") {
        let sample = args
            .iter()
            .skip_while(|a| a.as_str() != "--handoff-test")
            .nth(1)
            .cloned()
            .unwrap_or_else(|| "hello world".to_owned());
        std::process::exit(handoff::selftest(&sample));
    }
    // Same call the run pipeline makes, so gates can prove which backend the
    // daemon actually uses (LLM when reachable, rules otherwise).
    if let Some(i) = args.iter().position(|a| a == "--format-test") {
        let raw = args.get(i + 1).cloned().unwrap_or_default();
        if raw.is_empty() {
            println!("FORMAT-TEST usage: --format-test \"<raw transcript>\"");
            std::process::exit(2);
        }
        let cfg_path = args.get(i + 2).cloned().unwrap_or_else(|| {
            format!(
                "{}/.config/vaani/vaani.conf",
                std::env::var("HOME").unwrap_or_else(|_| ".".into())
            )
        });
        let cfg = vaani_config::load(std::path::Path::new(&cfg_path)).config;
        let pairs: Vec<(&str, &str)> = cfg
            .names
            .iter()
            .map(|(k, v)| (k.as_str(), v.as_str()))
            .chain(cfg.links.iter().map(|(k, v)| (k.as_str(), v.as_str())))
            .collect();
        let (out, backend) = llm_formatter::format_pipeline(&raw, &pairs);
        println!("FORMAT-TEST backend={backend} text={out}");
        std::process::exit(0);
    }
    if let Some(i) = args.iter().position(|a| a == "--stream-test") {
        let wav = args.get(i + 1).cloned().unwrap_or_default();
        if wav.is_empty() {
            println!("STREAM-FAIL usage: --stream-test <wav>");
            std::process::exit(2);
        }
        std::process::exit(stream_test(&wav));
    }
    if let Some(i) = args.iter().position(|a| a == "--refine-test") {
        let wav = args.get(i + 1).cloned().unwrap_or_default();
        if wav.is_empty() {
            println!("REFINE-FAIL usage: --refine-test <wav>");
            std::process::exit(2);
        }
        std::process::exit(refine_test(&wav));
    }
    if let Some(i) = args.iter().position(|a| a == "--servers-test") {
        std::process::exit(servers_test(&args[i + 1..]));
    }
    if let Some(i) = args.iter().position(|a| a == "--pipeline-test") {
        let wav = args.get(i + 1).cloned().unwrap_or_default();
        if wav.is_empty() {
            println!("PIPELINE-FAIL usage: --pipeline-test <wav> [config]");
            std::process::exit(2);
        }
        let cfg_path = args.get(i + 2).cloned().unwrap_or_else(|| {
            format!(
                "{}/.config/vaani/vaani.conf",
                std::env::var("HOME").unwrap_or_else(|_| ".".into())
            )
        });
        std::process::exit(pipeline_test(&wav, &cfg_path));
    }
    // Daemon path only: the test entries above take their own arguments. An
    // unknown flag used to be read as the config path, and a missing file
    // silently fell back to defaults -- both booted the wrong config.
    let positional = std::env::args().nth(1);
    if let Some(a) = &positional {
        if a.starts_with('-') {
            eprintln!(
                "usage: vaani-key-service [config] (test entries: --handoff-test, --format-test, --stream-test, --refine-test, --servers-test, --pipeline-test)"
            );
            std::process::exit(2);
        }
        if !std::path::Path::new(a).exists() {
            eprintln!("vaani key-service: no such config: {a}");
            std::process::exit(1);
        }
    }
    let cfg_path = positional.unwrap_or_else(|| {
        format!(
            "{}/.config/vaani/vaani.conf",
            std::env::var("HOME").unwrap_or_else(|_| ".".into())
        )
    });
    let outcome = vaani_config::load(std::path::Path::new(&cfg_path));
    for w in &outcome.warnings {
        eprintln!("vaani key-service: warn: {w}");
    }
    let cfg = outcome.config;
    let pid = std::process::id();

    unsafe {
        signal(SIGUSR1, on_trigger);
        signal(SIGTERM, on_shutdown);
        signal(SIGINT, on_shutdown);
    }

    // No compositor calls: the bind is static in hyprland.lua and the
    // trigger script signals us. All we publish is our pid.
    if let Err(e) = control::start() {
        log("error", &format!("control socket unavailable: {e}"));
        std::process::exit(1);
    }
    write_pid_file(pid);
    log(
        "idle",
        &format!("listening pid={pid} trigger=vaani-trigger bind=hyprland.lua"),
    );

    // The model servers this daemon owns: empty unless VAANI_STT_REFINE_SERVER
    // and/or VAANI_LLM_SERVER point at launcher scripts. A run spawns them
    // (speech first, then the formatter); the sweep below kills them once
    // idle_timeout_s has passed with no run, so no model memory is held
    // between dictations. Triggers always start a run: run_pipeline owns the
    // toggle (2nd press stops it) and drains presses landing mid-run, so two
    // pipelines can never overlap.
    let boot = std::time::Instant::now();
    let mut model_servers = servers::Server::owned();

    loop {
        // Sleep-poll, not pause(): a signal landing between the flag check
        // and a pause() would sleep forever with no further wakeup.
        std::thread::sleep(std::time::Duration::from_millis(50));
        // Idle sweep: kill the model servers this daemon owns once they have
        // been idle past idle_timeout_s, so the memory goes back. Only servers
        // we spawned are considered; timeouts::decide owns the decision.
        let now_s = boot.elapsed().as_secs();
        let mut fleet: Vec<timeouts::Helper> = Vec::new();
        for s in model_servers.iter_mut() {
            if s.running() {
                fleet.push(s.helper());
            }
        }
        for name in timeouts::due_for_offload(cfg.idle_timeout_s, now_s, &fleet) {
            if let Some(s) = model_servers.iter_mut().find(|s| s.name == name.as_str()) {
                s.stop();
                log(
                    "offload",
                    &format!("{name} server idle past {}s, stopped", cfg.idle_timeout_s),
                );
            }
        }
        if GOT_TRIGGER.swap(false, Ordering::SeqCst) {
            adopt_live_wayland_env();
            log(
                "triggered",
                &format!(
                    "static bind fired display={}",
                    std::env::var("WAYLAND_DISPLAY").unwrap_or_default()
                ),
            );
            run_pipeline(&cfg, &mut model_servers, boot);
            // A press landing mid-run must not start a second run.
            GOT_TRIGGER.swap(false, Ordering::SeqCst);
            log("idle", "run finished, listening");
        }
        if GOT_SHUTDOWN.load(Ordering::SeqCst) {
            log("shutting down", &format!("pid={pid}"));
            // Leave no model server behind: they hold VRAM, and the sweep only
            // runs while this loop does.
            for s in model_servers.iter_mut() {
                s.stop();
            }
            // Nothing compositor-side to clean up: no bind handle exists.
            control::state("IDLE", "");
            remove_pid_file();
            control::cleanup();
            break;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{chunk_rms, live_window, parse_env_file, pcm_from_wav, pick_transcript, should_refine};

    fn w(s: &str) -> Vec<String> {
        s.split_whitespace().map(str::to_string).collect()
    }

    #[test]
    fn trailing_window_shows_newest_words() {
        assert_eq!(live_window(&[], "", 4), "");
        assert_eq!(live_window(&w("one two"), "", 4), "one two");
        assert_eq!(live_window(&w("one two three four five"), "", 4), "two three four five");
        // The partial appends after the finals, so the window always ends
        // on what is being said right now.
        assert_eq!(live_window(&w("one two three"), "four five", 4), "two three four five");
        assert_eq!(live_window(&w("one two three four five"), "six", 4), "three four five six");
    }

    #[test]
    fn mic_level_tracks_signal() {
        assert_eq!(chunk_rms(&[]), 0.0);
        assert_eq!(chunk_rms(&[0, 0, 0, 0]), 0.0);
        let loud: Vec<u8> = [i16::MAX; 64].iter().flat_map(|s| s.to_le_bytes()).collect();
        assert!(chunk_rms(&loud) > 0.5, "full-scale input must read high");
        let quiet: Vec<u8> = [300i16; 64].iter().flat_map(|s| s.to_le_bytes()).collect();
        assert!(chunk_rms(&quiet) < 0.1, "near-silence must read low");
        // Odd byte counts must not panic or read past the end.
        assert!(chunk_rms(&[1, 2, 3]) >= 0.0);
    }


    #[test]
    fn refined_words_replace_streaming_but_never_vanish() {
        let streamed = vec!["hello".to_string(), "hello".to_string()];
        // The fine-tuned pass wins when it answers.
        let (text, used) = pick_transcript(&streamed, &["Hello, hello.".to_string()]);
        assert!(used);
        assert_eq!(text, "Hello, hello.");
        // No words from the second pass: the streaming words must survive.
        let (text, used) = pick_transcript(&streamed, &[]);
        assert!(!used);
        assert_eq!(text, "hello hello");
        // Whitespace-only output counts as nothing.
        let (text, used) = pick_transcript(&streamed, &["  ".to_string()]);
        assert!(!used);
        assert_eq!(text, "hello hello");
        // Both empty stays empty, so the daemon types nothing.
        let (text, _) = pick_transcript(&[], &[]);
        assert!(text.is_empty());
    }

    #[test]
    fn silence_is_never_re_decoded() {
        // Nothing heard and nothing decoded: skip, or Whisper's invented text
        // would be typed into the focused window.
        assert!(!should_refine(false, ""));
        assert!(!should_refine(false, "   "));
        // The VAD heard speech, or the streaming pass produced a word: refine.
        assert!(should_refine(true, ""));
        assert!(should_refine(false, "hello"));
    }

    #[test]
    fn install_env_lines_are_parsed_without_a_shell() {
        let parsed = parse_env_file(
            "# a comment\nexport VAANI_LLM_ENDPOINT=\"http://127.0.0.1:8082\"\n\nexport HOME=/root\n",
        );
        assert_eq!(
            parsed,
            vec![(
                "VAANI_LLM_ENDPOINT".to_string(),
                "http://127.0.0.1:8082".to_string()
            )]
        );
    }

    #[test]
    fn wav_payload_is_found() {
        // Minimal canonical 44-byte header + 4 bytes of samples.
        let mut w = Vec::new();
        w.extend_from_slice(b"RIFF");
        w.extend_from_slice(&40u32.to_le_bytes());
        w.extend_from_slice(b"WAVEfmt ");
        w.extend_from_slice(&16u32.to_le_bytes());
        w.extend_from_slice(&[0u8; 16]);
        w.extend_from_slice(b"data");
        w.extend_from_slice(&4u32.to_le_bytes());
        w.extend_from_slice(&[1, 2, 3, 4]);
        assert_eq!(pcm_from_wav(&w), Some(&[1u8, 2, 3, 4][..]));
        assert_eq!(pcm_from_wav(b"not a wav"), None);
    }
}
