//! Stable boundaries between Vaani's portable pipeline and replaceable engines.
//!
//! Implementations live in platform/runtime crates. These contracts contain
//! no Android, Quickshell, Firebase, or model-runtime types, so a V6 STT or a
//! different formatter can be registered without changing UI code.

use crate::personalization::PersonalizationSnapshot;
use serde::{Deserialize, Serialize};
use std::fmt;
use uuid::Uuid;

pub type SessionId = Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EngineErrorKind {
    Unavailable,
    InvalidInput,
    Permission,
    Runtime,
    Timeout,
    Cancelled,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EngineError {
    pub kind: EngineErrorKind,
    pub message: String,
}

impl EngineError {
    pub fn new(kind: EngineErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }
}

impl fmt::Display for EngineError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.kind, self.message)
    }
}

impl std::error::Error for EngineError {}

impl fmt::Display for EngineErrorKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let name = match self {
            Self::Unavailable => "unavailable",
            Self::InvalidInput => "invalid_input",
            Self::Permission => "permission",
            Self::Runtime => "runtime",
            Self::Timeout => "timeout",
            Self::Cancelled => "cancelled",
        };
        f.write_str(name)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SttPartial {
    pub session_id: SessionId,
    pub text: String,
    pub revision: u64,
    pub is_final: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SttCapabilities {
    pub engine_id: String,
    pub languages: Vec<String>,
    pub streaming: bool,
    pub n_best: bool,
}

/// Streaming speech-to-text boundary. Audio is passed in memory only.
pub trait SttEngine: Send {
    fn capabilities(&self) -> &SttCapabilities;
    fn start(&mut self, session_id: SessionId) -> Result<(), EngineError>;
    fn feed_audio(
        &mut self,
        session_id: SessionId,
        samples: &[f32],
    ) -> Result<Vec<SttPartial>, EngineError>;
    fn finalize(&mut self, session_id: SessionId) -> Result<SttPartial, EngineError>;
    fn cancel(&mut self, session_id: SessionId) -> Result<(), EngineError>;
}

/// Replaceable voice-activity gate. Implementations consume bounded mono
/// blocks and expose only activity/silence decisions to the controller.
pub trait VadEngine: Send {
    fn engine_id(&self) -> &str;
    fn push_block(&mut self, block: &[f32]) -> Result<bool, EngineError>;
    fn is_silence(&self) -> bool;
}

/// Replaceable audio preprocessor. Audio stays in memory and the output is
/// handed to the STT boundary without involving control IPC or shell args.
pub trait DenoiserEngine: Send + Sync {
    fn engine_id(&self) -> &str;
    fn process(&self, samples: &[f32]) -> Result<Vec<f32>, EngineError>;
}

/// Safe no-op denoiser for platforms without an installed preprocessing
/// model. It makes the optional stage explicit without changing audio.
#[derive(Debug, Clone, Copy, Default)]
pub struct NoopDenoiser;

impl DenoiserEngine for NoopDenoiser {
    fn engine_id(&self) -> &str {
        "none"
    }

    fn process(&self, samples: &[f32]) -> Result<Vec<f32>, EngineError> {
        Ok(samples.to_vec())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FormatContext {
    pub application: Option<String>,
    pub language: String,
    #[serde(default)]
    pub personalization: PersonalizationSnapshot,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FormatRequest {
    pub session_id: SessionId,
    pub transcript: String,
    pub context: FormatContext,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct FormatResult {
    pub engine_id: String,
    pub text: String,
    pub changed: bool,
}

pub trait FormatterEngine: Send + Sync {
    fn engine_id(&self) -> &str;
    fn format(&self, request: &FormatRequest) -> Result<FormatResult, EngineError>;
}

pub trait ContextProvider: Send + Sync {
    fn context_for(
        &self,
        application: Option<&str>,
        language: &str,
    ) -> Result<FormatContext, EngineError>;
}

pub trait PersonalizationProvider: Send + Sync {
    fn snapshot(&self) -> Result<PersonalizationSnapshot, EngineError>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum InsertOutcome {
    Inserted,
    Copied { reason: String },
    Unavailable { reason: String },
}

pub trait InsertionAdapter: Send + Sync {
    fn insert(&self, text: &str) -> Result<InsertOutcome, EngineError>;
}

pub trait MetricsProvider: Send + Sync {
    fn record_latency(&self, stage: &str, milliseconds: u64);
    fn record_error(&self, stage: &str, kind: EngineErrorKind);
}

/// CPU-safe formatter fallback. It performs only the deterministic polish
/// rules shared by the runtime; model-backed formatters can replace it behind
/// the same trait without changing the surrounding pipeline.
#[derive(Debug, Clone, Copy, Default)]
pub struct LocalFormatter;

impl FormatterEngine for LocalFormatter {
    fn engine_id(&self) -> &str {
        "local-polish"
    }

    fn format(&self, request: &FormatRequest) -> Result<FormatResult, EngineError> {
        let text = crate::transcript::polish(&request.transcript);
        Ok(FormatResult {
            engine_id: self.engine_id().into(),
            changed: text != request.transcript,
            text,
        })
    }
}

/// Portable text composition boundary. A formatter may be replaced without
/// changing deterministic personalization or any platform insertion adapter.
/// The formatter receives the original request; vocabulary, snippets, and
/// replacements are applied only after its output has passed successfully.
pub struct TextPipeline<F, P> {
    formatter: F,
    personalization: P,
}

impl<F, P> TextPipeline<F, P>
where
    F: FormatterEngine,
    P: PersonalizationProvider,
{
    pub fn new(formatter: F, personalization: P) -> Self {
        Self {
            formatter,
            personalization,
        }
    }

    pub fn process(&self, request: &FormatRequest) -> Result<FormatResult, EngineError> {
        let mut result = self.formatter.format(request)?;
        let snapshot = self.personalization.snapshot()?;
        let rendered = crate::personalization::render(&result.text, &snapshot);
        result.changed |= rendered != result.text;
        result.text = rendered;
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Formatter;
    impl FormatterEngine for Formatter {
        fn engine_id(&self) -> &str {
            "test-formatter"
        }

        fn format(&self, request: &FormatRequest) -> Result<FormatResult, EngineError> {
            Ok(FormatResult {
                engine_id: self.engine_id().into(),
                text: request.transcript.to_string(),
                changed: false,
            })
        }
    }

    struct Personalization;
    impl PersonalizationProvider for Personalization {
        fn snapshot(&self) -> Result<PersonalizationSnapshot, EngineError> {
            Ok(PersonalizationSnapshot {
                vocabulary: vec![crate::personalization::VocabularyEntry {
                    id: "vocab".into(),
                    canonical: "Hyprland".into(),
                    spoken_aliases: vec!["hyper land".into()],
                    category: None,
                    created_at_ms: 0,
                    updated_at_ms: 0,
                }],
                snippets: vec![crate::personalization::Snippet {
                    id: "snippet".into(),
                    trigger: "my GitHub".into(),
                    value: "https://github.com/example/repo".into(),
                    created_at_ms: 0,
                    updated_at_ms: 0,
                }],
                replacements: Vec::new(),
            })
        }
    }

    #[test]
    fn formatter_output_flows_through_deterministic_personalization() {
        let pipeline = TextPipeline::new(Formatter, Personalization);
        let request = FormatRequest {
            session_id: SessionId::new_v4(),
            transcript: "send my github to hyper land".into(),
            context: FormatContext {
                application: None,
                language: "en".into(),
                personalization: PersonalizationSnapshot::default(),
            },
        };
        let result = pipeline.process(&request).unwrap();
        assert_eq!(result.engine_id, "test-formatter");
        assert_eq!(
            result.text,
            "send https://github.com/example/repo to Hyprland"
        );
        assert!(result.changed);
    }

    #[test]
    fn local_formatter_is_a_conservative_offline_fallback() {
        let request = FormatRequest {
            session_id: SessionId::new_v4(),
            transcript: "uh the the browser".into(),
            context: FormatContext {
                application: None,
                language: "en".into(),
                personalization: PersonalizationSnapshot::default(),
            },
        };
        let result = LocalFormatter.format(&request).unwrap();
        assert_eq!(result.engine_id, "local-polish");
        assert_eq!(result.text, "the browser");
        assert!(result.changed);
    }

    #[test]
    fn noop_denoiser_preserves_audio_and_has_stable_identity() {
        let denoiser = NoopDenoiser;
        let samples = [0.0_f32, 0.25, -0.5, 1.0];
        assert_eq!(denoiser.engine_id(), "none");
        assert_eq!(denoiser.process(&samples).unwrap(), samples);
    }
}
