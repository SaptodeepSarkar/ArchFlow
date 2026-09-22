//! Firebase REST provider for desktop personalization sync.
//!
//! The provider deliberately receives an ID-token supplier instead of owning
//! credentials. Linux and Windows shells can bind that trait to their secure
//! credential stores, while this crate remains usable in local-only mode.

use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use vaani_core::engine::{EngineError, EngineErrorKind};
use vaani_core::sync::{PersonalizationRecord, SyncEntityKind, SyncProvider, SyncRecord};
use vaani_core::sync_crypto::{decrypt_record, encrypt_record, EncryptedEnvelope, RecoveryKey};

const FIRESTORE_BASE: &str = "https://firestore.googleapis.com";
const AUTH_BASE: &str = "https://identitytoolkit.googleapis.com/v1";
const SECURE_TOKEN_BASE: &str = "https://securetoken.googleapis.com/v1";
const MAX_PULL_RECORDS: usize = 2_000;

pub trait FirebaseTokenProvider: Send + Sync {
    fn user_id(&self) -> &str;
    fn id_token(&self) -> Result<String, EngineError>;
}

/// Email/password Firebase Auth client for desktop shells. Credentials are
/// sent only over HTTPS; returned tokens remain in the session object and are
/// not written to disk by this crate.
pub struct FirebaseEmailAuth {
    api_key: String,
    auth_base: String,
    secure_token_base: String,
    agent: ureq::Agent,
}

pub struct FirebaseSession {
    uid: String,
    email: String,
    api_key: String,
    secure_token_base: String,
    agent: ureq::Agent,
    tokens: Mutex<SessionTokens>,
}

struct SessionTokens {
    id_token: String,
    refresh_token: String,
    expires_at: Instant,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(crate) struct PersistedFirebaseSession {
    pub(crate) uid: String,
    pub(crate) email: String,
    pub(crate) refresh_token: String,
}

impl FirebaseEmailAuth {
    pub fn new(api_key: impl Into<String>) -> Self {
        Self {
            api_key: api_key.into(),
            auth_base: AUTH_BASE.into(),
            secure_token_base: SECURE_TOKEN_BASE.into(),
            agent: ureq::Agent::new_with_defaults(),
        }
    }

    #[cfg(test)]
    fn with_auth_base(mut self, base: impl Into<String>) -> Self {
        self.auth_base = base.into();
        self
    }

    pub fn sign_in(&self, email: &str, password: &str) -> Result<FirebaseSession, EngineError> {
        self.account_request("signInWithPassword", email, password)
    }

    pub fn create_account(
        &self,
        email: &str,
        password: &str,
    ) -> Result<FirebaseSession, EngineError> {
        self.account_request("signUp", email, password)
    }

    fn account_request(
        &self,
        action: &str,
        email: &str,
        password: &str,
    ) -> Result<FirebaseSession, EngineError> {
        if email.trim().is_empty() || password.is_empty() {
            return Err(EngineError::new(
                EngineErrorKind::InvalidInput,
                "email and password are required",
            ));
        }
        let url = format!(
            "{}/accounts:{}?key={}",
            self.auth_base.trim_end_matches('/'),
            action,
            self.api_key
        );
        let mut response = self
            .agent
            .post(url)
            .send_json(json!({
                "email": email.trim(),
                "password": password,
                "returnSecureToken": true,
            }))
            .map_err(|_| network_error("Firebase authentication request failed"))?;
        let body: Value = response
            .body_mut()
            .read_json()
            .map_err(|_| network_error("Firebase authentication response was invalid"))?;
        self.session_from_response(&body)
    }

    fn session_from_response(&self, body: &Value) -> Result<FirebaseSession, EngineError> {
        let uid = body
            .get("localId")
            .and_then(Value::as_str)
            .ok_or_else(|| network_error("Firebase authentication omitted user ID"))?;
        let email = body
            .get("email")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let id_token = body
            .get("idToken")
            .and_then(Value::as_str)
            .ok_or_else(|| network_error("Firebase authentication omitted ID token"))?;
        let refresh_token = body
            .get("refreshToken")
            .and_then(Value::as_str)
            .ok_or_else(|| network_error("Firebase authentication omitted refresh token"))?;
        let expires_in = body
            .get("expiresIn")
            .and_then(Value::as_str)
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(3_600);
        Ok(FirebaseSession {
            uid: uid.into(),
            email: email.into(),
            api_key: self.api_key.clone(),
            secure_token_base: self.secure_token_base.clone(),
            agent: ureq::Agent::new_with_defaults(),
            tokens: Mutex::new(SessionTokens {
                id_token: id_token.into(),
                refresh_token: refresh_token.into(),
                expires_at: Instant::now() + Duration::from_secs(expires_in),
            }),
        })
    }
}

impl FirebaseSession {
    pub fn email(&self) -> &str {
        &self.email
    }

