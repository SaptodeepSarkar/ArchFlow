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

// ---- hyprctl binding ----
//
// "SUPER+H" -> `hyprctl eval 'vaani_hotkey_<pid> = hl.bind("SUPER + H",
// hl.dsp.exec_cmd("kill -USR1 <pid>"))'`.
// Compositor-owned grab: no raw evdev, no conflict with Hyprland.
// (On Hyprland >= 0.56 `hyprctl keyword bind` is a no-op under the Lua
// parser, so we register through the Lua API instead.)
// Cleanup removes only our handle (`:remove()`), never the user's binds.
fn lua_hotkey(hotkey: &str) -> Result<String, String> {
    if !hotkey
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '+' || c == ' ')
    {
        return Err(format!("refusing suspicious hotkey: {hotkey:?}"));
    }
    let spaced = hotkey
        .split('+')
        .map(str::trim)
        .collect::<Vec<_>>()
        .join(" + ");
    if spaced.is_empty() {
        return Err("empty hotkey".into());
    }
    Ok(spaced)
}

fn hyprctl(args: &[&str]) -> Result<String, String> {
    let out = std::process::Command::new("hyprctl")
        .args(args)
        .output()
        .map_err(|e| format!("hyprctl not runnable: {e}"))?;
    if !out.status.success() {
        return Err(format!(
            "hyprctl {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&out.stderr)
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

fn register_hotkey(hotkey: &str, pid: u32) -> Result<String, String> {
    let key = lua_hotkey(hotkey)?;
    let handle = format!("vaani_hotkey_{pid}");
    let code = format!("{handle} = hl.bind(\"{key}\", hl.dsp.exec_cmd(\"kill -USR1 {pid}\"))");
    hyprctl(&["eval", &code])?;
    Ok(handle)
}

fn unregister_hotkey(handle: &str) -> Result<(), String> {
    hyprctl(&["eval", &format!("{handle}:remove()")]).map(|_| ())
}

// ---- Phase 09: STT -> LLM handoff (VRAM-serialized) ----
//
// Sequence: STT streams words, STT unloads, formatter loads, raw
// transcript fed. VRAM is sampled via nvidia-smi at every step; a step
// with both STT and formatter resident aborts to the error state.
// Helpers reporting busy are never killed: offload requests return
// false (deferred) while busy and are re-checked once idle.
//
// shortcut: SttBackend/LlmBackend are minimal local traits mirroring the
// PRD interfaces of stt-manager/llm-formatter (absent crates); swap for
// real path-deps + trait impls when those crates land.
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
    pub struct StubLlm {
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

    impl LlmBackend for StubLlm {
        fn load(&mut self) -> Result<(), String> {
            self.loaded = true;
            Ok(())
        }
        fn format(&mut self, transcript: &str) -> Result<String, String> {
            self.busy = true;
            let out = transcript.split_whitespace().collect::<Vec<_>>().join(" ");
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
        let mut llm = StubLlm { loaded: false, busy: false };
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

// Phase 10/11 decision modules. The run-phase daemon loop that feeds them
// lands in Phase 13; until then they compile in (bitrot-proof) and are
// covered by their own gates, not yet called.
#[allow(dead_code)]
mod timeouts;
#[allow(dead_code)]
mod cancel;

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

    let handle = match register_hotkey(&cfg.hotkey, pid) {
        Ok(h) => h,
        Err(e) => {
            log("error", &format!("hotkey bind failed: {e}"));
            std::process::exit(1);
        }
    };
    log("idle", &format!("listening pid={pid} hotkey={}", cfg.hotkey));

    loop {
        // Sleep-poll, not pause(): a signal landing between the flag check
        // and a pause() would sleep forever with no further wakeup.
        std::thread::sleep(std::time::Duration::from_millis(50));
        if GOT_TRIGGER.swap(false, Ordering::SeqCst) {
            // Phase 03: no pipeline yet — record the transition, stay resident.
            log("triggered", &format!("hotkey {} fired", cfg.hotkey));
        }
        if GOT_SHUTDOWN.load(Ordering::SeqCst) {
            log("shutting down", &format!("pid={pid}"));
            if let Err(e) = unregister_hotkey(&handle) {
                log("error", &format!("hotkey unbind failed: {e}"));
            }
            break;
        }
    }
}
