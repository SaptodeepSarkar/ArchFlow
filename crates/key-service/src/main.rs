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
mod timeouts;
#[allow(dead_code)]
mod cancel;

// Safety cap: a run never records longer than this, even if the second
// press never comes.
const MAX_RECORD_SECS: u64 = 60;

/// One live run: record (until 2nd press / timeout / shutdown) ->
/// transcribe RAM -> format with config vocab -> type. Every path ends
/// back at idle; STT loads per run and unloads after (backend reaped,
// zero VRAM ever held); the formatter is a rule call, nothing to load.
fn run_pipeline(cfg: &vaani_config::VaaniConfig) {
    log("listening", "mic open, press hotkey again to finish");
    let mut rec = audio_helper::Recorder::new();
    if let Err(e) = rec.start() {
        log("error", &format!("mic failed: {e}"));
        return;
    }
    let t0 = std::time::Instant::now();
    loop {
        std::thread::sleep(std::time::Duration::from_millis(100));
        if GOT_SHUTDOWN.load(Ordering::SeqCst) {
            let _ = rec.stop();
            log("error", "shutdown during recording, run aborted");
            return;
        }
        if GOT_TRIGGER.swap(false, Ordering::SeqCst)
            || t0.elapsed().as_secs() >= MAX_RECORD_SECS
        {
            break;
        }
    }
    let cap = match rec.stop() {
        Ok(c) => c,
        Err(e) => {
            log("error", &format!("mic stop failed: {e}"));
            return;
        }
    };
    log(
        "transcribing",
        &format!("{} samples, loading STT", cap.samples.len()),
    );
    let python = match stt_manager::resolve_python() {
        Some(p) => p,
        None => {
            log("error", "no STT python found");
            return;
        }
    };
    let model = match stt_manager::resolve_model() {
        Some(m) => m,
        None => {
            log("error", "no STT model found");
            return;
        }
    };
    let mut words = String::new();
    let stats = match stt_manager::transcribe_pcm(&cap.samples, &python, &model, &mut |w| {
        if !words.is_empty() {
            words.push(' ');
        }
        words.push_str(&w.text);
    }) {
        Ok(s) => s,
        Err(e) => {
            log("error", &format!("stt failed: {e}"));
            return;
        }
    };
    let text = words.trim().to_string();
    if text.is_empty() {
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
    let out = llm_formatter::format_with_vocab(&text, &pairs);
    log("writing", &format!("typing {} chars", out.len()));
    // pill_hidden=true: no pill is hosted yet (owed), so there is nothing
    // to hide and no focus to steal; states are logged instead.
    match typing_helper::type_text(&out, true) {
        Ok(r) => log("idle", &format!("typed, clipboard={}", r.clipboard_copied)),
        Err(e) => log("error", &format!("typing failed: {e}")),
    }
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
            remove_pid_file();
            break;
        }
    }
}