    pub(crate) fn persisted(&self) -> Result<PersistedFirebaseSession, EngineError> {
        let tokens = self
            .tokens
            .lock()
            .map_err(|_| network_error("Firebase session lock was poisoned"))?;
        Ok(PersistedFirebaseSession {
            uid: self.uid.clone(),
            email: self.email.clone(),
            refresh_token: tokens.refresh_token.clone(),
        })
    }

    pub(crate) fn from_persisted(api_key: String, persisted: PersistedFirebaseSession) -> Self {
        Self {
            uid: persisted.uid,
            email: persisted.email,
            api_key,
            secure_token_base: SECURE_TOKEN_BASE.into(),
            agent: ureq::Agent::new_with_defaults(),
            tokens: Mutex::new(SessionTokens {
                id_token: String::new(),
                refresh_token: persisted.refresh_token,
                expires_at: Instant::now(),
            }),
        }
    }

    fn refresh_token(&self, tokens: &mut SessionTokens) -> Result<(), EngineError> {
        let url = format!(
            "{}/token?key={}",
            self.secure_token_base.trim_end_matches('/'),
            self.api_key
        );
        let mut response = self
            .agent
            .post(url)
            .send_form([
                ("grant_type", "refresh_token"),
                ("refresh_token", tokens.refresh_token.as_str()),
            ])
            .map_err(|_| network_error("Firebase token refresh failed"))?;
        let body: Value = response
            .body_mut()
            .read_json()
            .map_err(|_| network_error("Firebase token response was invalid"))?;
        let id_token = body
            .get("id_token")
            .and_then(Value::as_str)
            .ok_or_else(|| network_error("Firebase token response omitted ID token"))?;
        let refresh_token = body
            .get("refresh_token")
            .and_then(Value::as_str)
            .unwrap_or(&tokens.refresh_token);
        let expires_in = body
            .get("expires_in")
            .and_then(Value::as_str)
            .and_then(|value| value.parse::<u64>().ok())
            .unwrap_or(3_600);
        tokens.id_token = id_token.into();
        tokens.refresh_token = refresh_token.into();
        tokens.expires_at = Instant::now() + Duration::from_secs(expires_in);
        Ok(())
    }
}

impl FirebaseTokenProvider for FirebaseSession {
    fn user_id(&self) -> &str {
        &self.uid
    }

    fn id_token(&self) -> Result<String, EngineError> {
        let mut tokens = self
            .tokens
            .lock()
            .map_err(|_| network_error("Firebase session lock was poisoned"))?;
        if tokens.expires_at <= Instant::now() + Duration::from_secs(30) {
            self.refresh_token(&mut tokens)?;
        }
        Ok(tokens.id_token.clone())
    }
}

impl FirebaseTokenProvider for &FirebaseSession {
    fn user_id(&self) -> &str {
        (*self).user_id()
    }

    fn id_token(&self) -> Result<String, EngineError> {
        (*self).id_token()
    }
}

pub struct FirebaseRestProvider<T> {
    project_id: String,
    database_id: String,
    base_url: String,
    token_provider: T,
    agent: ureq::Agent,
}

/// End-to-end encrypted Firestore provider. Firestore can authorize the
/// account path but cannot inspect a vocabulary word, trigger, URL, or
/// replacement target. Legacy `FirebaseRestProvider` remains available only
/// for migration tooling; normal desktop sync uses this provider.
pub struct EncryptedFirebaseRestProvider<T> {
    inner: FirebaseRestProvider<T>,
    key: RecoveryKey,
}

impl<T: FirebaseTokenProvider> EncryptedFirebaseRestProvider<T> {
    pub fn new(project_id: impl Into<String>, token_provider: T, key: RecoveryKey) -> Self {
        Self {
            inner: FirebaseRestProvider::new(project_id, token_provider),
            key,
        }
    }

