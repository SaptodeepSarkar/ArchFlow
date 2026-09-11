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
    // Terminals paste from the primary selection (Shift+Insert, single
    // modifier): the dual-modifier Shift+Ctrl+V chord does not deliver
    // through the virtual keyboard on this compositor, while single-modifier
    // chords and literal typing do. Both selections end up holding the text.
    let use_primary = uses_primary_paste(&current.app_id);
    if use_primary {
        if let Err(e) = clipboard::offer_primary(text) {
            return InsertOutcome::Failed(format!("primary offer failed: {e}"));
        }
        if let Err(e) = clipboard::offer_text(text) {
            return InsertOutcome::Failed(format!("clipboard offer failed: {e}"));
        }
        if !clipboard::primary_still_ours(text) {
            return InsertOutcome::CopyReady(
                "primary offer was replaced before paste dispatch".into(),
            );
        }
    } else if let Err(e) = clipboard::offer_text(text) {
        return InsertOutcome::Failed(format!("clipboard offer failed: {e}"));
    }
    if !clipboard::still_ours(text) {
        return InsertOutcome::CopyReady(
            "clipboard offer was replaced before paste dispatch".into(),
        );
    }
    if let Err(reason) = focus::recheck_target(start_target) {
        return InsertOutcome::CopyReady(format!(
            "target changed after clipboard offer ({reason})"
        ));
    }
    let chord = paste_chord_for(&current.app_id);
    match dispatch_paste(&chord) {
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
    if uses_primary_paste(&current.app_id) {
        clipboard::offer_primary(text).map_err(|e| format!("primary offer failed: {e}"))?;
        clipboard::offer_text(text).map_err(|e| format!("clipboard offer failed: {e}"))?;
        if !clipboard::primary_still_ours(text) {
            return Err("primary offer was replaced before paste dispatch".into());
        }
    } else {
        clipboard::offer_text(text).map_err(|e| format!("clipboard offer failed: {e}"))?;
    }
    if !clipboard::still_ours(text) {
        return Err("clipboard offer was replaced before paste dispatch".into());
    }
    focus::recheck_target(target)?;
    let chord = paste_chord_for(&current.app_id);
    dispatch_paste(&chord).map_err(|e| format!("dispatch failed: {e}"))?;
    Ok(())
}

/// Terminals paste from the primary selection with Shift+Insert (one
/// modifier); GUI apps paste from the clipboard with Ctrl+V.
fn uses_primary_paste(app_id: &str) -> bool {
    let l = app_id.to_lowercase();
    l.contains("foot")
        || l.contains("kitty")
        || l.contains("alacritty")
        || l.contains("wezterm")
}

fn paste_chord_for(app_id: &str) -> String {
    if uses_primary_paste(app_id) {
        "SHIFT+Insert".into()
    } else {
        "CTRL+V".into()
    }
}

/// Prefer the Wayland virtual-keyboard protocol. Chromium/Firefox-family
/// clients can ignore compositor-synthesized shortcuts even when Hyprland
/// reports success. Dictated text remains in the clipboard (and the primary
/// selection for terminals); only the paste chord itself is sent through
/// wtype. Fall back to Hyprland for installations without it.
fn dispatch_paste(chord: &str) -> anyhow::Result<()> {
    let (mods, key) = chord_parts(chord)?;
    if let Some(wtype) = find_wtype() {
        let mut cmd = std::process::Command::new(wtype);
        for modifier in mods.split_whitespace() {
            cmd.arg("-M").arg(modifier);
        }
        cmd.arg("-k").arg(&key);
        for modifier in mods.split_whitespace().rev() {
            cmd.arg("-m").arg(modifier);
        }
        let out = cmd.output().map_err(|e| anyhow::anyhow!("wtype failed to start: {e}"))?;
        if out.status.success() {
            return Ok(());
        }
    }

    let lua = format!(
        r#"hl.dispatch(hl.dsp.send_shortcut({{ mods = "{mods}", key = "{key}" }}))"#
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

fn find_wtype() -> Option<std::path::PathBuf> {
    let sibling = std::env::current_exe().ok()?.parent()?.join("wtype");
    if sibling.is_file() {
        return Some(sibling);
    }
    std::env::var_os("PATH").and_then(|paths| {
        std::env::split_paths(&paths)
            .map(|dir| dir.join("wtype"))
            .find(|path| path.is_file())
    })
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

    #[test]
    fn terminal_chords_use_primary_single_mod() {
        assert_eq!(paste_chord_for("foot"), "SHIFT+Insert");
        assert_eq!(paste_chord_for("kitty"), "SHIFT+Insert");
        assert_eq!(paste_chord_for("org.wezfurlong.wezterm"), "SHIFT+Insert");
        assert_eq!(paste_chord_for("zen"), "CTRL+V");
        assert_eq!(
            chord_parts("SHIFT+Insert").unwrap(),
            ("shift".into(), "insert".into())
        );
    }

    #[test]
    fn wtype_lookup_does_not_require_a_shell() {
        // Lookup is direct and fixed-name; dictated text never enters argv.
        if let Some(path) = find_wtype() {
            assert_eq!(path.file_name().unwrap(), "wtype");
        }
    }
}

fn looks_shell_like(t: &str) -> bool {
    let l = t.to_lowercase();
    ["rm -rf", "sudo ", "mkfs", ":(){", "chmod ", "curl ", "wget ", "dd if=", "shutdown", "reboot"]
        .iter()
        .any(|p| l.contains(p))
}
