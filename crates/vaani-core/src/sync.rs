//! Local-first storage and synchronization contracts.
//!
//! A platform database owns the concrete persistence. These records make
//! migrations, deletion, and cloud synchronization explicit without making
//! dictation depend on a network or a particular vendor SDK.

use crate::engine::EngineError;
use crate::personalization::{PersonalizationSnapshot, Replacement, Snippet, VocabularyEntry};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

pub const SYNC_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SyncEntityKind {
    Vocabulary,
    Snippet,
    Replacement,
    Preference,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SyncRecord<T> {
    pub schema_version: u32,
    pub entity: SyncEntityKind,
    pub id: String,
    pub revision: u64,
    pub logical_clock: u64,
    pub writer_device_id: String,
    pub updated_at_ms: i64,
    pub deleted_at_ms: Option<i64>,
    pub value: Option<T>,
}

impl<T> SyncRecord<T> {
    pub fn live(
        entity: SyncEntityKind,
        id: String,
        revision: u64,
        logical_clock: u64,
        writer_device_id: String,
        updated_at_ms: i64,
        value: T,
    ) -> Self {
        Self {
            schema_version: SYNC_SCHEMA_VERSION,
            entity,
            id,
            revision,
            logical_clock,
            writer_device_id,
            updated_at_ms,
            deleted_at_ms: None,
            value: Some(value),
        }
    }

    pub fn tombstone(
        entity: SyncEntityKind,
        id: String,
        revision: u64,
        logical_clock: u64,
        writer_device_id: String,
        deleted_at_ms: i64,
    ) -> Self {
        Self {
            schema_version: SYNC_SCHEMA_VERSION,
            entity,
            id,
            revision,
            logical_clock,
            writer_device_id,
            updated_at_ms: deleted_at_ms,
            deleted_at_ms: Some(deleted_at_ms),
            value: None,
        }
    }

    pub fn is_deleted(&self) -> bool {
        self.deleted_at_ms.is_some()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum PersonalizationRecord {
    Vocabulary(SyncRecord<VocabularyEntry>),
    Snippet(SyncRecord<Snippet>),
    Replacement(SyncRecord<Replacement>),
}

impl PersonalizationRecord {
    pub fn id(&self) -> &str {
        match self {
            Self::Vocabulary(record) => &record.id,
            Self::Snippet(record) => &record.id,
            Self::Replacement(record) => &record.id,
        }
    }

    /// Deterministic merge for one record. A Lamport-style logical clock wins;
    /// device ID and revision break ties, making convergence independent of
    /// wall-clock skew and network arrival order.
    pub fn merge(local: Self, remote: Self) -> Self {
        let local_key = record_key(&local);
        let remote_key = record_key(&remote);
        if remote_key > local_key {
            remote
        } else {
            local
        }
    }

    pub fn into_snapshot(self, snapshot: &mut PersonalizationSnapshot) {
        match self {
            Self::Vocabulary(record) if !record.is_deleted() => {
                if let Some(value) = record.value {
                    snapshot.vocabulary.push(value)
                }
            }
            Self::Snippet(record) if !record.is_deleted() => {
                if let Some(value) = record.value {
                    snapshot.snippets.push(value)
                }
            }
            Self::Replacement(record) if !record.is_deleted() => {
                if let Some(value) = record.value {
                    snapshot.replacements.push(value)
                }
            }
            _ => {}
        }
    }
}

fn record_key(record: &PersonalizationRecord) -> (u64, &str, u64, i64) {
    match record {
        PersonalizationRecord::Vocabulary(r) => (
            r.logical_clock,
            &r.writer_device_id,
            r.revision,
            r.updated_at_ms,
        ),
        PersonalizationRecord::Snippet(r) => (
            r.logical_clock,
            &r.writer_device_id,
            r.revision,
            r.updated_at_ms,
        ),
        PersonalizationRecord::Replacement(r) => (
            r.logical_clock,
            &r.writer_device_id,
            r.revision,
            r.updated_at_ms,
        ),
    }
}

pub trait StorageProvider: Send + Sync {
    fn personalization(&self) -> Result<PersonalizationSnapshot, EngineError>;
    fn upsert(&self, record: PersonalizationRecord) -> Result<(), EngineError>;
    fn tombstone(
        &self,
        entity: SyncEntityKind,
        id: &str,
        revision: u64,
        deleted_at_ms: i64,
    ) -> Result<(), EngineError>;
}

pub trait SyncStorage: StorageProvider {
    fn pending_sync(&self) -> Result<Vec<PersonalizationRecord>, EngineError>;
    fn acknowledge_sync(&self, records: &[PersonalizationRecord]) -> Result<(), EngineError>;
    fn merge_remote(&self, record: PersonalizationRecord) -> Result<(), EngineError>;
}

pub trait SyncProvider: Send + Sync {
    fn push(&self, records: &[PersonalizationRecord]) -> Result<(), EngineError>;
    fn pull(
        &self,
        cursor: Option<&str>,
    ) -> Result<(Vec<PersonalizationRecord>, Option<String>), EngineError>;
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct SyncCycle {
    pub pushed: usize,
    pub pulled: usize,
    pub failed: bool,
    pub cursor: Option<String>,
}

/// Runs one bounded background sync cycle. Local behavior is never gated on
/// this type: a provider failure leaves the outbox intact for a later retry.
pub struct SyncCoordinator<S, P> {
    storage: S,
    provider: P,
    cursor: Mutex<Option<String>>,
}

/// Execute one bounded push/pull cycle against caller-owned components.
/// Platform shells can use this without moving their local repository into a
/// coordinator, while retaining identical outbox and merge semantics.
pub fn run_sync_cycle<S: SyncStorage, P: SyncProvider>(
    storage: &S,
    provider: &P,
    cursor: &mut Option<String>,
) -> Result<SyncCycle, EngineError> {
    let mut cycle = SyncCycle::default();
    let pending = storage.pending_sync()?;
    if !pending.is_empty() {
        if provider.push(&pending).is_err() {
            cycle.failed = true;
            return Ok(cycle);
        }
        storage.acknowledge_sync(&pending)?;
        cycle.pushed = pending.len();
    }
    let (remote, next_cursor) = provider.pull(cursor.as_deref())?;
    for record in remote {
        storage.merge_remote(record)?;
        cycle.pulled += 1;
    }
    *cursor = next_cursor.clone();
    cycle.cursor = next_cursor;
    Ok(cycle)
}

impl<S: SyncStorage, P: SyncProvider> SyncCoordinator<S, P> {
    pub fn new(storage: S, provider: P) -> Self {
        Self {
            storage,
            provider,
            cursor: Mutex::new(None),
        }
    }

    pub fn run_once(&self) -> Result<SyncCycle, EngineError> {
        let mut cursor = self
            .cursor
            .lock()
            .map_err(|_| storage_error("sync cursor lock poisoned"))?
            .clone();
        let cycle = run_sync_cycle(&self.storage, &self.provider, &mut cursor)?;
        *self
            .cursor
            .lock()
            .map_err(|_| storage_error("sync cursor lock poisoned"))? = cursor;
        Ok(cycle)
    }
}

/// A dependency-free local repository for personalization records.
///
/// The file is JSONL, written atomically, and contains only the current
/// version of each record. It is intentionally small: Android can use Room
/// behind the same trait, while Linux/Windows can use this repository before
/// shipping a heavier database dependency.
pub struct JsonlStorage {
    path: PathBuf,
    outbox_path: PathBuf,
    device_id: String,
    state: Mutex<Vec<PersonalizationRecord>>,
    logical_clock: Mutex<u64>,
    outbox: Mutex<Vec<PersonalizationRecord>>,
}

impl JsonlStorage {
    pub fn open(
        path: impl Into<PathBuf>,
        device_id: impl Into<String>,
    ) -> Result<Self, EngineError> {
        let path = path.into();
        let records = if path.exists() {
            read_records(&path)?
        } else {
            Vec::new()
        };
        let outbox_path = path.with_extension("outbox.jsonl");
        let outbox = if outbox_path.exists() {
            read_records(&outbox_path)?
        } else {
            Vec::new()
        };
        let clock = records.iter().map(record_clock).max().unwrap_or(0);
        Ok(Self {
            path,
            outbox_path,
            device_id: device_id.into(),
            state: Mutex::new(records),
            logical_clock: Mutex::new(clock),
            outbox: Mutex::new(outbox),
        })
    }

    /// Return the versioned local records for a control surface. Callers may
    /// filter by entity, but must not bypass the storage provider methods when
    /// mutating records.
    pub fn records(&self) -> Result<Vec<PersonalizationRecord>, EngineError> {
        self.state
            .lock()
            .map(|records| records.clone())
            .map_err(|_| storage_error("state lock poisoned"))
    }

    fn next_clock(&self) -> Result<u64, EngineError> {
        let mut clock = self
            .logical_clock
            .lock()
            .map_err(|_| storage_error("clock lock poisoned"))?;
        *clock = clock.saturating_add(1);
        Ok(*clock)
    }

    fn commit(&self, records: Vec<PersonalizationRecord>) -> Result<(), EngineError> {
        write_records(&self.path, &records)?;
        *self
            .state
            .lock()
            .map_err(|_| storage_error("state lock poisoned"))? = records;
        Ok(())
    }
}

impl StorageProvider for JsonlStorage {
    fn personalization(&self) -> Result<PersonalizationSnapshot, EngineError> {
        let records = self
            .state
            .lock()
            .map_err(|_| storage_error("state lock poisoned"))?;
        let mut snapshot = PersonalizationSnapshot::default();
        for record in records.iter().cloned() {
            record.into_snapshot(&mut snapshot);
        }
        Ok(snapshot)
    }

    fn upsert(&self, record: PersonalizationRecord) -> Result<(), EngineError> {
        let queued = record.clone();
        let mut records = self
            .state
            .lock()
            .map_err(|_| storage_error("state lock poisoned"))?
            .clone();
        if let Some(slot) = records
            .iter_mut()
            .find(|existing| same_record(existing, &record))
        {
            *slot = PersonalizationRecord::merge(slot.clone(), record);
        } else {
            records.push(record);
        }
        self.commit(records)?;
        let mut outbox = self
            .outbox
            .lock()
            .map_err(|_| storage_error("sync outbox lock poisoned"))?;
        outbox.push(queued);
        write_records(&self.outbox_path, &outbox)?;
        Ok(())
    }

    fn tombstone(
        &self,
        entity: SyncEntityKind,
        id: &str,
        revision: u64,
        deleted_at_ms: i64,
    ) -> Result<(), EngineError> {
        let existing = self
            .state
            .lock()
            .map_err(|_| storage_error("state lock poisoned"))?
            .iter()
            .find(|record| record.entity() == entity && record.id() == id)
            .cloned();
        let clock = self.next_clock()?;
        let tombstone = match existing {
            Some(PersonalizationRecord::Vocabulary(_)) => {
                PersonalizationRecord::Vocabulary(SyncRecord::tombstone(
                    entity,
                    id.into(),
                    revision,
                    clock,
                    self.device_id.clone(),
                    deleted_at_ms,
                ))
            }
            Some(PersonalizationRecord::Snippet(_)) => {
                PersonalizationRecord::Snippet(SyncRecord::tombstone(
                    entity,
                    id.into(),
                    revision,
                    clock,
                    self.device_id.clone(),
                    deleted_at_ms,
                ))
            }
            Some(PersonalizationRecord::Replacement(_)) => {
                PersonalizationRecord::Replacement(SyncRecord::tombstone(
                    entity,
                    id.into(),
                    revision,
                    clock,
                    self.device_id.clone(),
                    deleted_at_ms,
                ))
            }
            None => {
                return Err(EngineError::new(
                    crate::engine::EngineErrorKind::InvalidInput,
                    "cannot tombstone an unknown personalization record",
                ))
            }
        };
        self.upsert(tombstone)
    }
}

impl SyncStorage for JsonlStorage {
    fn pending_sync(&self) -> Result<Vec<PersonalizationRecord>, EngineError> {
        Ok(self
            .outbox
            .lock()
            .map_err(|_| storage_error("sync outbox lock poisoned"))?
            .clone())
    }

    fn acknowledge_sync(&self, records: &[PersonalizationRecord]) -> Result<(), EngineError> {
        let mut outbox = self
            .outbox
            .lock()
            .map_err(|_| storage_error("sync outbox lock poisoned"))?;
        outbox.retain(|pending| !records.iter().any(|sent| sent == pending));
        write_records(&self.outbox_path, &outbox)
    }

    fn merge_remote(&self, record: PersonalizationRecord) -> Result<(), EngineError> {
        let mut records = self
            .state
            .lock()
            .map_err(|_| storage_error("state lock poisoned"))?
            .clone();
        if let Some(slot) = records
            .iter_mut()
            .find(|existing| same_record(existing, &record))
        {
            *slot = PersonalizationRecord::merge(slot.clone(), record);
        } else {
            records.push(record);
        }
        self.commit(records)
    }
}

fn same_record(left: &PersonalizationRecord, right: &PersonalizationRecord) -> bool {
    left.entity() == right.entity() && left.id() == right.id()
}
fn record_clock(record: &PersonalizationRecord) -> u64 {
    match record {
        PersonalizationRecord::Vocabulary(r) => r.logical_clock,
        PersonalizationRecord::Snippet(r) => r.logical_clock,
        PersonalizationRecord::Replacement(r) => r.logical_clock,
    }
}

impl PersonalizationRecord {
    fn entity(&self) -> SyncEntityKind {
        match self {
            Self::Vocabulary(r) => r.entity,
            Self::Snippet(r) => r.entity,
            Self::Replacement(r) => r.entity,
        }
    }
}

fn storage_error(message: impl Into<String>) -> EngineError {
    EngineError::new(crate::engine::EngineErrorKind::Runtime, message)
}

fn read_records(path: &Path) -> Result<Vec<PersonalizationRecord>, EngineError> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| storage_error(format!("read personalization store: {e}")))?;
    text.lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| {
            serde_json::from_str(line)
                .map_err(|e| storage_error(format!("invalid personalization record: {e}")))
        })
        .collect()
}

fn write_records(path: &Path, records: &[PersonalizationRecord]) -> Result<(), EngineError> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| storage_error(format!("create personalization directory: {e}")))?;
    }
    let tmp = path.with_extension("tmp");
    let body = records
        .iter()
        .map(|record| {
            serde_json::to_string(record)
                .map_err(|e| storage_error(format!("serialize personalization record: {e}")))
        })
        .collect::<Result<Vec<_>, _>>()?
        .join("\n")
        + if records.is_empty() { "" } else { "\n" };
    std::fs::write(&tmp, body)
        .map_err(|e| storage_error(format!("write personalization store: {e}")))?;
    std::fs::rename(&tmp, path)
        .map_err(|e| storage_error(format!("commit personalization store: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn word(value: &str, updated_at_ms: i64) -> VocabularyEntry {
        VocabularyEntry {
            id: value.into(),
            canonical: value.into(),
            spoken_aliases: vec![],
            category: None,
            created_at_ms: 0,
            updated_at_ms,
        }
    }

    #[test]
    fn tombstones_are_explicit_and_older_remote_values_do_not_win() {
        let local = PersonalizationRecord::Vocabulary(SyncRecord::live(
            SyncEntityKind::Vocabulary,
            "hypr".into(),
            2,
            2,
            "phone".into(),
            20,
            word("Hyprland", 20),
        ));
        let remote = PersonalizationRecord::Vocabulary(SyncRecord::tombstone(
            SyncEntityKind::Vocabulary,
            "hypr".into(),
            3,
            3,
            "laptop".into(),
            30,
        ));
        let merged = PersonalizationRecord::merge(local, remote);
        assert!(matches!(merged, PersonalizationRecord::Vocabulary(record) if record.is_deleted()));
    }

    #[test]
    fn old_tombstone_cannot_delete_newer_value() {
        let live = PersonalizationRecord::Vocabulary(SyncRecord::live(
            SyncEntityKind::Vocabulary,
            "hypr".into(),
            4,
            4,
            "phone".into(),
            40,
            word("Hyprland", 40),
        ));
        let tombstone = PersonalizationRecord::Vocabulary(SyncRecord::tombstone(
            SyncEntityKind::Vocabulary,
            "hypr".into(),
            3,
            3,
            "laptop".into(),
            30,
        ));
        let merged = PersonalizationRecord::merge(live, tombstone);
        assert!(
            matches!(merged, PersonalizationRecord::Vocabulary(record) if !record.is_deleted())
        );
    }

    #[test]
    fn jsonl_storage_persists_and_excludes_tombstones() {
        let path =
            std::env::temp_dir().join(format!("vaani-sync-test-{}.jsonl", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_file(path.with_extension("outbox.jsonl"));
        let store = JsonlStorage::open(&path, "test-device").unwrap();
        let value = word("Vaani", 10);
        store
            .upsert(PersonalizationRecord::Vocabulary(SyncRecord::live(
                SyncEntityKind::Vocabulary,
                "v".into(),
                1,
                1,
                "test-device".into(),
                10,
                value,
            )))
            .unwrap();
        assert_eq!(store.pending_sync().unwrap().len(), 1);
        assert_eq!(store.personalization().unwrap().vocabulary.len(), 1);
        store
            .tombstone(SyncEntityKind::Vocabulary, "v", 2, 20)
            .unwrap();
        assert!(store.personalization().unwrap().vocabulary.is_empty());
        let reopened = JsonlStorage::open(&path, "test-device").unwrap();
        assert!(reopened.personalization().unwrap().vocabulary.is_empty());
        assert_eq!(reopened.pending_sync().unwrap().len(), 2);
        let _ = std::fs::remove_file(path);
        let _ = std::fs::remove_file(reopened.outbox_path);
    }

    struct MockProvider {
        pushed: std::sync::Arc<std::sync::Mutex<usize>>,
        remote: std::sync::Arc<std::sync::Mutex<Vec<PersonalizationRecord>>>,
    }

    impl SyncProvider for MockProvider {
        fn push(&self, records: &[PersonalizationRecord]) -> Result<(), EngineError> {
            *self.pushed.lock().unwrap() += records.len();
            Ok(())
        }

        fn pull(
            &self,
            cursor: Option<&str>,
        ) -> Result<(Vec<PersonalizationRecord>, Option<String>), EngineError> {
            assert!(cursor.is_none());
            Ok((
                std::mem::take(&mut *self.remote.lock().unwrap()),
                Some("cursor-1".into()),
            ))
        }
    }

    #[test]
    fn coordinator_acknowledges_local_edits_and_merges_remote_without_requeue() {
        let path = std::env::temp_dir().join(format!(
            "vaani-coordinator-test-{}.jsonl",
            std::process::id()
        ));
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_file(path.with_extension("outbox.jsonl"));
        let store = JsonlStorage::open(&path, "phone").unwrap();
        store
            .upsert(PersonalizationRecord::Vocabulary(SyncRecord::live(
                SyncEntityKind::Vocabulary,
                "hypr".into(),
                1,
                1,
                "phone".into(),
                1,
                word("Hyprland", 1),
            )))
            .unwrap();
        let pushed = std::sync::Arc::new(std::sync::Mutex::new(0));
        let remote =
            std::sync::Arc::new(std::sync::Mutex::new(vec![PersonalizationRecord::Snippet(
                SyncRecord::live(
                    SyncEntityKind::Snippet,
                    "github".into(),
                    1,
                    2,
                    "laptop".into(),
                    2,
                    Snippet {
                        id: "github".into(),
                        trigger: "my GitHub".into(),
                        value: "https://github.com/example/repo".into(),
                        created_at_ms: 2,
                        updated_at_ms: 2,
                    },
                ),
            )]));
        let coordinator = SyncCoordinator::new(
            store,
            MockProvider {
                pushed: pushed.clone(),
                remote,
            },
        );
        let cycle = coordinator.run_once().unwrap();
        assert_eq!(
            cycle,
            SyncCycle {
                pushed: 1,
                pulled: 1,
                failed: false,
                cursor: Some("cursor-1".into())
            }
        );
        assert_eq!(*pushed.lock().unwrap(), 1);
        let reopened = JsonlStorage::open(&path, "phone").unwrap();
        assert!(reopened.pending_sync().unwrap().is_empty());
        let snapshot = reopened.personalization().unwrap();
        assert_eq!(snapshot.vocabulary[0].canonical, "Hyprland");
        assert_eq!(
            snapshot.snippets[0].value,
            "https://github.com/example/repo"
        );
        let _ = std::fs::remove_file(path);
        let _ = std::fs::remove_file(reopened.outbox_path);
    }
}