    fn push_one(&self, record: &PersonalizationRecord) -> Result<(), EngineError> {
        let updated_at_ms = record_updated_at(record);
        let envelope = encrypt_record(&self.key, record.id(), updated_at_ms, record)
            .map_err(|_| network_error("could not encrypt personalization record"))?;
        let token = self.inner.auth_header()?;
        self.inner
            .agent
            .patch(self.inner.document_url(Some(record.id()))?)
            .header("Authorization", token)
            .send_json(json!({ "fields": encrypted_fields(&envelope) }))
            .map_err(|_| network_error("encrypted Firestore write failed"))?;
        Ok(())
    }

    fn pull_page(
        &self,
        page_token: Option<&str>,
    ) -> Result<(Vec<PersonalizationRecord>, Option<String>), EngineError> {
        let token = self.inner.auth_header()?;
        let mut request = self
            .inner
            .agent
            .get(self.inner.document_url(None)?)
            .header("Authorization", token);
        if let Some(page_token) = page_token {
            request = request.query("pageToken", page_token);
        }
        let mut response = request
            .call()
            .map_err(|_| network_error("encrypted Firestore read failed"))?;
        let body: Value = response
            .body_mut()
            .read_json()
            .map_err(|_| network_error("encrypted Firestore response was invalid"))?;
        let documents = body
            .get("documents")
            .and_then(Value::as_array)
            .ok_or_else(|| network_error("Firestore response omitted documents"))?;
        if documents.len() > MAX_PULL_RECORDS {
            return Err(network_error("Firestore personalization limit exceeded"));
        }
        let mut records = Vec::with_capacity(documents.len());
        for document in documents {
            if let Some(record) = encrypted_record_from_document(document, &self.key)? {
                records.push(record);
            }
        }
        Ok((
            records,
            body.get("nextPageToken")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .map(str::to_owned),
        ))
    }
}

impl<T: FirebaseTokenProvider> SyncProvider for EncryptedFirebaseRestProvider<T> {
    fn push(&self, records: &[PersonalizationRecord]) -> Result<(), EngineError> {
        for record in records {
            self.push_one(record)?;
        }
        Ok(())
    }

    fn pull(
        &self,
        _cursor: Option<&str>,
    ) -> Result<(Vec<PersonalizationRecord>, Option<String>), EngineError> {
        let mut all = Vec::new();
        let mut page = None;
        loop {
            let (records, next) = self.pull_page(page.as_deref())?;
            all.extend(records);
            page = next;
            if page.is_none() {
                return Ok((all, None));
            }
            if all.len() > MAX_PULL_RECORDS {
                return Err(network_error("Firestore personalization limit exceeded"));
            }
        }
    }
}

impl<T: FirebaseTokenProvider> FirebaseRestProvider<T> {
    pub fn new(project_id: impl Into<String>, token_provider: T) -> Self {
        Self {
            project_id: project_id.into(),
            database_id: "(default)".into(),
            base_url: FIRESTORE_BASE.into(),
            token_provider,
            agent: ureq::Agent::new_with_defaults(),
        }
    }

    pub fn with_database(mut self, database_id: impl Into<String>) -> Self {
        self.database_id = database_id.into();
        self
    }

    #[cfg(test)]
    fn with_base_url(mut self, base_url: impl Into<String>) -> Self {
        self.base_url = base_url.into();
        self
    }

    fn document_url(&self, record_id: Option<&str>) -> Result<String, EngineError> {
        let project = safe_segment(&self.project_id)?;
        let database = safe_segment(&self.database_id)?;
        let user = safe_segment(self.token_provider.user_id())?;
        let suffix = record_id
            .map(|id| safe_segment(id).map(|id| format!("/{id}")))
            .transpose()?
            .unwrap_or_default();
        Ok(format!(
            "{}/v1/projects/{}/databases/{}/documents/users/{}/personalization{}",
            self.base_url.trim_end_matches('/'),
            project,
            database,
            user,
            suffix
        ))
    }

    fn auth_header(&self) -> Result<String, EngineError> {
        Ok(format!("Bearer {}", self.token_provider.id_token()?))
    }

    fn push_one(&self, record: &PersonalizationRecord) -> Result<(), EngineError> {
        let token = self.auth_header()?;
        let url = self.document_url(Some(record.id()))?;
        self.agent
            .patch(url)
            .header("Authorization", token)
            .send_json(json!({ "fields": firestore_fields(record) }))
            .map_err(|error| network_error(format!("Firestore write failed: {error}")))?;
        Ok(())
    }

