//! Portable end-to-end encrypted sync envelopes.
//!
//! Firestore sees only an encrypted, compressed JSON record and non-sensitive
//! routing metadata. The 256-bit recovery key is generated on the first
//! trusted device, stored in that platform's secure key store, and is needed
//! to enrol another device. It is never derived from a Firebase password.

use aes_gcm::aead::{rand_core::RngCore, Aead, KeyInit, OsRng};
use aes_gcm::{Aes256Gcm, Nonce};
use base64::engine::general_purpose::URL_SAFE_NO_PAD;
use base64::Engine;
use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use flate2::Compression;
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};

pub const SYNC_CIPHER_SCHEMA: u32 = 1;
const AAD_PREFIX: &str = "vaani-sync-envelope-v1:";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RecoveryKey([u8; 32]);

impl RecoveryKey {
    pub fn generate() -> Result<Self, SyncCryptoError> {
        let mut material = [0u8; 32];
        OsRng.fill_bytes(&mut material);
        Ok(Self(material))
    }

    /// Human-transferable form for a QR code or recovery-code screen.
    pub fn export(&self) -> String {
        format!("VSK1-{}", URL_SAFE_NO_PAD.encode(self.0))
    }

    pub fn import(value: &str) -> Result<Self, SyncCryptoError> {
        let encoded = value
            .trim()
            .strip_prefix("VSK1-")
            .ok_or(SyncCryptoError::Key)?;
        let bytes = URL_SAFE_NO_PAD
            .decode(encoded)
            .map_err(|_| SyncCryptoError::Key)?;
        let material: [u8; 32] = bytes.try_into().map_err(|_| SyncCryptoError::Key)?;
        Ok(Self(material))
    }

    pub fn as_bytes(&self) -> &[u8; 32] {
        &self.0
    }
}

/// The complete value stored beneath a user's Firestore `sync` collection.
/// `record_id` and timestamps stay outside encryption solely to support
/// convergence and bounded queries; user words and URLs are ciphertext.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct EncryptedEnvelope {
    pub schema_version: u32,
    pub record_id: String,
    pub updated_at_ms: i64,
    pub compression: String,
    pub cipher: String,
    pub nonce: String,
    pub ciphertext: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SyncCryptoError {
    Key,
    Randomness,
    Serialize,
    Compress,
    Encrypt,
    Decrypt,
    Decompress,
    Deserialize,
    InvalidEnvelope,
}

impl std::fmt::Display for SyncCryptoError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("encrypted sync data could not be processed")
    }
}

impl std::error::Error for SyncCryptoError {}

pub fn encrypt_record<T: Serialize>(
    key: &RecoveryKey,
    record_id: &str,
    updated_at_ms: i64,
    value: &T,
) -> Result<EncryptedEnvelope, SyncCryptoError> {
    if record_id.is_empty() || record_id.len() > 128 {
        return Err(SyncCryptoError::InvalidEnvelope);
    }
    let serialized = serde_json::to_vec(value).map_err(|_| SyncCryptoError::Serialize)?;
    let mut compressor = GzEncoder::new(Vec::new(), Compression::default());
    compressor
        .write_all(&serialized)
        .map_err(|_| SyncCryptoError::Compress)?;
    let compressed = compressor.finish().map_err(|_| SyncCryptoError::Compress)?;
    let mut nonce_bytes = [0u8; 12];
    OsRng.fill_bytes(&mut nonce_bytes);
    let cipher = Aes256Gcm::new_from_slice(key.as_bytes()).map_err(|_| SyncCryptoError::Key)?;
    let ciphertext = cipher
        .encrypt(
            Nonce::from_slice(&nonce_bytes),
            aes_gcm::aead::Payload {
                msg: &compressed,
                aad: associated_data(record_id).as_bytes(),
            },
        )
        .map_err(|_| SyncCryptoError::Encrypt)?;
    Ok(EncryptedEnvelope {
        schema_version: SYNC_CIPHER_SCHEMA,
        record_id: record_id.into(),
        updated_at_ms,
        compression: "gzip".into(),
        cipher: "aes-256-gcm".into(),
        nonce: URL_SAFE_NO_PAD.encode(nonce_bytes),
        ciphertext: URL_SAFE_NO_PAD.encode(ciphertext),
    })
}

