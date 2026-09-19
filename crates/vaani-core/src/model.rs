//! Data-driven model package metadata and validation.
//!
//! Filesystem discovery, downloads, and hashing belong to runtime crates. The
//! core owns the portable manifest shape and rejects metadata that could make
//! a package escape its designated model directory.

use serde::{Deserialize, Serialize};
use std::path::Path;

pub const MODEL_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ModelKind {
    Stt,
    Formatter,
    Vad,
    Denoiser,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ModelFile {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ModelManifest {
    pub schema_version: u32,
    pub id: String,
    pub kind: ModelKind,
    pub version: String,
    pub runtime: String,
    pub quantization: Option<String>,
    pub languages: Vec<String>,
    pub files: Vec<ModelFile>,
    pub minimum_ram_mb: u32,
    pub license: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ManifestError {
    MissingField(&'static str),
    UnsupportedSchema(u32),
    InvalidFilePath(String),
    InvalidChecksum(String),
    DuplicateFile(String),
    EmptyFiles,
}

impl std::fmt::Display for ManifestError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MissingField(field) => write!(f, "missing manifest field: {field}"),
            Self::UnsupportedSchema(version) => {
                write!(f, "unsupported model manifest schema: {version}")
            }
            Self::InvalidFilePath(path) => write!(f, "unsafe model file path: {path}"),
            Self::InvalidChecksum(path) => write!(f, "invalid sha256 for model file: {path}"),
            Self::DuplicateFile(path) => write!(f, "duplicate model file: {path}"),
            Self::EmptyFiles => f.write_str("model manifest contains no files"),
        }
    }
}

impl std::error::Error for ManifestError {}

impl ModelManifest {
    pub fn from_json(json: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(json)
    }

    pub fn validate(&self) -> Result<(), ManifestError> {
        if self.schema_version != MODEL_SCHEMA_VERSION {
            return Err(ManifestError::UnsupportedSchema(self.schema_version));
        }
        if self.id.trim().is_empty() {
            return Err(ManifestError::MissingField("id"));
        }
        if self.version.trim().is_empty() {
            return Err(ManifestError::MissingField("version"));
        }
        if self.runtime.trim().is_empty() {
            return Err(ManifestError::MissingField("runtime"));
        }
        if self.languages.is_empty() {
            return Err(ManifestError::MissingField("languages"));
        }
        if self.files.is_empty() {
            return Err(ManifestError::EmptyFiles);
        }

        let mut seen = std::collections::HashSet::new();
        for file in &self.files {
            let path = Path::new(&file.path);
            if file.path.trim().is_empty()
                || path.is_absolute()
                || path.components().any(|component| {
                    matches!(
                        component,
                        std::path::Component::ParentDir
                            | std::path::Component::RootDir
                            | std::path::Component::Prefix(_)
                    )
                })
            {
                return Err(ManifestError::InvalidFilePath(file.path.clone()));
            }
            if !seen.insert(&file.path) {
                return Err(ManifestError::DuplicateFile(file.path.clone()));
            }
            if file.sha256.len() != 64 || !file.sha256.bytes().all(|byte| byte.is_ascii_hexdigit())
            {
                return Err(ManifestError::InvalidChecksum(file.path.clone()));
            }
        }
        Ok(())
    }
}

pub trait ModelRegistry: Send + Sync {
    fn discover(&self) -> Result<Vec<ModelManifest>, ManifestError>;
    fn activate(&self, model_id: &str) -> Result<(), ManifestError>;
}

#[cfg(test)]
mod tests {
    use super::*;

    fn manifest(path: &str) -> ModelManifest {
        ModelManifest {
            schema_version: MODEL_SCHEMA_VERSION,
            id: "vaani-stt-v5".into(),
            kind: ModelKind::Stt,
            version: "5.0.0".into(),
            runtime: "whisper.cpp".into(),
            quantization: Some("q8_0".into()),
            languages: vec!["en".into()],
            files: vec![ModelFile {
                path: path.into(),
                bytes: 42,
                sha256: "a".repeat(64),
            }],
            minimum_ram_mb: 512,
            license: "MIT".into(),
            capabilities: vec!["streaming".into()],
        }
    }

    #[test]
    fn accepts_valid_manifest() {
        assert!(manifest("model.bin").validate().is_ok());
    }

    #[test]
    fn parses_manifest_without_runtime_specific_types() {
        let json = serde_json::to_string(&manifest("model.bin")).unwrap();
        let parsed = ModelManifest::from_json(&json).unwrap();
        assert_eq!(parsed, manifest("model.bin"));
    }

    #[test]
    fn rejects_path_escape_and_bad_checksum() {
        assert_eq!(
            manifest("../model.bin").validate(),
            Err(ManifestError::InvalidFilePath("../model.bin".into()))
        );
        assert_eq!(
            ModelManifest {
                files: vec![ModelFile {
                    path: "model.bin".into(),
                    bytes: 1,
                    sha256: "nope".into()
                }],
                ..manifest("model.bin")
            }
            .validate(),
            Err(ManifestError::InvalidChecksum("model.bin".into()))
        );
    }
}
