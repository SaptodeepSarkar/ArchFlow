//! Wayland clipboard via `wl-copy` / `wl-paste` (stdin/structured buffers,
//! never shell interpolation or argv text). Plain-text selection only, bounded
//! serving period. Restoration limited to a bounded plain-text snapshot and
//! only if the clipboard still belongs to this operation.

use std::io::Write;
use std::process::{Command, Stdio};

/// Place UTF-8 plain text on the Wayland clipboard. Returns Ok when wl-copy
/// accepted the offer (ownership, NOT proof the target pasted it).
pub fn offer_text(text: &str) -> anyhow::Result<()> {
    let mut child = Command::new("wl-copy")
        .arg("--type")
        .arg("text/plain;charset=utf-8")
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| anyhow::anyhow!("wl-copy spawn failed: {e}"))?;
    child
        .stdin
        .take()
        .expect("piped")
        .write_all(text.as_bytes())?;
    let out = child.wait_with_output()?;
    if !out.status.success() {
        anyhow::bail!(
            "wl-copy failed: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }
    Ok(())
}

/// Snapshot current plain-text clipboard (bounded 64 KiB), if any.
pub fn snapshot_text() -> Option<String> {
    let out = Command::new("wl-paste")
        .arg("--no-newline")
        .arg("--type")
        .arg("text/plain")
        .output()
        .ok()?;
    if !out.status.success() || out.stdout.is_empty() {
        return None;
    }
    let mut s = String::from_utf8(out.stdout).ok()?;
    let mut boundary = s.len().min(64 * 1024);
    while !s.is_char_boundary(boundary) { boundary -= 1; }
    s.truncate(boundary);
    Some(s)
}

/// Best-effort check: does the clipboard still contain exactly our text?
/// (Clipboard managers may read the offer first — a match is ownership
/// evidence, a mismatch is NOT proof of consumption.)
pub fn still_ours(text: &str) -> bool {
    match snapshot_text() {
        Some(cur) => cur == text,
        None => false,
    }
}

/// Clear only if still ours; never clobber user-copied content.
pub fn clear_if_ours(text: &str) {
    if still_ours(text) {
        let _ = Command::new("wl-copy").arg("--clear").output();
    }
}