pub fn decrypt_record<T: for<'a> Deserialize<'a>>(
    key: &RecoveryKey,
    envelope: &EncryptedEnvelope,
) -> Result<T, SyncCryptoError> {
    if envelope.schema_version != SYNC_CIPHER_SCHEMA
        || envelope.compression != "gzip"
        || envelope.cipher != "aes-256-gcm"
        || envelope.record_id.is_empty()
    {
        return Err(SyncCryptoError::InvalidEnvelope);
    }
    let nonce = URL_SAFE_NO_PAD
        .decode(&envelope.nonce)
        .map_err(|_| SyncCryptoError::InvalidEnvelope)?;
    let nonce: [u8; 12] = nonce
        .try_into()
        .map_err(|_| SyncCryptoError::InvalidEnvelope)?;
    let ciphertext = URL_SAFE_NO_PAD
        .decode(&envelope.ciphertext)
        .map_err(|_| SyncCryptoError::InvalidEnvelope)?;
    let cipher = Aes256Gcm::new_from_slice(key.as_bytes()).map_err(|_| SyncCryptoError::Key)?;
    let compressed = cipher
        .decrypt(
            Nonce::from_slice(&nonce),
            aes_gcm::aead::Payload {
                msg: &ciphertext,
                aad: associated_data(&envelope.record_id).as_bytes(),
            },
        )
        .map_err(|_| SyncCryptoError::Decrypt)?;
    let mut decoder = GzDecoder::new(compressed.as_slice());
    let mut serialized = Vec::new();
    decoder
        .read_to_end(&mut serialized)
        .map_err(|_| SyncCryptoError::Decompress)?;
    serde_json::from_slice(&serialized).map_err(|_| SyncCryptoError::Deserialize)
}

fn associated_data(record_id: &str) -> String {
    format!("{AAD_PREFIX}{record_id}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::sync::PersonalizationRecord;

    #[test]
    fn recovery_key_round_trips_without_using_an_account_password() {
        let key = RecoveryKey::generate().unwrap();
        assert_eq!(RecoveryKey::import(&key.export()).unwrap(), key);
    }

    #[test]
    fn encrypted_envelope_round_trips_and_rejects_tampering() {
        let key = RecoveryKey::generate().unwrap();
        let mut envelope = encrypt_record(
            &key,
            "record-1",
            42,
            &vec!["my github", "https://example.test"],
        )
        .unwrap();
        let clear: Vec<String> = decrypt_record(&key, &envelope).unwrap();
        assert_eq!(clear[1], "https://example.test");
        envelope.record_id = "record-2".into();
        assert_eq!(
            decrypt_record::<Vec<String>>(&key, &envelope),
            Err(SyncCryptoError::Decrypt)
        );
    }

    #[test]
    fn android_personalization_record_shape_is_portable() {
        // This is the JSON generated by Android's PersonalizationStore before
        // it is gzip-compressed and encrypted. Keep the cross-platform format
        // explicit: outer enum variants are PascalCase, inner entity values
        // follow SyncEntityKind's snake_case serde representation.
        let android_record = serde_json::json!({
            "Replacement": {
                "schema_version": 1,
                "entity": "replacement",
                "id": "android-rule-1",
                "revision": 1,
                "logical_clock": 1727000000000u64,
                "writer_device_id": "android-device",
                "updated_at_ms": 1727000000000i64,
                "deleted_at_ms": null,
                "value": {
                    "id": "android-rule-1",
                    "source": "my github",
                    "target": "https://github.com/SaptodeepSarkar/ArchFlow",
                    "created_at_ms": 1727000000000i64,
                    "updated_at_ms": 1727000000000i64
                }
            }
        });
        let key = RecoveryKey::generate().unwrap();
        let envelope =
            encrypt_record(&key, "android-rule-1", 1727000000000, &android_record).unwrap();
        let clear: PersonalizationRecord = decrypt_record(&key, &envelope).unwrap();
        assert_eq!(clear.id(), "android-rule-1");
    }
}
