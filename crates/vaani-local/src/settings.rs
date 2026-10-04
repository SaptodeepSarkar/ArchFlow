//! Preserve comments/unknown keys and reject malformed/conflicting user settings.
use std::{io::Write, path::Path};
use vaani_core::config::Config;
pub fn read(path: &Path) -> anyhow::Result<(String, Config)> {
    let text = std::fs::read_to_string(path)?;
    let config = toml_edit::de::from_str::<Config>(&text)?;
    Ok((text, config))
}
pub fn update(path: &Path, expected: &str, key: &str, value: &str) -> anyhow::Result<()> {
    update_many(path, expected, &[(key, value.to_owned())])
}
pub fn update_many(path: &Path, expected: &str, updates: &[(&str, String)]) -> anyhow::Result<()> {
    let current = std::fs::read_to_string(path)?;
    anyhow::ensure!(
        current == expected,
        "Settings changed outside this window; reload before saving."
    );
    let mut config = toml_edit::de::from_str::<Config>(&current)?;
    for (key, value) in updates {
        config.set_key(key, value).map_err(anyhow::Error::msg)?;
    }
    let mut document = current.parse::<toml_edit::DocumentMut>()?;
    for (key, _) in updates {
        let (section, field) = key
            .split_once('.')
            .ok_or_else(|| anyhow::anyhow!("invalid settings key"))?;
        let canonical = serde_json::to_value(&config)?;
        let field_value = &canonical[section][field];
        document[section][field] = match field_value {
            serde_json::Value::Bool(v) => toml_edit::value(*v),
            serde_json::Value::Number(v) => {
                toml_edit::value(v.as_i64().ok_or_else(|| anyhow::anyhow!("integer"))?)
            }
            serde_json::Value::String(v) => toml_edit::value(v.as_str()),
            _ => anyhow::bail!("unsupported field"),
        };
    }
    let tmp = path.with_extension(format!("{}.tmp", uuid::Uuid::new_v4()));
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let result = (|| {
        let mut f = options.open(&tmp)?;
        f.write_all(document.to_string().as_bytes())?;
        f.sync_all()?;
        anyhow::ensure!(
            std::fs::read_to_string(path)? == expected,
            "Settings changed while saving; reload."
        );
        std::fs::rename(&tmp, path)?;
        Ok(())
    })();
    let _ = std::fs::remove_file(tmp);
    result
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn update_preserves_unknown_fields_and_rejects_conflict() {
        let path =
            std::env::temp_dir().join(format!("vaani-settings-{}.toml", uuid::Uuid::new_v4()));
        let text = "# user comment\n[general]\nresidency_profile='economy'\ncustom='keep'\n";
        std::fs::write(&path, text).unwrap();
        update(&path, text, "general.residency_profile", "balanced").unwrap();
        let saved = std::fs::read_to_string(&path).unwrap();
        assert!(saved.contains("user comment") && saved.contains("custom='keep'"));
        assert!(update(&path, text, "general.residency_profile", "ready").is_err());
        let _ = std::fs::remove_file(path);
    }
}
