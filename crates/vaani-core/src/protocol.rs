//! Versioned JSON control protocol over Unix socket (newline-delimited).
//! Audio NEVER travels here; audio uses an inherited pipe to the worker.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Request {
    pub protocol_version: u32,
    pub request_id: String,
    #[serde(default)]
    pub session_id: Option<String>,
    pub kind: RequestKind,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "op", content = "args", rename_all = "snake_case")]
pub enum RequestKind {
    Toggle,
    Start,
    Stop,
    Cancel,
    /// Live dictation: commits stabilized words while recording (SUPER+H).
    /// Only stable prefixes are inserted; the trailing tail stays provisional.
    LiveToggle,
    Status,
    Settings,
    Doctor,
    CopyPending,
    RecoverPending,
    DiscardPending,
    Subscribe,
    MicTest { secs: u32 },
    /// Strictly validated single-key config update (whitelisted keys only).
    ConfigSet { key: String, value: String },
    /// Returns current effective configuration as JSON.
    ConfigGet,
    /// Stream cleaned text into the active target via virtual keyboard.
    /// Args: none. Daemon reads transcript from pending/cleaned state.
    Inject,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Response {
    pub protocol_version: u32,
    pub request_id: String,
    #[serde(default)]
    pub session_id: Option<String>,
    pub ok: bool,
    #[serde(default)]
    pub state: Option<String>,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub data: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Event {
    pub protocol_version: u32,
    pub event: String,
    #[serde(default)]
    pub session_id: Option<String>,
    #[serde(default)]
    pub state: Option<String>,
    #[serde(default)]
    pub amplitude: Option<f32>,
    #[serde(default)]
    pub message: Option<String>,
    #[serde(default)]
    pub data: Option<serde_json::Value>,
}

impl Request {
    pub fn new(kind: RequestKind) -> Self {
        Self {
            protocol_version: crate::PROTOCOL_VERSION,
            request_id: uuid::Uuid::new_v4().to_string(),
            session_id: None,
            kind,
        }
    }
    pub fn to_line(&self) -> anyhow::Result<String, serde_json::Error> {
        serde_json::to_string(self).map(|mut s| {
            s.push('\n');
            s
        })
    }
    pub fn validate_line(line: &str) -> Result<Request, String> {
        if line.len() > crate::MAX_CONTROL_BYTES {
            return Err("message too large".into());
        }
        let r: Request =
            serde_json::from_str(line).map_err(|e| format!("malformed message: {e}"))?;
        if r.protocol_version != crate::PROTOCOL_VERSION {
            return Err(format!(
                "incompatible protocol version {}",
                r.protocol_version
            ));
        }
        Ok(r)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip() {
        let r = Request::new(RequestKind::Toggle);
        let line = r.to_line().unwrap();
        let back = Request::validate_line(line.trim_end()).unwrap();
        assert_eq!(back.kind, RequestKind::Toggle);
    }

    #[test]
    fn rejects_bad_version() {
        let s = r#"{"protocol_version":99,"request_id":"x","kind":{"op":"toggle"}}"#;
        assert!(Request::validate_line(s).is_err());
    }

    #[test]
    fn rejects_oversize() {
        let big = "x".repeat(crate::MAX_CONTROL_BYTES + 1);
        assert!(Request::validate_line(&big).is_err());
    }
}
