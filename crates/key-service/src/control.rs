//! Control socket for the Vaani Quickshell overlay (quickshell config
//! "vaani", see UI/quickshell/README-upstream.md).
//!
//! Wire format is newline-delimited JSON, both directions:
//!   daemon -> UI: first line per connection is a *snapshot* carrying
//!     `state` (the overlay quits at once if it is IDLE/CANCELLED and the
//!     message is not an event); after that `state` / `provisional` /
//!     `amplitude` events, and `{ok, request_id}` responses to ops.
//!   UI -> daemon: `{protocol_version, request_id, session_id, kind:{op}}`;
//!     the only op implemented is `stop` (= cancel this run; nothing is typed).
//!
//! States are the overlay's vocabulary: STARTING, RECORDING, TRANSCRIBING,
//! CLEANING, INSERTING, READY, IDLE, CANCELLED, ERROR.
//!
//! One client at a time: a newly connected overlay replaces the old one, so
//! a stale window can never hold the socket.

use std::io::{BufRead, BufReader, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

static CLIENT: Mutex<Option<UnixStream>> = Mutex::new(None);
/// Last published state: replayed as the snapshot for a fresh connection.
static STATE: Mutex<Option<String>> = Mutex::new(None);
static STOP: AtomicBool = AtomicBool::new(false);

/// `$XDG_RUNTIME_DIR/vaani/control.sock`, matching the overlay's default.
pub fn sock_path() -> PathBuf {
    let base = std::env::var("XDG_RUNTIME_DIR").unwrap_or_else(|_| "/tmp".into());
    PathBuf::from(base).join("vaani/control.sock")
}

/// Escape a JSON string body (values here are our own words/status text,
/// but they can still contain quotes or backslashes).
fn esc(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

fn send(line: &str) {
    let mut guard = match CLIENT.lock() {
        Ok(g) => g,
        Err(_) => return,
    };
    let Some(stream) = guard.as_mut() else {
        return; // no overlay connected: state still advances, nothing to tell
    };
    let ok = stream.write_all(line.as_bytes()).is_ok() && stream.write_all(b"\n").is_ok();
    if ok {
        let _ = stream.flush();
    } else {
        *guard = None; // dead client: drop it, next connect replaces
    }
}

/// Bind the socket and serve connections in a background thread.
/// Returns the path so the caller can log/clean it up.
pub fn start() -> std::io::Result<PathBuf> {
    let path = sock_path();
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
        // The fallback is /tmp, so the directory must be private.
        std::fs::set_permissions(dir, std::fs::Permissions::from_mode(0o700))?;
    }
    // Do not unlink a live daemon's socket. A stale file (connect refused) is
    // removed and rebound; a live one is an error that stops the second daemon.
    let listener = match UnixListener::bind(&path) {
        Ok(l) => l,
        Err(e) if e.kind() == std::io::ErrorKind::AddrInUse => {
            if UnixStream::connect(&path).is_ok() {
                return Err(e);
            }
            std::fs::remove_file(&path)?;
            UnixListener::bind(&path)?
        }
        Err(e) => return Err(e),
    };
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
    std::thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(stream) = stream else { continue };
            adopt(stream);
        }
    });
    Ok(path)
}

/// The op a UI line asks for. The wire format is one JSON object per line; this
/// reads only the `kind.op` value, so an unknown op (or a line that is not the
/// protocol at all) never matches.
fn op_of(line: &str) -> Option<&str> {
    let (_, rest) = line.split_once("\"op\"")?;
    let rest = rest.trim_start().strip_prefix(':')?.trim_start();
    rest.strip_prefix('"')?.split('"').next()
}

/// The only op the daemon implements: cancel the current run.
fn is_stop(line: &str) -> bool {
    op_of(line) == Some("stop")
}