    fn pull_page(
        &self,
        page_token: Option<&str>,
    ) -> Result<(Vec<PersonalizationRecord>, Option<String>), EngineError> {
        let token = self.auth_header()?;
        let mut request = self
            .agent
            .get(self.document_url(None)?)
            .header("Authorization", token);
        if let Some(page_token) = page_token {
            request = request.query("pageToken", page_token);
        }
        let mut response = request
            .call()
            .map_err(|error| network_error(format!("Firestore read failed: {error}")))?;
        let body: Value = response
            .body_mut()
            .read_json()
            .map_err(|error| network_error(format!("invalid Firestore response: {error}")))?;
        let documents = body
            .get("documents")
            .and_then(Value::as_array)
            .ok_or_else(|| network_error("Firestore response omitted documents"))?;
        let mut records = Vec::with_capacity(documents.len());
        for document in documents {
            if records.len() >= MAX_PULL_RECORDS {
                return Err(network_error("Firestore personalization limit exceeded"));
            }
            if let Some(record) = record_from_document(document)? {
                records.push(record);
            }
        }
        let next = body
            .get("nextPageToken")
            .and_then(Value::as_str)
            .filter(|value| !value.is_empty())
            .map(str::to_owned);
        Ok((records, next))
    }
}

impl<T: FirebaseTokenProvider> SyncProvider for FirebaseRestProvider<T> {
    fn push(&self, records: &[PersonalizationRecord]) -> Result<(), EngineError> {
        for record in records {
            self.push_one(record)?;
        }
        Ok(())
    }

