//! Desktop-local personalization repository.
//!
//! This keeps the desktop control center independent of a database vendor.
//! The same versioned JSONL records can later be handed to a remote
//! `SyncProvider`; UI actions are local and immediate.

use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;
use vaani_core::engine::{EngineError, EngineErrorKind};
use vaani_core::personalization::{
    render, PersonalizationSnapshot, Replacement, Snippet, VocabularyEntry,
};
use vaani_core::sync::{
    JsonlStorage, PersonalizationRecord, StorageProvider, SyncEntityKind, SyncRecord,
};

pub struct PersonalizationRepository {
    storage: JsonlStorage,
    device_id: String,
}

impl PersonalizationRepository {
    pub fn open(path: impl AsRef<Path>, device_id: impl Into<String>) -> Result<Self, EngineError> {
        let device_id = device_id.into();
        Ok(Self {
            storage: JsonlStorage::open(path.as_ref().to_path_buf(), device_id.clone())?,
            device_id,
        })
    }

    pub fn snapshot(&self) -> Result<PersonalizationSnapshot, EngineError> {
        self.storage.personalization()
    }

    pub fn render(&self, text: &str) -> Result<String, EngineError> {
        Ok(render(text, &self.snapshot()?))
    }

    pub fn add_vocabulary(
        &self,
        canonical: impl Into<String>,
        aliases: Vec<String>,
        category: Option<String>,
    ) -> Result<String, EngineError> {
        let id = Uuid::new_v4().to_string();
        let now = now_ms()?;
        self.storage
            .upsert(PersonalizationRecord::Vocabulary(SyncRecord::live(
                SyncEntityKind::Vocabulary,
                id.clone(),
                1,
                1,
                self.device_id.clone(),
                now,
                VocabularyEntry {
                    id: id.clone(),
                    canonical: canonical.into(),
                    spoken_aliases: aliases,
                    category,
                    created_at_ms: now,
                    updated_at_ms: now,
                },
            )))?;
        Ok(id)
    }

    pub fn add_snippet(
        &self,
        trigger: impl Into<String>,
        value: impl Into<String>,
    ) -> Result<String, EngineError> {
        let id = Uuid::new_v4().to_string();
        let now = now_ms()?;
        self.storage
            .upsert(PersonalizationRecord::Snippet(SyncRecord::live(
                SyncEntityKind::Snippet,
                id.clone(),
                1,
                1,
                self.device_id.clone(),
                now,
                Snippet {
                    id: id.clone(),
                    trigger: trigger.into(),
                    value: value.into(),
                    created_at_ms: now,
                    updated_at_ms: now,
                },
            )))?;
        Ok(id)
    }

    pub fn add_replacement(
        &self,
        source: impl Into<String>,
        target: impl Into<String>,
    ) -> Result<String, EngineError> {
        let id = Uuid::new_v4().to_string();
        let now = now_ms()?;
        self.storage
            .upsert(PersonalizationRecord::Replacement(SyncRecord::live(
                SyncEntityKind::Replacement,
                id.clone(),
                1,
                1,
                self.device_id.clone(),
                now,
                Replacement {
                    id: id.clone(),
                    source: source.into(),
                    target: target.into(),
                    created_at_ms: now,
                    updated_at_ms: now,
                },
            )))?;
        Ok(id)
    }

    pub fn remove(&self, kind: SyncEntityKind, id: &str, revision: u64) -> Result<(), EngineError> {
        self.storage.tombstone(kind, id, revision, now_ms()?)
    }
}

fn now_ms() -> Result<i64, EngineError> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| EngineError::new(EngineErrorKind::Runtime, "system clock before Unix epoch"))
        .and_then(|duration| {
            i64::try_from(duration.as_millis())
                .map_err(|_| EngineError::new(EngineErrorKind::Runtime, "system clock overflow"))
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn desktop_repository_renders_and_persists_rules() {
        let path = std::env::temp_dir().join(format!(
            "vaani-desktop-personalization-{}.jsonl",
            std::process::id()
        ));
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_file(path.with_extension("outbox.jsonl"));
        let repository = PersonalizationRepository::open(&path, "desktop-test").unwrap();
        let vocabulary_id = repository
            .add_vocabulary(
                "Hyprland",
                vec!["hyper land".into()],
                Some("technical".into()),
            )
            .unwrap();
        let snippet_id = repository
            .add_snippet("my GitHub", "https://github.com/example/repo")
            .unwrap();
        assert_eq!(
            repository.render("my GitHub is hyper land").unwrap(),
            "https://github.com/example/repo is Hyprland"
        );
        repository
            .remove(SyncEntityKind::Snippet, &snippet_id, 2)
            .unwrap();
        assert_eq!(
            repository.render("my GitHub is hyper land").unwrap(),
            "my GitHub is Hyprland"
        );
        repository
            .remove(SyncEntityKind::Vocabulary, &vocabulary_id, 2)
            .unwrap();
        let reopened = PersonalizationRepository::open(&path, "desktop-test").unwrap();
        assert!(reopened
            .render("hyper land")
            .unwrap()
            .contains("hyper land"));
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_file(path.with_extension("outbox.jsonl"));
    }
}
