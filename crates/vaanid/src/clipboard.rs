//! Wayland clipboard via `wl-copy` / `wl-paste` (stdin/structured buffers,
//! never shell interpolation or argv text). Plain-text selection only, bounded
//! serving period. Restoration limited to a bounded plain-text snapshot and
//! only if the clipboard still belongs to this operation.

use std::io::Write;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

/// Run a short helper with a hard deadline. Clipboard/dispatch helpers must
/// never wedge the controller: a hung wl-copy/wl-paste/wtype/hyprctl used to
/// park sessions in INSERTING forever, deaf to Super+H. On expiry the child
/// is killed and an error is returned so the caller falls back to copy-only.
///
/// `capture` reads stdout/stderr on success. It must be false for helpers
/// that daemonize (wl-copy forks a clipboard server inheriting its fds:
/// draining those pipes blocks until the server exits, i.e. nearly forever).
pub fn run_timeout(
    mut cmd: Command,
    input: Option<&[u8]>,
    secs: u64,
    capture: bool,
) -> anyhow::Result<std::process::Output> {
    let mut child = cmd
        .stdin(if input.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(if capture {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stderr(if capture {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .spawn()
        .map_err(|e| anyhow::anyhow!("spawn failed: {e}"))?;
    if let Some(data) = input {
        if let Some(mut stdin) = child.stdin.take() {
            let _ = stdin.write_all(data);
        }
        // stdin dropped here -> EOF so wl-copy can proceed to fork/serve.
    }
    let deadline = Instant::now() + Duration::from_secs(secs);
    loop {
        match child
            .try_wait()
            .map_err(|e| anyhow::anyhow!("wait failed: {e}"))?
        {
            Some(status) => {
                if capture {
                    return child
                        .wait_with_output()
                        .map_err(|e| anyhow::anyhow!("output failed: {e}"));
                }
                return Ok(std::process::Output {
                    status,
                    stdout: Vec::new(),
                    stderr: Vec::new(),
                });
            }
            None if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                anyhow::bail!("helper timed out after {secs}s");
            }
            None => std::thread::sleep(Duration::from_millis(25)),
        }
    }
}

/// Place UTF-8 plain text on the Wayland clipboard. Returns Ok when wl-copy
/// accepted the offer (ownership, NOT proof the target pasted it).
pub fn offer_text(text: &str) -> anyhow::Result<()> {
    let mut cmd = Command::new("wl-copy");
    cmd.arg("--type").arg("text/plain;charset=utf-8");
    let out = run_timeout(cmd, Some(text.as_bytes()), 5, false)?;
    if !out.status.success() {
        anyhow::bail!(
            "wl-copy failed: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }
    Ok(())
}

/// Place UTF-8 plain text on the primary selection (middle-click /
// Shift+Insert source for terminals). Same ownership semantics as
// offer_text; text travels via stdin pipe, never argv.
pub fn offer_primary(text: &str) -> anyhow::Result<()> {
    let mut cmd = Command::new("wl-copy");
    cmd.arg("--primary")
        .arg("--type")
        .arg("text/plain;charset=utf-8");
    let out = run_timeout(cmd, Some(text.as_bytes()), 5, false)?;
    if !out.status.success() {
        anyhow::bail!(
            "wl-copy --primary failed: {}",
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }
    Ok(())
}

/// Snapshot current plain-text clipboard (bounded 64 KiB), if any.
pub fn snapshot_text() -> Option<String> {
    let mut cmd = Command::new("wl-paste");
    cmd.arg("--no-newline").arg("--type").arg("text/plain");
    let out = run_timeout(cmd, None, 5, true).ok()?;
    snapshot_from_output(&out)
}

/// Snapshot current primary selection (bounded 64 KiB), if any.
pub fn snapshot_primary() -> Option<String> {
    let mut cmd = Command::new("wl-paste");
    cmd.arg("--primary")
        .arg("--no-newline")
        .arg("--type")
        .arg("text/plain");
    let out = run_timeout(cmd, None, 5, true).ok()?;
    snapshot_from_output(&out)
}

fn snapshot_from_output(out: &std::process::Output) -> Option<String> {
    if !out.status.success() || out.stdout.is_empty() {
        return None;
    }
    let mut s = String::from_utf8(out.stdout.clone()).ok()?;
    let mut boundary = s.len().min(64 * 1024);
    while !s.is_char_boundary(boundary) {
        boundary -= 1;
    }
    s.truncate(boundary);
    Some(s)
}

/// Best-effort check: does the primary selection still hold exactly our text?
pub fn primary_still_ours(text: &str) -> bool {
    match snapshot_primary() {
        Some(cur) => cur == text,
        None => false,
    }
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
        let mut cmd = Command::new("wl-copy");
        cmd.arg("--clear");
        let _ = run_timeout(cmd, None, 5, false);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn helper_success_returns_output() {
        let out = run_timeout(Command::new("true"), None, 5, true).unwrap();
        assert!(out.status.success());
    }

    #[test]
    fn helper_hang_is_killed_by_deadline() {
        let mut sleep = Command::new("sleep");
        sleep.arg("30");
        let t0 = std::time::Instant::now();
        let err = run_timeout(sleep, None, 1, true).unwrap_err();
        assert!(err.to_string().contains("timed out"), "{err}");
        assert!(t0.elapsed() < Duration::from_secs(4));
    }
}