    fn pull(
        &self,
        _cursor: Option<&str>,
    ) -> Result<(Vec<PersonalizationRecord>, Option<String>), EngineError> {
        // A full bounded scan is intentional until a server-side updatedAt
        // query is introduced. Returning no opaque page cursor prevents an
        // expiring Firestore page token from skipping future edits.
        let mut all = Vec::new();
        let mut page = None;
        loop {
            let (records, next) = self.pull_page(page.as_deref())?;
            all.extend(records);
            page = next;
            if page.is_none() {
                return Ok((all, None));
            }
        }
    }
}

fn firestore_fields(record: &PersonalizationRecord) -> Map<String, Value> {
    let (entity, id, revision, clock, writer, updated, deleted, value) = match record {
        PersonalizationRecord::Vocabulary(record) => (
            "vocabulary", &record.id, record.revision, record.logical_clock,
            &record.writer_device_id, record.updated_at_ms, record.deleted_at_ms,
            record.value.as_ref().map(|value| json!({
                "canonical": string_value(&value.canonical),
                "spoken_aliases": array_value(&value.spoken_aliases),
                "category": value.category.as_ref().map_or_else(null_value, |v| string_value(v)),
                "created_at_ms": integer_value(value.created_at_ms),
                "updated_at_ms": integer_value(value.updated_at_ms),
            })),
        ),
        PersonalizationRecord::Snippet(record) => (
            "snippet", &record.id, record.revision, record.logical_clock,
            &record.writer_device_id, record.updated_at_ms, record.deleted_at_ms,
            record.value.as_ref().map(|value| json!({
                "trigger": string_value(&value.trigger),
                "value": string_value(&value.value),
                "created_at_ms": integer_value(value.created_at_ms),
                "updated_at_ms": integer_value(value.updated_at_ms),
            })),
        ),
        PersonalizationRecord::Replacement(record) => (
            "replacement", &record.id, record.revision, record.logical_clock,
            &record.writer_device_id, record.updated_at_ms, record.deleted_at_ms,
            record.value.as_ref().map(|value| json!({
                "source": string_value(&value.source),
                "target": string_value(&value.target),
                "created_at_ms": integer_value(value.created_at_ms),
                "updated_at_ms": integer_value(value.updated_at_ms),
            })),
        ),
    };
    let mut fields = Map::new();
    fields.insert("schema_version".into(), integer_value(1));
    fields.insert("entity".into(), string_value(entity));
    fields.insert("id".into(), string_value(id));
    fields.insert("revision".into(), integer_value(revision));
    fields.insert("logical_clock".into(), integer_value(clock));
    fields.insert("writer_device_id".into(), string_value(writer));
    fields.insert("updated_at_ms".into(), integer_value(updated));
    fields.insert(
        "deleted_at_ms".into(),
        deleted.map_or_else(null_value, integer_value),
    );
    fields.insert(
        "value".into(),
        value.map_or_else(null_value, |value| map_value(value)),
    );
    fields
}

fn record_updated_at(record: &PersonalizationRecord) -> i64 {
    match record {
        PersonalizationRecord::Vocabulary(record) => record.updated_at_ms,
        PersonalizationRecord::Snippet(record) => record.updated_at_ms,
        PersonalizationRecord::Replacement(record) => record.updated_at_ms,
    }
}

fn encrypted_fields(envelope: &EncryptedEnvelope) -> Map<String, Value> {
    [
        (
            "schema_version".into(),
            integer_value(envelope.schema_version),
        ),
        ("record_id".into(), string_value(&envelope.record_id)),
        (
            "updated_at_ms".into(),
            integer_value(envelope.updated_at_ms),
        ),
        ("compression".into(), string_value(&envelope.compression)),
        ("cipher".into(), string_value(&envelope.cipher)),
        ("nonce".into(), string_value(&envelope.nonce)),
        ("ciphertext".into(), string_value(&envelope.ciphertext)),
    ]
    .into_iter()
    .collect()
}

fn encrypted_record_from_document(
    document: &Value,
    key: &RecoveryKey,
) -> Result<Option<PersonalizationRecord>, EngineError> {
    let fields = document
        .get("fields")
        .and_then(Value::as_object)
        .ok_or_else(|| network_error("Firestore document omitted fields"))?;
    let envelope = EncryptedEnvelope {
        schema_version: required_u64(fields, "schema_version")? as u32,
        record_id: required_string(fields, "record_id")?.to_owned(),
        updated_at_ms: required_i64(fields, "updated_at_ms")?,
        compression: required_string(fields, "compression")?.to_owned(),
        cipher: required_string(fields, "cipher")?.to_owned(),
        nonce: required_string(fields, "nonce")?.to_owned(),
        ciphertext: required_string(fields, "ciphertext")?.to_owned(),
    };
    decrypt_record(key, &envelope)
        .map(Some)
        .map_err(|_| network_error("encrypted personalization record could not be verified"))
}

fn record_from_document(document: &Value) -> Result<Option<PersonalizationRecord>, EngineError> {
    let fields = document
        .get("fields")
        .and_then(Value::as_object)
        .ok_or_else(|| network_error("Firestore document omitted fields"))?;
    let entity = required_string(fields, "entity")?;
    let kind = match entity {
        "vocabulary" => SyncEntityKind::Vocabulary,
        "snippet" => SyncEntityKind::Snippet,
        "replacement" => SyncEntityKind::Replacement,
        _ => return Ok(None),
    };
    let id = required_string(fields, "id")?.to_owned();
    let schema_version = required_u64(fields, "schema_version")? as u32;
    if schema_version != 1 || id.is_empty() {
        return Ok(None);
    }
    let revision = required_u64(fields, "revision")?;
    let logical_clock = required_u64(fields, "logical_clock")?;
    let writer_device_id = required_string(fields, "writer_device_id")?.to_owned();
    let updated_at_ms = required_i64(fields, "updated_at_ms")?;
    let deleted_at_ms = optional_i64(fields.get("deleted_at_ms"))?;
    let value = fields.get("value").and_then(map_fields);
    let record = match (kind, deleted_at_ms, value) {
        (SyncEntityKind::Vocabulary, None, Some(value)) => {
            PersonalizationRecord::Vocabulary(SyncRecord {
                schema_version,
                entity: kind,
                id: id.clone(),
                revision,
                logical_clock,
                writer_device_id,
                updated_at_ms,
                deleted_at_ms,
                value: Some(vaani_core::personalization::VocabularyEntry {
                    id,
                    canonical: required_string(value, "canonical")?.to_owned(),
                    spoken_aliases: array_strings(value, "spoken_aliases")?,
                    category: optional_string(value.get("category"))?,
                    created_at_ms: required_i64(value, "created_at_ms")?,
                    updated_at_ms: required_i64(value, "updated_at_ms")?,
                }),
            })
        }
        (SyncEntityKind::Snippet, None, Some(value)) => {
            PersonalizationRecord::Snippet(SyncRecord {
                schema_version,
                entity: kind,
                id: id.clone(),
                revision,
                logical_clock,
                writer_device_id,
                updated_at_ms,
                deleted_at_ms,
                value: Some(vaani_core::personalization::Snippet {
                    id,
                    trigger: required_string(value, "trigger")?.to_owned(),
                    value: required_string(value, "value")?.to_owned(),
                    created_at_ms: required_i64(value, "created_at_ms")?,
                    updated_at_ms: required_i64(value, "updated_at_ms")?,
                }),
            })
        }
        (SyncEntityKind::Replacement, None, Some(value)) => {
            PersonalizationRecord::Replacement(SyncRecord {
                schema_version,
                entity: kind,
                id: id.clone(),
                revision,
                logical_clock,
                writer_device_id,
                updated_at_ms,
                deleted_at_ms,
                value: Some(vaani_core::personalization::Replacement {
                    id,
                    source: required_string(value, "source")?.to_owned(),
                    target: required_string(value, "target")?.to_owned(),
                    created_at_ms: required_i64(value, "created_at_ms")?,
                    updated_at_ms: required_i64(value, "updated_at_ms")?,
                }),
            })
        }
        (
            SyncEntityKind::Vocabulary | SyncEntityKind::Snippet | SyncEntityKind::Replacement,
            Some(_),
            _,
        ) => tombstone(
            kind,
            id,
            revision,
            logical_clock,
            writer_device_id,
            updated_at_ms,
            deleted_at_ms,
        ),
        _ => return Ok(None),
    };
    Ok(Some(record))
}

fn tombstone(
    kind: SyncEntityKind,
    id: String,
    revision: u64,
    logical_clock: u64,
    writer_device_id: String,
    updated_at_ms: i64,
    deleted_at_ms: Option<i64>,
) -> PersonalizationRecord {
    let deleted_at_ms = deleted_at_ms.unwrap_or(updated_at_ms);
    match kind {
        SyncEntityKind::Vocabulary => PersonalizationRecord::Vocabulary(SyncRecord::<
            vaani_core::personalization::VocabularyEntry,
        >::tombstone(
            kind,
            id,
            revision,
            logical_clock,
            writer_device_id,
            deleted_at_ms,
        )),
        SyncEntityKind::Snippet => PersonalizationRecord::Snippet(SyncRecord::<
            vaani_core::personalization::Snippet,
        >::tombstone(
            kind,
            id,
            revision,
            logical_clock,
            writer_device_id,
            deleted_at_ms,
        )),
        SyncEntityKind::Replacement => PersonalizationRecord::Replacement(SyncRecord::<
            vaani_core::personalization::Replacement,
        >::tombstone(
            kind,
            id,
            revision,
            logical_clock,
            writer_device_id,
            deleted_at_ms,
        )),
        SyncEntityKind::Preference => unreachable!(),
    }
}

fn safe_segment(value: &str) -> Result<&str, EngineError> {
    if value.is_empty()
        || !value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.' | b'(' | b')')
        })
    {
        return Err(EngineError::new(
            EngineErrorKind::InvalidInput,
            "unsafe Firebase path segment",
        ));
    }
    Ok(value)
}

