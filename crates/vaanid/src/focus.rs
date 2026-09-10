//! Compositor focus checks via supported Hyprland IPC (`hyprctl`).
//! Records target window identity + app id at dictation start (never titles
//! or document contents). At completion, verifies the target still exists
//! and is focused. No focus stealing, no global key grabs.

use serde::Deserialize;

#[derive(Debug, Clone, Default)]
pub struct FocusTarget {
    pub address: String,
    pub app_id: String,
    pub focused: bool,
}

#[derive(Debug, Deserialize)]
struct ActiveWindow {
    #[serde(default)]
    address: String,
    #[serde(default)]
    class: String,
    #[serde(default)]
    focused: bool,
}

pub fn active_target() -> FocusTarget {
    let out = std::process::Command::new("hyprctl")
        .arg("activewindow")
        .arg("-j")
        .output();
    let Ok(out) = out else { return FocusTarget::default() };
    if !out.status.success() {
        return FocusTarget::default();
    }
    match serde_json::from_slice::<ActiveWindow>(&out.stdout) {
        Ok(w) => FocusTarget {
            address: w.address,
            app_id: w.class,
            focused: true,
        },
        Err(_) => FocusTarget::default(),
    }
}

/// Re-check immediately before dispatch. Returns Ok(target) if the original
/// target still exists and has focus; Err(reason) otherwise.
pub fn recheck_target(start: &FocusTarget) -> Result<FocusTarget, String> {
    let now = active_target();
    if now.address.is_empty() {
        return Err("cannot determine focused window; using copy-only".into());
    }
    if now.address != start.address {
        return Err("target changed".into());
    }
    if !now.focused {
        return Err("target lost focus".into());
    }
    Ok(now)
}

/// Whether this app id is a terminal (copy-only default; multiline paste can
/// execute commands even without synthetic Enter).
pub fn is_terminal(app_id: &str) -> bool {
    let l = app_id.to_lowercase();
    ["foot", "kitty", "alacritty", "wezterm", "gnome-terminal", "konsole", "xterm", "ghostty"]
        .iter()
        .any(|t| l.contains(t))
}
