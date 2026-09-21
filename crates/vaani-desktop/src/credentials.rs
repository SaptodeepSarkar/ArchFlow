//! OS-backed storage for optional Firebase desktop sessions.

use crate::firebase::{FirebaseSession, PersistedFirebaseSession};
use vaani_core::engine::{EngineError, EngineErrorKind};

const SERVICE: &str = "Vaani";

/// Stores only the refreshable Firebase session in the platform credential
/// store: Secret Service on Linux and Windows Credential Manager on Windows.
pub struct SecureSessionStore {
    api_key: String,
    username: String,
}

impl SecureSessionStore {
    pub fn new(project_id: impl Into<String>, api_key: impl Into<String>) -> Self {
        Self {
            api_key: api_key.into(),
            username: format!("firebase-session:{}", project_id.into()),
        }
    }

    pub fn save(&self, session: &FirebaseSession) -> Result<(), EngineError> {
        let payload = serde_json::to_string(&session.persisted()?)
            .map_err(|_| storage_error("could not encode secure session"))?;
        self.entry()?
            .set_password(&payload)
            .map_err(|_| storage_error("could not save secure session"))
    }

    pub fn load(&self) -> Result<Option<FirebaseSession>, EngineError> {
        let payload = match self.entry()?.get_password() {
            Ok(payload) => payload,
            Err(keyring::Error::NoEntry) => return Ok(None),
            Err(_) => return Err(storage_error("could not read secure session")),
        };
        let persisted: PersistedFirebaseSession = serde_json::from_str(&payload)
            .map_err(|_| storage_error("secure session is invalid"))?;
        if persisted.uid.is_empty() || persisted.refresh_token.is_empty() {
            return Err(storage_error("secure session is incomplete"));
        }
        Ok(Some(FirebaseSession::from_persisted(
            self.api_key.clone(),
            persisted,
        )))
    }

    pub fn clear(&self) -> Result<(), EngineError> {
        let _ = self.entry()?.delete_credential();
        Ok(())
    }

    fn entry(&self) -> Result<keyring::Entry, EngineError> {
        keyring::Entry::new(SERVICE, &self.username)
            .map_err(|_| storage_error("platform secure credential store unavailable"))
    }
}

fn storage_error(message: impl Into<String>) -> EngineError {
    EngineError::new(EngineErrorKind::Unavailable, message)
}
