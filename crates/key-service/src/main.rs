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

fn main() {
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