/// Take over as the live client: send the snapshot, then read ops until the
/// peer goes away.
fn adopt(stream: UnixStream) {
    let snapshot_state = STATE
        .lock()
        .ok()
        .and_then(|g| g.clone())
        .unwrap_or_else(|| "IDLE".to_string());
    let mut writer = match stream.try_clone() {
        Ok(w) => w,
        Err(_) => return,
    };
    // A frozen overlay must not block the dictation thread on a full socket.
    let _ = writer.set_write_timeout(Some(Duration::from_millis(50)));
    let snap = format!(
        "{{\"protocol_version\":1,\"session_id\":\"{}\",\"state\":\"{}\"}}",
        esc(&session()),
        esc(&snapshot_state)
    );
    if writer
        .write_all(format!("{snap}\n").as_bytes())
        .and_then(|_| writer.flush())
        .is_err()
    {
        return;
    }
    if let Ok(mut guard) = CLIENT.lock() {
        *guard = Some(writer);
    }
    // Ops from the UI. Only `stop` exists today; parse it without pulling in
    // a JSON dependency (the UI sends one small object per line).
    let reader = BufReader::new(stream);
    for line in reader.lines() {
        let Ok(line) = line else { break };
        if is_stop(&line) {
            STOP.store(true, Ordering::SeqCst);
        }
    }
    if let Ok(mut guard) = CLIENT.lock() {
        *guard = None;
    }
}

/// Current session id: the overlay ignores events from other sessions.
fn session() -> String {
    format!("s{}", std::process::id())
}

fn publish(body: &str) {
    let sid = esc(&session());
    send(&format!("{{\"session_id\":\"{sid}\",{body}}}"));
}

/// A state transition (drives the overlay's label and lifetime).
pub fn state(state: &str, message: &str) {
    if let Ok(mut guard) = STATE.lock() {
        *guard = Some(state.to_string());
    }
    let (s, m) = (esc(state), esc(message));
    publish(&format!("\"event\":\"state\",\"state\":\"{s}\",\"message\":\"{m}\""));
}

/// Final answer for the overlay to show: the text, and whether it is on the
/// clipboard (which makes the overlay linger longer before it exits).
pub fn state_with_text(state: &str, message: &str, text: &str, copied: bool) {
    if let Ok(mut guard) = STATE.lock() {
        *guard = Some(state.to_string());
    }
    let (s, m, t) = (esc(state), esc(message), esc(text));
    publish(&format!(
        "\"event\":\"state\",\"state\":\"{s}\",\"message\":\"{m}\",\"data\":{{\"text\":\"{t}\",\"copied\":{copied}}}"
    ));
}

/// Live words while recording (`words` is the trailing window; the overlay
/// highlights the last word).
pub fn provisional(words: &str, hidden: bool) {
    let w = esc(words);
    publish(&format!(
        "\"event\":\"provisional\",\"data\":{{\"tail\":\"{w}\",\"words\":\"{w}\",\"hidden\":{hidden}}}"
    ));
}

/// Mic level 0..1 for the activity bars (published per audio chunk).
pub fn amplitude(a: f64) {
    publish(&format!("\"event\":\"amplitude\",\"amplitude\":{:.3}", a.clamp(0.0, 1.0)));
}

/// True once the UI asked to stop the current run.
pub fn take_stop() -> bool {
    STOP.swap(false, Ordering::SeqCst)
}

/// Non-consuming peek: a long wait polls this and bails out, leaving the flag
/// for the caller to take and publish CANCELLED.
pub fn stop_pending() -> bool {
    STOP.load(Ordering::SeqCst)
}

/// Drop a stop left over from a previous run or an idle client.
pub fn reset_stop() {
    STOP.store(false, Ordering::SeqCst);
}

/// Remove the socket file (shutdown).
pub fn cleanup() {
    let _ = std::fs::remove_file(sock_path());
}

#[cfg(test)]
mod tests {
    use super::is_stop;

    #[test]
    fn stop_op_is_recognised() {
        assert!(is_stop(
            r#"{"protocol_version":1,"request_id":"qml-1","session_id":null,"kind":{"op":"stop"}}"#
        ));
        // The reader strips the newline; the parser must not depend on it.
        assert!(is_stop("{\"kind\":{\"op\":\"stop\"}}\n"));
    }

    #[test]
    fn unknown_ops_do_not_cancel() {
        assert!(!is_stop(r#"{"kind":{"op":"config_get"}}"#));
        // "stop" elsewhere in the object is not the op.
        assert!(!is_stop(
            r#"{"request_id":"stop-1","kind":{"op":"config_get"}}"#
        ));
        assert!(!is_stop(r#"{"kind":{"op":"stopplease"}}"#));
    }

    #[test]
    fn malformed_lines_do_not_cancel() {
        assert!(!is_stop(""));
        assert!(!is_stop("not json"));
        assert!(!is_stop(r#"{"kind":{"op":}}"#));
        assert!(!is_stop(r#"{"kind":{"op"}}"#));
    }
}
