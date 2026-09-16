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
