//! Parser for `vaani.conf` — the single source of Vaani settings.
//!
//! Parsed once at boot (see `PRD/config.md`, `DOCS/configuration.md`).
//! Rules: unknown keys/sections yield warnings, never errors; a missing
//! file yields the documented defaults. Stdlib only, no dependencies.

use std::path::Path;

/// Device preference for model loading (`prefer_device`).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum PreferDevice {
    Dgpu,
    Igpu,
    #[default]
    Auto,
}

impl PreferDevice {
    fn parse(value: &str) -> Option<Self> {
        match value.trim().to_ascii_lowercase().as_str() {
            "dgpu" => Some(Self::Dgpu),
            "igpu" => Some(Self::Igpu),
            "auto" => Some(Self::Auto),
            _ => None,
        }
    }
}

impl std::fmt::Display for PreferDevice {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Dgpu => write!(f, "dgpu"),
            Self::Igpu => write!(f, "igpu"),
            Self::Auto => write!(f, "auto"),
        }
    }
}

/// All settings from `vaani.conf`. `Default` holds the documented fallback
/// values used when the file is missing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct VaaniConfig {
    pub hotkey: String,
    pub ui_words: u32,
    pub stt_model: String,
    pub stt_fallback_model: String,
    pub llm_model: String,
    pub prefer_device: PreferDevice,
    pub idle_timeout_s: u64,
    /// Quiet time after speech that ends a dictation run, in ms. The same
    /// number as `key_service::vad::DEFAULT_SILENCE_MS`.
    pub end_of_speech_ms: u32,
    /// `spoken = typed` pairs from `[names]`, in file order.
    pub names: Vec<(String, String)>,
    /// `spoken = url` pairs from `[links]`, in file order.
    pub links: Vec<(String, String)>,
}

impl Default for VaaniConfig {
    fn default() -> Self {
        Self {
            hotkey: "SUPER+H".to_owned(),
            ui_words: 4,
            stt_model: "small.en".to_owned(),
            stt_fallback_model: "base.en".to_owned(),
            llm_model: "qwen2.5-1.5B-q4".to_owned(),
            prefer_device: PreferDevice::Auto,
            idle_timeout_s: 120,
            end_of_speech_ms: 2000,
            names: Vec::new(),
            links: Vec::new(),
        }
    }
}

impl VaaniConfig {
    /// Canonical form: parses back to an equal config with zero warnings.
    pub fn to_canonical(&self) -> String {
        let mut s = String::new();
        s.push_str(&format!("hotkey = {}\n", self.hotkey));
        s.push_str(&format!("ui_words = {}\n", self.ui_words));
        s.push_str(&format!("stt_model = {}\n", self.stt_model));
        s.push_str(&format!(
            "stt_fallback_model = {}\n",
            self.stt_fallback_model
        ));
        s.push_str(&format!("llm_model = {}\n", self.llm_model));
        s.push_str(&format!("prefer_device = {}\n", self.prefer_device));
        s.push_str(&format!("idle_timeout_s = {}\n", self.idle_timeout_s));
        s.push_str(&format!(
            "end_of_speech_ms = {}\n",
            self.end_of_speech_ms
        ));
        s.push_str("\n[names]\n");
        for (spoken, typed) in &self.names {
            s.push_str(&format!("{spoken} = {typed}\n"));
        }
        s.push_str("\n[links]\n");
        for (spoken, url) in &self.links {
            s.push_str(&format!("{spoken} = {url}\n"));
        }
        s
    }
}

