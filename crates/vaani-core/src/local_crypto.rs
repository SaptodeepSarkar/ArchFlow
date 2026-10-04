//! Local data encryption. A missing/locked keyring never falls back to plaintext.
use aes_gcm::{
    aead::{rand_core::RngCore, Aead, KeyInit, OsRng},
    Aes256Gcm, Nonce,
};
use base64::{engine::general_purpose::STANDARD, Engine};
use fs2::FileExt;
use std::{io::Write, path::Path};

const MAGIC: &[u8] = b"VAANIENC1";

pub fn key(path: &Path) -> anyhow::Result<[u8; 32]> {
    let parent = path
        .parent()
        .ok_or_else(|| anyhow::anyhow!("missing data directory"))?;
    std::fs::create_dir_all(parent)?;
    let lock = private_file(&parent.join("key-init.lock"))?;
    lock.lock_exclusive()?;
    let entry = keyring::Entry::new("org.vaani.local", "personalization-v1")?;
    match entry.get_password() {
        Ok(value) => Ok(STANDARD
            .decode(value)?
            .try_into()
            .map_err(|_| anyhow::anyhow!("invalid data key"))?),
        Err(keyring::Error::NoEntry) => {
            if [path.to_path_buf(), path.with_extension("outbox.jsonl")]
                .iter()
                .any(|p| {
                    std::fs::read(p)
                        .map(|b| b.starts_with(MAGIC))
                        .unwrap_or(false)
                })
            {
                anyhow::bail!("The encrypted data key is missing. Restore your keyring backup; do not replace the data file.");
            }
            let mut key = [0; 32];
            OsRng.fill_bytes(&mut key);
            entry.set_password(&STANDARD.encode(key))?;
            Ok(key)
        }
        Err(_) => {
            anyhow::bail!("Unlock a Secret Service keyring to use encrypted personalization.")
        }
    }
}

pub fn seal(key: &[u8; 32], clear: &[u8]) -> anyhow::Result<Vec<u8>> {
    let mut nonce = [0; 12];
    OsRng.fill_bytes(&mut nonce);
    let cipher = Aes256Gcm::new_from_slice(key).map_err(|_| anyhow::anyhow!("key"))?;
    let body = cipher
        .encrypt(
            Nonce::from_slice(&nonce),
            aes_gcm::aead::Payload {
                msg: clear,
                aad: MAGIC,
            },
        )
        .map_err(|_| anyhow::anyhow!("encryption failed"))?;
    Ok([MAGIC, &nonce, &body].concat())
}

pub fn open(key: &[u8; 32], body: &[u8]) -> anyhow::Result<Vec<u8>> {
    anyhow::ensure!(
        body.len() >= MAGIC.len() + 12 + 16 && body.starts_with(MAGIC),
        "invalid encrypted store"
    );
    Aes256Gcm::new_from_slice(key).map_err(|_| anyhow::anyhow!("key"))?
        .decrypt(Nonce::from_slice(&body[MAGIC.len()..MAGIC.len()+12]), aes_gcm::aead::Payload {msg:&body[MAGIC.len()+12..],aad:MAGIC})
        .map_err(|_| anyhow::anyhow!("Encrypted data authentication failed; preserve the file and restore a verified backup."))
}

pub fn read(path: &Path, key: Option<&[u8; 32]>) -> anyhow::Result<String> {
    let body = std::fs::read(path)?;
    if body.starts_with(MAGIC) {
        Ok(String::from_utf8(open(
            key.ok_or_else(|| anyhow::anyhow!("encrypted store requires keyring"))?,
            &body,
        )?)?)
    } else {
        Ok(String::from_utf8(body)?)
    }
}

fn private_file(path: &Path) -> std::io::Result<std::fs::File> {
    let mut options = std::fs::OpenOptions::new();
    options.create(true).write(true).truncate(false);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options.open(path)
}

pub fn write(path: &Path, clear: &[u8], key: Option<&[u8; 32]>) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let body = match key {
        Some(key) => seal(key, clear)?,
        None => clear.to_vec(),
    };
    let tmp = path.with_extension(format!("{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| {
        let mut file = private_file(&tmp)?;
        file.write_all(&body)?;
        file.sync_all()?;
        if let Some(key) = key {
            anyhow::ensure!(
                open(key, &std::fs::read(&tmp)?)? == clear,
                "verification failed"
            );
        }
        std::fs::rename(&tmp, path)?;
        if let Some(parent) = path.parent() {
            std::fs::File::open(parent)?.sync_all()?;
        }
        Ok(())
    })();
    let _ = std::fs::remove_file(tmp);
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn authenticated_cipher_rejects_corruption_and_wrong_key() {
        let body = seal(&[1; 32], b"private vocabulary").unwrap();
        assert_eq!(open(&[1; 32], &body).unwrap(), b"private vocabulary");
        assert!(open(&[2; 32], &body).is_err());
        let mut damaged = body;
        *damaged.last_mut().unwrap() ^= 1;
        assert!(open(&[1; 32], &damaged).is_err());
    }
}
