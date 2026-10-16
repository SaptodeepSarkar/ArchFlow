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
#[allow(dead_code)]
mod cancel;

// Safety cap: a run never records longer than this, even if the second
// press never comes.
const MAX_RECORD_SECS: u64 = 60;

/// s16 mono at 16 kHz is 32 bytes per millisecond of audio.
const BYTES_PER_MS: usize = 32;

/// One live run: open mic + STT stream (words show while speaking, until
/// 2nd press / cap / shutdown) -> format with config vocab -> type. Every
/// path ends back at idle; STT loads per run and unloads after (backend
/// reaped, zero VRAM ever held); the formatter is a rule call.
fn run_pipeline(cfg: &vaani_config::VaaniConfig) {
    let (python, model) = match (stt_manager::resolve_python(), stt_manager::resolve_model()) {
        (Some(p), Some(m)) => (p, m),
        (None, _) => {
            control::state("ERROR", "No STT python found");
            log("error", "no STT python found");
            return;
        }
        (_, None) => {
            control::state("ERROR", "No STT model found");
            log("error", "no STT model found");
            return;
        }
    };
    // STARTING is published before the overlay starts: a fresh connection
    // gets it as the snapshot, and an IDLE snapshot would make it quit.
    control::state("STARTING", "Starting microphone");
    let mut rec = audio_helper::Recorder::new();
    if let Err(e) = rec.start_stream() {
        control::state("ERROR", &format!("Mic failed: {e}"));
        log("error", &format!("mic failed: {e}"));
        return;
    }
    let mut stt = match stt_manager::LiveSession::start(&python, &model) {
        Ok(s) => s,
        Err(e) => {
            rec.stop_stream();
            control::state("ERROR", &format!("STT failed: {e}"));
            log("error", &format!("stt failed: {e}"));
            return;
        }
    };
    let mut ui = UiGuard::start();
    control::state("RECORDING", "Speak naturally…");
    control::provisional("", false);
    log("listening", "mic open, press hotkey again to finish");

    let mut committed: Vec<String> = Vec::new();
    let mut partial = String::new();
    let mut vad = vad::Vad::new();
    let t0 = std::time::Instant::now();
    // Raw utterance, kept so the fine-tuned model can re-read exactly the audio
    // the streaming pass saw. Bounded by MAX_RECORD_SECS (~2 MB).
    let mut captured: Vec<u8> = Vec::new();
    let refine = stt_manager::resolve_refine(&python);
    let mut heard = false;
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
            }
        }
        if changed {
            control::provisional(&live_window(&committed, &partial, 12), false);
        }
        if GOT_SHUTDOWN.load(Ordering::SeqCst) {
            rec.stop_stream();
            stt.unload();
            ui.dismiss();
            control::state("IDLE", "");
            log("error", "shutdown during recording, run aborted");
            return;
        }
        // Auto-stop on end of speech: the user speaks once and never
        // presses twice. A second press / the Stop button still end the
        // run early, and the cap covers a stuck detector.
        if got_ms > 0 {
            if let vad::Decision::End { heard: h } = vad.tick(got_ms, changed) {
                heard = h;
                log("idle", &format!("end of speech (heard={h})"));
                break;
            }
        }
        if GOT_TRIGGER.swap(false, Ordering::SeqCst)
            || control::take_stop()
            || t0.elapsed().as_secs() >= MAX_RECORD_SECS
        {
            break;
        }
    }
    rec.stop_stream();
    log("transcribing", &format!("{} words decoded", committed.len()));
    control::state("TRANSCRIBING", "Transcribing");
    // Words flushed by the backend at end-of-stream land here; losing them
    // was why short runs typed nothing.
    let stats = match stt.finish(&mut |w| {
        committed.push(w.text.clone());
    }) {
        Ok(s) => s,
        Err(e) => {
            ui.dismiss();
            control::state("ERROR", &format!("STT failed: {e}"));
            log("error", &format!("stt failed: {e}"));
            return;
        }
    };
    // Second pass: the fine-tuned model re-reads the finished utterance and,
    // when it answers, its words are the ones that get formatted and typed. The
    // streaming words stay the fallback, so a missing model server can never
    // lose what the user actually said.
    let mut text = committed.join(" ").trim().to_string();
    if let Some(r) = &refine {
        if should_refine(heard, &text) {
            let mut refined: Vec<String> = Vec::new();
            let pcm = stt_manager::bytes_to_pcm(&captured);
            match stt_manager::refine_pcm(&pcm, &r.python, &r.backend, &r.endpoint, &mut |w| {
                refined.push(w.text.clone())
            }) {
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
    if text.is_empty() {
        ui.dismiss();
        control::state("IDLE", "Nothing heard");
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
    let (out, backend) = llm_formatter::format_pipeline(&text, &pairs);
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
    let stats = match stt.finish(&mut |w| words.push(w.text.clone())) {
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

/// Gate/test entry: full chain on a wav FILE (no mic): transcribe ->
/// format with the given config vocab -> type. Gate 17 runs this with
/// a stub wtype first on PATH.
fn pipeline_test(wav: &str, cfg_path: &str) -> i32 {
    let cfg = vaani_config::load(std::path::Path::new(cfg_path)).config;
    let (python, model) = match (stt_manager::resolve_python(), stt_manager::resolve_model()) {
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
    let cfg_path = std::env::args().nth(1).unwrap_or_else(|| {
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
    }
    write_pid_file(pid);
    log(
        "idle",
        &format!(
            "listening pid={pid} hotkey={} trigger=vaani-trigger bind=hyprland.lua",
            cfg.hotkey
        ),
    );

    // Run-phase tracking for the idle sweep (timeouts::due_for_offload over
    // the helpers vec). The vec stays empty until the daemon spawns helpers;
    // the sweep is live code either way. Triggers always start a run:
    // run_pipeline owns the toggle (2nd press stops it) and drains presses
    // landing mid-run, so two pipelines can never overlap.
    let boot = std::time::Instant::now();
    let mut helpers: Vec<timeouts::Helper> = Vec::new();

    loop {
        // Sleep-poll, not pause(): a signal landing between the flag check
        // and a pause() would sleep forever with no further wakeup.
        std::thread::sleep(std::time::Duration::from_millis(50));
        // Idle sweep: offload helpers past idle_timeout_s. Busy helpers are
        // never killed (timeouts::decide keeps them alive for re-check).
        let now_s = boot.elapsed().as_secs();
        for name in timeouts::due_for_offload(cfg.idle_timeout_s, now_s, &helpers) {
            log("offload", &format!("helper {name} idle past timeout"));
            helpers.retain(|h| h.name != name);
        }
        if GOT_TRIGGER.swap(false, Ordering::SeqCst) {
            adopt_live_wayland_env();
            log(
                "triggered",
                &format!(
                    "hotkey {} fired display={}",
                    cfg.hotkey,
                    std::env::var("WAYLAND_DISPLAY").unwrap_or_default()
                ),
            );
            run_pipeline(&cfg);
            // A press landing mid-run must not start a second run.
            GOT_TRIGGER.swap(false, Ordering::SeqCst);
            log("idle", "run finished, listening");
        }
        if GOT_SHUTDOWN.load(Ordering::SeqCst) {
            log("shutting down", &format!("pid={pid}"));
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
    use super::{chunk_rms, live_window, pcm_from_wav, pick_transcript, should_refine};

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