/// Parse result: the config plus non-fatal warnings (unknown keys, bad
/// values, malformed lines). Never an error — the parser cannot crash.
#[derive(Debug, Default)]
pub struct ParseOutcome {
    pub config: VaaniConfig,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Section {
    Top,
    Names,
    Links,
    Unknown,
}

/// Parse `vaani.conf` text. Unknown keys/sections and bad values produce
/// warnings; the corresponding documented default is kept.
pub fn parse_str(text: &str) -> ParseOutcome {
    let mut out = ParseOutcome::default();
    let mut section = Section::Top;
    for (idx, raw) in text.lines().enumerate() {
        let lineno = idx + 1;
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with(';') {
            continue;
        }
        if line.starts_with('[') && line.ends_with(']') && line.len() >= 2 {
            let name = line[1..line.len() - 1].trim().to_ascii_lowercase();
            section = match name.as_str() {
                "names" => Section::Names,
                "links" => Section::Links,
                _ => {
                    out.warnings.push(format!(
                        "line {lineno}: unknown section [{name}], ignoring its entries"
                    ));
                    Section::Unknown
                }
            };
            continue;
        }
        let Some((k, v)) = line.split_once('=') else {
            out.warnings.push(format!(
                "line {lineno}: ignoring malformed line (no '='): {line}"
            ));
            continue;
        };
        let (key, value) = (k.trim(), v.trim());
        if key.is_empty() || value.is_empty() {
            out.warnings.push(format!(
                "line {lineno}: ignoring entry with empty key/value: {line}"
            ));
            continue;
        }
        match section {
            Section::Names => out.config.names.push((key.to_owned(), value.to_owned())),
            Section::Links => out.config.links.push((key.to_owned(), value.to_owned())),
            Section::Unknown => out.warnings.push(format!(
                "line {lineno}: ignoring entry in unknown section: {line}"
            )),
            Section::Top => set_top(&mut out, lineno, key, value),
        }
    }
    out
}

fn set_top(out: &mut ParseOutcome, lineno: usize, key: &str, value: &str) {
    let cfg = &mut out.config;
    match key {
        "hotkey" => cfg.hotkey = value.to_owned(),
        "ui_words" => match value.parse::<u32>() {
            Ok(n) => cfg.ui_words = n,
            Err(_) => out.warnings.push(format!(
                "line {lineno}: bad ui_words '{value}' (want a positive integer), using default"
            )),
        },
        "stt_model" => cfg.stt_model = value.to_owned(),
        "stt_fallback_model" => cfg.stt_fallback_model = value.to_owned(),
        "llm_model" => cfg.llm_model = value.to_owned(),
        "prefer_device" => match PreferDevice::parse(value) {
            Some(d) => cfg.prefer_device = d,
            None => out.warnings.push(format!(
                "line {lineno}: unknown prefer_device '{value}' (want dgpu|igpu|auto), using default"
            )),
        },
        "idle_timeout_s" => match value.parse::<u64>() {
            Ok(n) => cfg.idle_timeout_s = n,
            Err(_) => out.warnings.push(format!(
                "line {lineno}: bad idle_timeout_s '{value}' (want seconds), using default"
            )),
        },
        "end_of_speech_ms" => match value.parse::<u32>() {
            Ok(n) if n > 0 => cfg.end_of_speech_ms = n,
            _ => out.warnings.push(format!(
                "line {lineno}: bad end_of_speech_ms '{value}' (want ms > 0), using default"
            )),
        },
        _ => out.warnings.push(format!(
            "line {lineno}: unknown key '{key}', ignoring"
        )),
    }
}

/// Load and parse a `vaani.conf` file. A missing file yields the documented
/// defaults with no warnings; an unreadable file yields defaults plus one
/// warning. Never fails.
pub fn load(path: &Path) -> ParseOutcome {
    match std::fs::read_to_string(path) {
        Ok(text) => parse_str(&text),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => ParseOutcome::default(),
        Err(e) => ParseOutcome {
            config: VaaniConfig::default(),
            warnings: vec![format!(
                "cannot read {}: {e}, using defaults",
                path.display()
            )],
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "hotkey = SUPER+H\n\
        ui_words = 4\n\
        stt_model = small.en\n\
        stt_fallback_model = base.en\n\
        llm_model = qwen2.5-1.5B-q4\n\
        prefer_device = auto\n\
        idle_timeout_s = 120\n\
        end_of_speech_ms = 2000\n\
        \n\
        [names]\n\
        saptodeep = Saptodeep Sarkar\n\
        \n\
        [links]\n\
        github = https://github.com/SaptodeepSarkar\n";

    #[test]
    fn sample_parses_to_documented_values() {
        let o = parse_str(SAMPLE);
        assert!(o.warnings.is_empty(), "warnings: {:?}", o.warnings);
        let c = o.config;
        assert_eq!(c.hotkey, "SUPER+H");
        assert_eq!(c.ui_words, 4);
        assert_eq!(c.stt_model, "small.en");
        assert_eq!(c.stt_fallback_model, "base.en");
        assert_eq!(c.llm_model, "qwen2.5-1.5B-q4");
        assert_eq!(c.prefer_device, PreferDevice::Auto);
        assert_eq!(c.idle_timeout_s, 120);
        assert_eq!(c.end_of_speech_ms, 2000);
        assert_eq!(
            c.names,
            vec![("saptodeep".to_owned(), "Saptodeep Sarkar".to_owned())]
        );
        assert_eq!(
            c.links,
            vec![(
                "github".to_owned(),
                "https://github.com/SaptodeepSarkar".to_owned()
            )]
        );
    }

    #[test]
    fn missing_file_gives_defaults_silently() {
        let p = std::env::temp_dir().join("vaani-phase02-missing-test.conf");
        let _ = std::fs::remove_file(&p);
        let o = load(&p);
        assert_eq!(o.config, VaaniConfig::default());
        assert!(o.warnings.is_empty());
    }

    #[test]
    fn unknown_keys_warn_never_crash() {
        let o = parse_str("hotkey = SUPER+J\nnope = 1\n[names]\nfoo = Foo\n[zzz]\na = b\n");
        assert_eq!(o.config.hotkey, "SUPER+J");
        assert_eq!(
            o.config.names,
            vec![("foo".to_owned(), "Foo".to_owned())]
        );
        assert_eq!(o.warnings.len(), 3, "warnings: {:?}", o.warnings);
    }

    #[test]
    fn broken_values_keep_defaults() {
        let o = parse_str(
            "ui_words = lots\nidle_timeout_s = -3\nend_of_speech_ms = soon\nprefer_device = hyper\n=\ngarbage line\n",
        );
        assert_eq!(o.config.ui_words, 4);
        assert_eq!(o.config.idle_timeout_s, 120);
        assert_eq!(o.config.end_of_speech_ms, 2000);
        assert_eq!(o.config.prefer_device, PreferDevice::Auto);
        assert_eq!(o.warnings.len(), 6, "warnings: {:?}", o.warnings);
    }

    #[test]
    fn canonical_round_trips() {
        let mut cfg = parse_str(SAMPLE).config;
        cfg.links
            .push(("search".to_owned(), "https://x.y/?a=b".to_owned()));
        let o = parse_str(&cfg.to_canonical());
        assert!(o.warnings.is_empty(), "warnings: {:?}", o.warnings);
        assert_eq!(o.config, cfg);
        let o = parse_str(&VaaniConfig::default().to_canonical());
        assert!(o.warnings.is_empty());
        assert_eq!(o.config, VaaniConfig::default());
    }
}