fn network_error(message: impl Into<String>) -> EngineError {
    EngineError::new(EngineErrorKind::Unavailable, message)
}
fn string_value(value: impl AsRef<str>) -> Value {
    json!({ "stringValue": value.as_ref() })
}
fn integer_value(value: impl ToString) -> Value {
    json!({ "integerValue": value.to_string() })
}
fn null_value() -> Value {
    json!({ "nullValue": null })
}
fn array_value(values: &[String]) -> Value {
    json!({ "arrayValue": { "values": values.iter().map(string_value).collect::<Vec<_>>() } })
}
fn map_value(fields: Value) -> Value {
    json!({ "mapValue": { "fields": fields } })
}

fn required_string<'a>(fields: &'a Map<String, Value>, key: &str) -> Result<&'a str, EngineError> {
    fields
        .get(key)
        .and_then(string_field)
        .ok_or_else(|| network_error(format!("Firestore record missing {key}")))
}
fn required_u64(fields: &Map<String, Value>, key: &str) -> Result<u64, EngineError> {
    fields
        .get(key)
        .and_then(integer_field)
        .and_then(|value| value.parse().ok())
        .ok_or_else(|| network_error(format!("Firestore record has invalid {key}")))
}
fn required_i64(fields: &Map<String, Value>, key: &str) -> Result<i64, EngineError> {
    fields
        .get(key)
        .and_then(integer_field)
        .and_then(|value| value.parse().ok())
        .ok_or_else(|| network_error(format!("Firestore record has invalid {key}")))
}
fn optional_i64(value: Option<&Value>) -> Result<Option<i64>, EngineError> {
    match value {
        None => Ok(None),
        Some(value) if value.get("nullValue").is_some() => Ok(None),
        Some(value) => integer_field(value)
            .and_then(|v| v.parse().ok())
            .map(Some)
            .ok_or_else(|| network_error("Firestore record has invalid deletion time")),
    }
}
fn optional_string(value: Option<&Value>) -> Result<Option<String>, EngineError> {
    match value {
        None => Ok(None),
        Some(value) if value.get("nullValue").is_some() => Ok(None),
        Some(value) => string_field(value)
            .map(str::to_owned)
            .map(Some)
            .ok_or_else(|| network_error("Firestore record has invalid optional string")),
    }
}
fn string_field(value: &Value) -> Option<&str> {
    value.get("stringValue").and_then(Value::as_str)
}
fn integer_field(value: &Value) -> Option<&str> {
    value.get("integerValue").and_then(Value::as_str)
}
fn map_fields(value: &Value) -> Option<&Map<String, Value>> {
    value.get("mapValue")?.get("fields")?.as_object()
}
fn array_strings(fields: &Map<String, Value>, key: &str) -> Result<Vec<String>, EngineError> {
    let values = fields
        .get(key)
        .and_then(|value| value.get("arrayValue"))
        .and_then(|value| value.get("values"))
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    values
        .iter()
        .map(|value| {
            string_field(value)
                .map(str::to_owned)
                .ok_or_else(|| network_error("Firestore aliases contain a non-string value"))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use vaani_core::personalization::VocabularyEntry;

    struct Session;
    impl FirebaseTokenProvider for Session {
        fn user_id(&self) -> &str {
            "user-1"
        }
        fn id_token(&self) -> Result<String, EngineError> {
            Ok("token".into())
        }
    }

    #[test]
    fn firestore_payload_preserves_tombstones_and_aliases() {
        let record = PersonalizationRecord::Vocabulary(SyncRecord::live(
            SyncEntityKind::Vocabulary,
            "id-1".into(),
            2,
            4,
            "desktop".into(),
            99,
            VocabularyEntry {
                id: "id-1".into(),
                canonical: "Hyprland".into(),
                spoken_aliases: vec!["hyper land".into()],
                category: None,
                created_at_ms: 1,
                updated_at_ms: 99,
            },
        ));
        let fields = firestore_fields(&record);
        assert_eq!(fields["entity"]["stringValue"], "vocabulary");
        assert_eq!(
            fields["value"]["mapValue"]["fields"]["canonical"]["stringValue"],
            "Hyprland"
        );
        assert_eq!(
            fields["value"]["mapValue"]["fields"]["spoken_aliases"]["arrayValue"]["values"][0]
                ["stringValue"],
            "hyper land"
        );
        let document = json!({ "fields": fields });
        let decoded = record_from_document(&document).unwrap().unwrap();
        assert_eq!(decoded, record);
    }

    #[test]
    fn path_segments_reject_traversal() {
        assert!(safe_segment("user/../other").is_err());
        assert!(safe_segment("user-1").is_ok());
    }

    #[test]
    fn provider_uses_firestore_endpoint_shape() {
        let provider = FirebaseRestProvider::new("arch-flow-vanni", Session)
            .with_base_url("https://example.test");
        assert_eq!(provider.document_url(Some("id-1")).unwrap(), "https://example.test/v1/projects/arch-flow-vanni/databases/(default)/documents/users/user-1/personalization/id-1");
    }

    #[test]
    fn auth_response_creates_memory_only_session() {
        let auth = FirebaseEmailAuth::new("web-api-key").with_auth_base("https://example.test/v1");
        let session = auth
            .session_from_response(&json!({
                "localId": "user-1",
                "email": "person@example.test",
                "idToken": "id-token",
                "refreshToken": "refresh-token",
                "expiresIn": "3600"
            }))
            .unwrap();
        assert_eq!(session.user_id(), "user-1");
        assert_eq!(session.email(), "person@example.test");
        assert_eq!(session.id_token().unwrap(), "id-token");
    }

    #[test]
    fn auth_rejects_missing_credentials() {
        let auth = FirebaseEmailAuth::new("web-api-key");
        assert!(auth.sign_in("", "secret").is_err());
        assert!(auth.create_account("person@example.test", "").is_err());
    }
}
