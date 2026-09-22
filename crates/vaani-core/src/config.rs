//! Human-editable TOML configuration.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

pub const CONFIG_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    #[serde(default = "schema_default")]
    pub schema_version: u32,
    #[serde(default)]
    pub general: General,
    #[serde(default)]
    pub audio: Audio,
    #[serde(default)]
    pub recognition: Recognition,
    #[serde(default)]
    pub insertion: Insertion,
    #[serde(default)]
    pub cleanup: Cleanup,
    #[serde(default)]
    pub privacy: Privacy,
}

fn schema_default() -> u32 {
    CONFIG_SCHEMA_VERSION
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct General {
    /// economy | balanced | ready
    #[serde(default = "default_profile")]
    pub residency_profile: String,
    #[serde(default)]
    pub review_before_insertion: bool,
    #[serde(default = "default_true")]
    pub unicode_output: bool,
    /// live-dictation commit cadence, seconds (2..=10). Lower = more
    /// responsive typing, more inference cost + clipboard churn.
    #[serde(default = "default_live_chunk")]
    pub live_chunk_secs: u64,
    /// Hands-free finish: stop + transcribe after this many seconds of
    /// silence following speech (1..=10). 0 disables (manual stop only).
    #[serde(default = "default_auto_stop")]
    pub auto_stop_secs: u64,
    /// First-run desktop onboarding has been completed.
    #[serde(default)]
    pub onboarding_complete: bool,
    /// Human-readable compositor shortcut, generated into the app-owned
    /// Hyprland include by the installer or desktop Settings. The daemon never
    /// grabs keys itself.
    #[serde(default = "default_shortcut")]
    pub shortcut: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Audio {
    /// stable device property e.g. "alsa.card_name=..." or empty = default source
    #[serde(default)]
    pub device_selector: String,
    #[serde(default = "default_threads")]
    pub worker_threads: u32,
    /// seconds, hard cap
    #[serde(default = "default_max_secs")]
    pub max_secs: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Recognition {
    #[serde(default = "default_model")]
    pub model: String,
    /// Fast model for the running live preview (1 s ticks). The final
    /// transcript always uses `model`: preview stays cheap (base loads in
    /// ~1 s; without the resident server the fine-tuned CT2 reloads every call)
    /// the accurate model. Provisional either way.
    #[serde(default = "default_model")]
    pub live_model: String,
    /// Resident faster-whisper server idle TTL, seconds (10..=600). The
    /// fine-tuned model stays loaded this long after the last chunk so
    /// streaming ticks skip the model reload (~0.3 s/chunk); expiry frees VRAM.
    /// 0 disables the server (one-shot per call).
    #[serde(default = "default_server_idle")]
    pub server_idle_secs: u64,
    /// en | hi | bn | auto (auto only for >=10s utterances; short uses `language`)
    #[serde(default = "default_lang")]
    pub language: String,
    #[serde(default)]
    pub translate_to_en: bool,
    #[serde(default = "default_device")]
    pub device: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Insertion {
    /// automatic | review | copy-only
    #[serde(default = "default_insertion_mode")]
    pub mode: String,
    /// app-id regex -> mode override
    #[serde(default)]
    pub app_overrides: HashMap<String, String>,
    /// bounded clipboard serving seconds
    #[serde(default = "default_clip_secs")]
    pub clipboard_serve_secs: u64,
    #[serde(default = "default_pending_secs")]
    pub pending_expiry_secs: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Cleanup {
    #[serde(default)]
    pub vocabulary: Vec<String>,
    /// Path to the local formatter model directory.
    #[serde(default)]
    pub model_path: String,
    /// Path to the local LLM LoRA adapter dir. Empty keeps the legacy
    /// dpo-sft adapter next to model_path.
    #[serde(default)]
    pub adapter_path: String,
    /// Path to vaani_inject.py (optional: daemon falls back to builtin call).
    #[serde(default)]
    pub python_path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Privacy {
    #[serde(default)]
    pub save_history: bool,
    #[serde(default)]
    pub hide_preview_on_sharing: bool,
}

fn default_profile() -> String {
    "economy".into()
}
fn default_true() -> bool {
    true
}
fn default_live_chunk() -> u64 {
    1
}
fn default_auto_stop() -> u64 {
    1
}
fn default_shortcut() -> String {
    "SUPER+H".into()
}
fn default_threads() -> u32 {
    4
}
fn default_max_secs() -> u32 {
    120
}
fn default_model() -> String {
    "base".into()
}
fn default_server_idle() -> u64 {
    // Economy is the default profile and must not leave an inference helper
    // resident after an operation. Balanced/Ready opt in to a non-zero TTL.
    0
}
fn default_lang() -> String {
    "en".into()
}
fn default_device() -> String {
    "cpu".into()
}
fn default_insertion_mode() -> String {
    // Automatic delivery was the original dictation behavior. Safety policy
    // still forces terminals, review sessions, and failed focus checks to
    // copy-only; users can opt out globally with insertion.mode = "copy-only".
    "automatic".into()
}
fn default_clip_secs() -> u64 {
    30
}
fn default_pending_secs() -> u64 {
    300
}
impl Default for General {
    fn default() -> Self {
        Self {
            residency_profile: default_profile(),
            review_before_insertion: false,
            unicode_output: true,
            live_chunk_secs: default_live_chunk(),
            auto_stop_secs: default_auto_stop(),
            onboarding_complete: false,
            shortcut: default_shortcut(),
        }
    }
}
impl Default for Audio {
    fn default() -> Self {
        Self {
            device_selector: String::new(),
            worker_threads: 4,
            max_secs: 120,
        }
    }
}
impl Default for Recognition {
    fn default() -> Self {
        Self {
            model: default_model(),
            live_model: default_model(),
            server_idle_secs: default_server_idle(),
            language: default_lang(),
            translate_to_en: false,
            device: default_device(),
        }
    }
}
impl Default for Insertion {
    fn default() -> Self {
        Self {
            mode: default_insertion_mode(),
            app_overrides: HashMap::new(),
            clipboard_serve_secs: default_clip_secs(),
            pending_expiry_secs: default_pending_secs(),
        }
    }
}
impl Default for Cleanup {
    fn default() -> Self {
        Self {
            vocabulary: Vec::new(),
            model_path: String::new(),
            adapter_path: String::new(),
            python_path: String::new(),
        }
    }
}
impl Default for Privacy {
    fn default() -> Self {
        Self {
            save_history: false,
            hide_preview_on_sharing: false,
        }
    }
}
impl Default for Config {
    fn default() -> Self {
        Self {
            schema_version: CONFIG_SCHEMA_VERSION,
            general: General::default(),
            audio: Audio::default(),
            recognition: Recognition::default(),
            insertion: Insertion::default(),
            cleanup: Cleanup::default(),
            privacy: Privacy::default(),
        }
    }
}

impl Config {
    pub fn config_path() -> PathBuf {
        #[cfg(windows)]
        let base = std::env::var("APPDATA")
            .or_else(|_| std::env::var("LOCALAPPDATA"))
            .unwrap_or_else(|_| ".".into());
        #[cfg(not(windows))]
        let base = std::env::var("XDG_CONFIG_HOME").unwrap_or_else(|_| {
            format!(
                "{}/.config",
                std::env::var("HOME").unwrap_or_else(|_| ".".into())
            )
        });
        PathBuf::from(base).join("vaani/config.toml")
    }

    pub fn load() -> Self {
        let p = Self::config_path();
        Self::load_from(&p)
    }

    pub fn load_from(p: &std::path::Path) -> Self {
        match std::fs::read_to_string(p) {
            Ok(s) => match toml::from_str::<Config>(&s) {
                Ok(mut c) => {
                    c.normalise();
                    c
                }
                Err(_) => Self::default(),
            },
            Err(_) => Self::default(),
        }
    }

    fn normalise(&mut self) {
        // Clamp worker threads 1..=16, max_secs 5..=120.
        self.audio.worker_threads = self.audio.worker_threads.clamp(1, 16);
        self.audio.max_secs = self.audio.max_secs.clamp(5, crate::MAX_AUDIO_SECS);
        self.recognition.server_idle_secs = self.recognition.server_idle_secs.min(600);
        if !valid_shortcut(&self.general.shortcut) {
            self.general.shortcut = default_shortcut();
        }
        // Bound vocabulary: max 200 terms, each max 80 chars.
        self.cleanup.vocabulary.truncate(200);
        for t in &mut self.cleanup.vocabulary {
            t.truncate(80);
        }
        // Validate enums, fall back to safe defaults.
        match self.general.residency_profile.as_str() {
            "economy" | "balanced" | "ready" => {}
            _ => self.general.residency_profile = "economy".into(),
        }
        match self.insertion.mode.as_str() {
            "automatic" | "review" | "copy-only" => {}
            _ => self.insertion.mode = "automatic".into(),
        }
        self.insertion.app_overrides.retain(|pattern, mode| {
            !pattern.trim().is_empty()
                && pattern.len() <= 128
                && !pattern.contains(['=', '\r', '\n'])
                && matches!(mode.as_str(), "automatic" | "review" | "copy-only")
        });
    }

    /// Effective insertion mode for an app id (override wins).
    pub fn insertion_mode_for(&self, app_id: &str) -> String {
        for (pat, mode) in &self.insertion.app_overrides {
            if app_id.contains(pat.as_str()) || app_id == pat {
                return mode.clone();
            }
        }
        self.insertion.mode.clone()
    }

    /// Residency policy is authoritative. Economy never keeps an inference
    /// sidecar alive; Balanced keeps it warm for at least 60 seconds; Ready
    /// keeps it warm up to the configured 10-minute safety cap. A non-zero
    /// configured TTL may shorten neither profile's minimum guarantee.
    pub fn effective_server_idle_secs(&self) -> u64 {
        match self.general.residency_profile.as_str() {
            "economy" => 0,
            "balanced" => self.recognition.server_idle_secs.max(60),
            "ready" => self.recognition.server_idle_secs.max(600),
            _ => 0,
        }
    }

    /// Whitelisted single-key update from UI/CLI. Values are validated and
    /// clamped; unknown keys are rejected. Returns the canonical value.
    pub fn set_key(&mut self, key: &str, value: &str) -> Result<String, String> {
        let v = value.trim();
        match key {
            "general.onboarding_complete" => match v {
                "true" | "false" => {
                    self.general.onboarding_complete = v == "true";
                    Ok(v.into())
                }
                _ => Err("must be true|false".into()),
            },
            "general.shortcut" => {
                if !valid_shortcut(v) {
                    return Err("use one key with optional CTRL+ALT+SHIFT+SUPER modifiers".into());
                }
                self.general.shortcut = v.to_ascii_uppercase();
                Ok(self.general.shortcut.clone())
            }
            "general.residency_profile" => match v {
                "economy" | "balanced" | "ready" => {
                    self.general.residency_profile = v.into();
                    Ok(v.into())
                }
                _ => Err("must be economy|balanced|ready".into()),
            },
            "general.review_before_insertion" => match v {
                "true" | "false" => {
                    self.general.review_before_insertion = v == "true";
                    Ok(v.into())
                }
                _ => Err("must be true|false".into()),
            },
            "general.live_chunk_secs" => {
                let n: u64 = v.parse().map_err(|_| "must be 1..10")?;
                if !(1..=10).contains(&n) {
                    return Err("must be 1..10".into());
                }
                self.general.live_chunk_secs = n;
                Ok(n.to_string())
            }
            "general.auto_stop_secs" => {
                let n: u64 = v.parse().map_err(|_| "must be 0..10")?;
                if n > 10 {
                    return Err("must be 0..10".into());
                }
                self.general.auto_stop_secs = n;
                Ok(n.to_string())
            }
            "audio.device_selector" => {
                if v.len() > 256 {
                    return Err("too long".into());
                }
                self.audio.device_selector = v.into();
                Ok(v.into())
            }
            "audio.worker_threads" => {
                let n: u32 = v.parse().map_err(|_| "must be 1..16")?;
                if !(1..=16).contains(&n) {
                    return Err("must be 1..16".into());
                }
                self.audio.worker_threads = n;
                Ok(n.to_string())
            }
            "recognition.model" => match v {
                "tiny" | "base" | "base.en" | "small" | "cozy" | "v5" => {
                    self.recognition.model = v.into();
                    Ok(v.into())
                }
                _ => Err("must be tiny|base|base.en|small|cozy|v5".into()),
            },
            "recognition.live_model" => match v {
                "tiny" | "base" | "base.en" | "small" | "cozy" | "v5" => {
                    self.recognition.live_model = v.into();
                    Ok(v.into())
                }
                _ => Err("must be tiny|base|base.en|small|cozy|v5".into()),
            },
            "recognition.server_idle_secs" => {
                let n: u64 = v.parse().map_err(|_| "must be 0..600")?;
                if n > 600 {
                    return Err("must be 0..600".into());
                }
                self.recognition.server_idle_secs = n;
                Ok(n.to_string())
            }
            "recognition.language" => match v {
                "en" | "hi" | "bn" => {
                    self.recognition.language = v.into();
                    Ok(v.into())
                }
                _ => Err("must be en|hi|bn".into()),
            },
            "recognition.translate_to_en" => match v {
                "true" | "false" => {
                    self.recognition.translate_to_en = v == "true";
                    Ok(v.into())
                }
                _ => Err("must be true|false".into()),
            },
            "recognition.device" => match v {
                "cpu" | "cuda" => {
                    self.recognition.device = v.into();
                    Ok(v.into())
                }
                _ => Err("must be cpu|cuda".into()),
            },
            "insertion.mode" => match v {
                "automatic" | "review" | "copy-only" => {
                    self.insertion.mode = v.into();
                    Ok(v.into())
                }
                _ => Err("must be automatic|review|copy-only".into()),
            },
            "insertion.app_override" => {
                let (pattern, mode) = v
                    .split_once('=')
                    .ok_or("must be app pattern=automatic|review|copy-only|none")?;
                let pattern = pattern.trim();
                if pattern.is_empty() || pattern.len() > 128 || pattern.contains(['=', '\r', '\n'])
                {
                    return Err(
                        "app pattern must be 1..128 characters without = or newlines".into(),
                    );
                }
                match mode.trim() {
                    "automatic" | "review" | "copy-only" => {
                        self.insertion
                            .app_overrides
                            .insert(pattern.into(), mode.trim().into());
                        Ok(format!("{pattern}={}", mode.trim()))
                    }
                    "none" => {
                        self.insertion.app_overrides.remove(pattern);
                        Ok(format!("{pattern}=none"))
                    }
                    _ => Err("must be app pattern=automatic|review|copy-only|none".into()),
                }
            }
            "cleanup.model_path" => {
                if v.len() > 512 {
                    return Err("too long".into());
                }
                self.cleanup.model_path = v.into();
                Ok(v.into())
            }
            "cleanup.adapter_path" => {
                if v.len() > 512 {
                    return Err("too long".into());
                }
                self.cleanup.adapter_path = v.into();
                Ok(v.into())
            }
            "cleanup.python_path" => {
                if v.len() > 512 {
                    return Err("too long".into());
                }
                self.cleanup.python_path = v.into();
                Ok(v.into())
            }
            // Vocabulary (names/terms) for the recognizer prompt.
            // Comma-separated APPEND; empty value clears the list.
            "cleanup.vocabulary" => {
                if v.is_empty() {
                    self.cleanup.vocabulary.clear();
                    return Ok(String::new());
                }
                for term in v.split(',').map(str::trim).filter(|t| !t.is_empty()) {
                    let mut t = term.to_string();
                    t.truncate(80);
                    if !self
                        .cleanup
                        .vocabulary
                        .iter()
                        .any(|e| e.eq_ignore_ascii_case(&t))
                    {
                        self.cleanup.vocabulary.push(t);
                    }
                }
                self.cleanup.vocabulary.truncate(200);
                Ok(self.cleanup.vocabulary.join(", "))
            }
            "privacy.save_history" | "privacy.hide_preview_on_sharing" => match v {
                "true" | "false" => {
                    let b = v == "true";
                    if key == "privacy.save_history" {
                        self.privacy.save_history = b;
                    } else {
                        self.privacy.hide_preview_on_sharing = b;
                    }
                    Ok(v.into())
                }
                _ => Err("must be true|false".into()),
            },
            _ => Err("unknown key".into()),
        }
    }

    /// Atomic persist (tmp file + rename). User config is preserved on
    /// uninstall; never touched by package hooks.
    pub fn save(&self) -> anyhow::Result<()> {
        let p = Self::config_path();
        if let Some(dir) = p.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let text = toml::to_string_pretty(self)?;
        let tmp = p.with_extension("toml.tmp");
        std::fs::write(&tmp, text)?;
        std::fs::rename(&tmp, &p)?;
        Ok(())
    }
}

fn valid_shortcut(value: &str) -> bool {
    let parts: Vec<_> = value
        .split('+')
        .map(|part| part.trim().to_ascii_uppercase())
        .filter(|part| !part.is_empty())
        .collect();
    if parts.is_empty() || parts.len() > 5 {
        return false;
    }
    let mut keys = 0;
    for part in parts {
        if matches!(part.as_str(), "CTRL" | "ALT" | "SHIFT" | "SUPER" | "META") {
            continue;
        }
        keys += 1;
        if part.len() > 16 || !part.chars().all(|c| c.is_ascii_alphanumeric()) {
            return false;
        }
    }
    keys == 1
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_are_safe() {
        let c = Config::default();
        assert_eq!(c.general.residency_profile, "economy");
        assert_eq!(c.effective_server_idle_secs(), 0);
        assert!(!c.privacy.save_history);
    }

    #[test]
    fn residency_profiles_have_explicit_warmth_guarantees() {
        let mut c = Config::default();
        c.general.residency_profile = "balanced".into();
        assert_eq!(c.effective_server_idle_secs(), 60);
        c.general.residency_profile = "ready".into();
        assert_eq!(c.effective_server_idle_secs(), 600);
        c.recognition.server_idle_secs = 120;
        assert_eq!(c.effective_server_idle_secs(), 600);
        c.general.residency_profile = "economy".into();
        assert_eq!(c.effective_server_idle_secs(), 0);
    }

    #[test]
    fn overrides_win() {
        let mut c = Config::default();
        assert_eq!(c.insertion_mode_for("anything"), "automatic");
        c.insertion
            .app_overrides
            .insert("foot".into(), "automatic".into());
        assert_eq!(c.insertion_mode_for("foot"), "automatic");
        assert_eq!(c.insertion_mode_for("firefox"), "automatic");
    }

    #[test]
    fn invalid_insertion_mode_falls_back_to_automatic() {
        let mut c = Config::default();
        c.insertion.mode = "unsafe".into();
        c.normalise();
        assert_eq!(c.insertion.mode, "automatic");
    }
}
