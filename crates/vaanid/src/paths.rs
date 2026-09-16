//! XDG paths. Runtime sockets live ONLY under $XDG_RUNTIME_DIR/vaani.

use std::path::PathBuf;

fn home() -> String {
    std::env::var("HOME").unwrap_or_else(|_| ".".into())
}

pub fn runtime_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("XDG_RUNTIME_DIR") {
        PathBuf::from(dir).join("vaani")
    } else {
        // Never invent a shared /tmp fallback with weak perms: scope to
        // /tmp/vaani-<uid> with 0700.
        let uid = std::env::var("UID").ok().and_then(|s| s.parse::<u32>().ok()).unwrap_or(1000);
        PathBuf::from(format!("/tmp/vaani-{uid}"))
    }
}

pub fn control_sock() -> PathBuf {
    runtime_dir().join("control.sock")
}

pub fn config_dir() -> PathBuf {
    let base =
        std::env::var("XDG_CONFIG_HOME").unwrap_or_else(|_| format!("{}/.config", home()));
    PathBuf::from(base).join("vaani")
}

pub fn data_dir() -> PathBuf {
    let base =
        std::env::var("XDG_DATA_HOME").unwrap_or_else(|_| format!("{}/.local/share", home()));
    PathBuf::from(base).join("vaani")
}

pub fn models_dir() -> PathBuf {
    data_dir().join("models")
}

pub fn personalization_path() -> PathBuf {
    data_dir().join("personalization.jsonl")
}

pub fn ensure_dirs() -> anyhow::Result<()> {
    for d in [runtime_dir(), config_dir(), data_dir(), models_dir()] {
        std::fs::create_dir_all(&d)?;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(runtime_dir(), std::fs::Permissions::from_mode(0o700));
    }
    Ok(())
}

/// Explicit paths also work when another shell owns the default QML config.
pub fn ui_path() -> PathBuf {
    let config = std::env::var("XDG_CONFIG_HOME")
        .unwrap_or_else(|_| format!("{}/.config", home()));
    let local = PathBuf::from(config).join("quickshell/vaani/shell.qml");
    if local.is_file() { return local; }
    let data = std::env::var("XDG_DATA_DIRS").unwrap_or_else(|_| "/usr/local/share:/usr/share".into());
    for base in data.split(':').filter(|s| !s.is_empty()) {
        let candidate = PathBuf::from(base).join("quickshell/vaani/shell.qml");
        if candidate.is_file() { return candidate; }
    }
    local
}
