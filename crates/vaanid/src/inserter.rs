//! Hyprland insertion adapter: clipboard offer + verified key-dispatch.
//! Returns a TextInserter outcome; a successful key dispatch is NOT proof the
//! app accepted the text, so we report "Paste requested".

use crate::clipboard;
use crate::focus::{self, FocusTarget};

#[derive(Debug, Clone, PartialEq)]
pub enum InsertOutcome {
    /// Environment cannot insert (e.g. no hyprctl) — caller keeps copy-ready.
    Unsupported(String),
    CopyReady(String),
    DispatchAttempted(String),
    Failed(String),
}

impl std::fmt::Display for InsertOutcome {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            InsertOutcome::Unsupported(s) => write!(f, "unsupported: {s}"),
            InsertOutcome::CopyReady(s) => write!(f, "copy-ready: {s}"),
            InsertOutcome::DispatchAttempted(s) => write!(f, "paste requested: {s}"),
            InsertOutcome::Failed(s) => write!(f, "failed: {s}"),
        }
    }
}

/// Attempt automatic insertion for `target`. Policy inputs: configured mode,
/// terminal copy-only rule, multiline-terminal refusal.
pub fn insert_automatic(
    text: &str,
    start_target: &FocusTarget,
    configured_mode: &str,
) -> InsertOutcome {
    if configured_mode == "copy-only" {
        return InsertOutcome::CopyReady("copy-only mode configured".into());
    }
    if configured_mode == "review" {
        return InsertOutcome::CopyReady("review mode: awaiting explicit confirmation".into());
    }
    // Recheck focus immediately before dispatch (documented race remains).
    let current = match focus::recheck_target(start_target) {
        Ok(t) => t,
        Err(reason) => return InsertOutcome::CopyReady(format!("target changed ({reason})")),
    };
    // Terminal policy: copy-only, and never auto-paste multiline shell-like
    // content or append Enter.
    if focus::is_terminal(&current.app_id) {
        return InsertOutcome::CopyReady("terminal target: copy-only policy".into());
    }
    if text.contains('\n') && looks_shell_like(text) {
        return InsertOutcome::CopyReady(
            "multiline shell-like text: copy-only to avoid accidental execution".into(),
        );
    }
    // Offer on clipboard, then dispatch the app's paste chord.
    if let Err(e) = clipboard::offer_text(text) {
        return InsertOutcome::Failed(format!("clipboard offer failed: {e}"));
    }
    let chord = paste_chord_for(&current.app_id);
    match dispatch_key(&chord) {
        Ok(()) => InsertOutcome::DispatchAttempted(format!(
            "paste dispatched ({chord}) for {}",
            current.app_id
        )),
        Err(e) => InsertOutcome::CopyReady(format!("dispatch failed ({e}); text on clipboard")),
    }
}

/// Live-dictation commit: type one stabilized delta into the target.
/// Rechecks focus immediately before dispatch; any failure freezes live
/// commits (caller keeps the full text recoverable). Never appends Enter.
pub(crate) fn commit_delta(text: &str, target: &FocusTarget) -> Result<(), String> {
    let current = focus::recheck_target(target)?;
    clipboard::offer_text(text).map_err(|e| format!("clipboard offer failed: {e}"))?;
    let chord = paste_chord_for(&current.app_id);
    dispatch_key(&chord).map_err(|e| format!("dispatch failed: {e}"))?;
    Ok(())
}

fn paste_chord_for(app_id: &str) -> String {
    let l = app_id.to_lowercase();
    if l.contains("foot") || l.contains("kitty") || l.contains("alacritty") || l.contains("wezterm") {
        "SHIFT+CTRL+V".into()
    } else {
        "CTRL+V".into()
    }
}

/// Key dispatch through the compositor's Lua API (`send_shortcut`).
/// NOTE: the classic `hyprctl dispatch sendkey <mods>,<key>` CLI form is a
/// Lua syntax error on Lua-driven Hyprland builds (0.56+), so every dispatch
/// through it failed and all insertion silently fell back to copy-only.
/// This was verified live against the installed compositor, including a
/// paste-into-scratch-window proof. Only fixed chord fragments are ever
/// interpolated (validated below); dictated text travels via clipboard.
fn dispatch_key(chord: &str) -> anyhow::Result<()> {
    let (mods, key) = chord_parts(chord)?;
    let lua = format!(
        r#"hl.dispatch(hl.dsp.send_shortcut({{ mods = "{mods}", key = "{key}", window = "active" }}))"#
    );
    let out = std::process::Command::new("hyprctl")
        .arg("eval")
        .arg(&lua)
        .output()
        .map_err(|e| anyhow::anyhow!("hyprctl not available: {e}"))?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    if out.status.success() && stdout.trim() == "ok" {
        Ok(())
    } else {
        let err = String::from_utf8_lossy(&out.stderr);
        let detail = if err.trim().is_empty() { stdout.trim().to_string() } else { err.trim().to_string() };
        anyhow::bail!("{detail}")
    }
}

/// Split "SHIFT+CTRL+V" into Lua send_shortcut (mods, key), whitelisted to
/// alphanumerics + space so only our fixed chords can interpolate.
fn chord_parts(chord: &str) -> anyhow::Result<(String, String)> {
    let mut parts: Vec<&str> = chord.split('+').collect();
    if parts.is_empty() {
        anyhow::bail!("empty chord");
    }
    let key = parts.pop().unwrap().to_lowercase();
    let mods = parts.iter().map(|m| m.to_lowercase()).collect::<Vec<_>>().join(" ");
    for s in std::iter::once(key.as_str()).chain(mods.split(' ')) {
        if s.is_empty() || !s.chars().all(|c| c.is_ascii_alphanumeric()) {
            anyhow::bail!("invalid chord fragment");
        }
    }
    Ok((mods, key))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn chords_split_for_lua() {
        assert_eq!(chord_parts("CTRL+V").unwrap(), ("ctrl".into(), "v".into()));
        assert_eq!(
            chord_parts("SHIFT+CTRL+V").unwrap(),
            ("shift ctrl".into(), "v".into())
        );
        assert!(chord_parts("CTRL+$(evil)").is_err());
    }
}

fn looks_shell_like(t: &str) -> bool {
    let l = t.to_lowercase();
    ["rm -rf", "sudo ", "mkfs", ":(){", "chmod ", "curl ", "wget ", "dd if=", "shutdown", "reboot"]
        .iter()
        .any(|p| l.contains(p))
}
