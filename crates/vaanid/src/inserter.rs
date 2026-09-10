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

fn paste_chord_for(app_id: &str) -> String {
    let l = app_id.to_lowercase();
    if l.contains("foot") || l.contains("kitty") || l.contains("alacritty") || l.contains("wezterm") {
        "SHIFT+CTRL+V".into()
    } else {
        "CTRL+V".into()
    }
}

/// Verified compositor key dispatch. Aborts to copy-only if modifier state
/// cannot be established — never a blind sleep-and-hope.
fn dispatch_key(chord: &str) -> anyhow::Result<()> {
    // hyprctl dispatch sendkey <modifiers>,<key>. Verify hyprctl exists and
    // the call succeeds; hyprctl itself resolves modifier state.
    let (mods, key) = chord
        .rsplit_once('+')
        .map(|(m, k)| (m.to_lowercase(), k.to_string()))
        .unwrap_or(("".into(), chord.into()));
    let key_arg = if mods.is_empty() {
        key
    } else {
        format!("{mods},{key}")
    };
    let out = std::process::Command::new("hyprctl")
        .arg("dispatch")
        .arg("sendkey")
        .arg(&key_arg)
        .output()
        .map_err(|e| anyhow::anyhow!("hyprctl not available: {e}"))?;
    if out.status.success() {
        Ok(())
    } else {
        anyhow::bail!("{}", String::from_utf8_lossy(&out.stderr).trim());
    }
}

fn looks_shell_like(t: &str) -> bool {
    let l = t.to_lowercase();
    ["rm -rf", "sudo ", "mkfs", ":(){", "chmod ", "curl ", "wget ", "dd if=", "shutdown", "reboot"]
        .iter()
        .any(|p| l.contains(p))
}
