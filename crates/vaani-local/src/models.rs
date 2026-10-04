//! Verified model packs. No model is loaded by installation or app launch.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    io::{Read, Write},
    path::Path,
    sync::atomic::{AtomicBool, Ordering},
};
#[derive(Clone, Serialize, Deserialize)]
pub struct Asset {
    pub id: String,
    pub kind: String,
    pub filename: String,
    pub url: String,
    pub sha256: String,
    pub bytes: u64,
    pub license: String,
}
pub fn validate_asset(asset: &Asset) -> anyhow::Result<()> {
    anyhow::ensure!(
        matches!(asset.kind.as_str(), "stt" | "formatter" | "formatter_v6")
            && asset.filename.len() < 128
            && !asset.filename.contains(['/', '\\'])
            && !asset.filename.starts_with('.')
            && asset.sha256.len() == 64
            && asset.sha256.bytes().all(|c| c.is_ascii_hexdigit())
            && asset.bytes > 0
            && asset.bytes <= 4 * 1024 * 1024 * 1024
            && !asset.license.trim().is_empty(),
        "Invalid model catalog entry"
    );
    Ok(())
}
pub fn install<R: Read>(
    asset: &Asset,
    mut reader: R,
    root: &Path,
    cancel: &AtomicBool,
    mut progress: impl FnMut(u64),
) -> anyhow::Result<std::path::PathBuf> {
    validate_asset(asset)?;
    let dir = root.join(&asset.kind);
    std::fs::create_dir_all(&dir)?;
    let path = dir.join(&asset.filename);
    let tmp = dir.join(format!(".{}.part", uuid::Uuid::new_v4()));
    let result = (|| {
        let mut output = std::fs::File::create(&tmp)?;
        let mut hash = Sha256::new();
        let mut count = 0;
        let mut buffer = [0; 65536];
        loop {
            anyhow::ensure!(!cancel.load(Ordering::Relaxed), "Download cancelled");
            let n = reader.read(&mut buffer)?;
            if n == 0 {
                break;
            }
            count += n as u64;
            anyhow::ensure!(count <= asset.bytes, "Model exceeds declared size");
            hash.update(&buffer[..n]);
            output.write_all(&buffer[..n])?;
            progress(count);
        }
        output.sync_all()?;
        anyhow::ensure!(
            count == asset.bytes
                && crate::pairing::hex(&hash.finalize()) == asset.sha256.to_lowercase(),
            "Model checksum or size mismatch"
        );
        if asset.kind == "stt" {
            let mut magic = [0; 4];
            std::fs::File::open(&tmp)?.read_exact(&mut magic)?;
            anyhow::ensure!(
                &magic == b"lmgg" || &magic == b"ggml",
                "Expected a whisper.cpp GGML model"
            );
        }
        if asset.kind == "formatter" {
            let mut magic = [0; 4];
            std::fs::File::open(&tmp)?.read_exact(&mut magic)?;
            anyhow::ensure!(&magic == b"GGUF", "Expected GGUF");
        }
        if asset.kind == "formatter_v6" {
            vaani_core::v6_tagger::parse(&std::fs::read(&tmp)?)
                .map_err(|e| anyhow::anyhow!("invalid formatter model: {e:?}"))?;
        }
        let backup = path.with_extension("previous");
        if path.exists() {
            std::fs::copy(&path, &backup)?;
        }
        std::fs::rename(&tmp, &path)?;
        Ok(path)
    })();
    let _ = std::fs::remove_file(tmp);
    result
}
pub fn download(
    asset: &Asset,
    root: &Path,
    cancel: &AtomicBool,
    progress: impl FnMut(u64),
) -> anyhow::Result<std::path::PathBuf> {
    anyhow::ensure!(asset.url.starts_with("https://"), "Models require HTTPS");
    let response = ureq::get(&asset.url).call()?;
    install(
        asset,
        response.into_body().into_reader(),
        root,
        cancel,
        progress,
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn corrupt_download_preserves_working_model() {
        let root = std::env::temp_dir().join(format!("vaani-model-test-{}", uuid::Uuid::new_v4()));
        let asset = Asset {
            id: "test".into(),
            kind: "stt".into(),
            filename: "base.bin".into(),
            url: "https://example.com/model".into(),
            sha256: "00".repeat(32),
            bytes: 4,
            license: "test".into(),
        };
        std::fs::create_dir_all(root.join("stt")).unwrap();
        std::fs::write(root.join("stt/base.bin"), b"old").unwrap();
        assert!(install(&asset, &b"lmgg"[..], &root, &AtomicBool::new(false), |_| {}).is_err());
        assert_eq!(std::fs::read(root.join("stt/base.bin")).unwrap(), b"old");
        let _ = std::fs::remove_dir_all(root);
    }
}
