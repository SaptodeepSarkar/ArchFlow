use vaani_core::config::Config;

#[test]
fn whitelist_accepts_known_keys() {
    let mut c = Config::default();
    assert_eq!(c.set_key("recognition.model", "small").unwrap(), "small");
    assert_eq!(c.set_key("recognition.model", "cozy").unwrap(), "cozy");
    assert_eq!(c.set_key("recognition.language", "hi").unwrap(), "hi");
    assert_eq!(c.set_key("audio.worker_threads", "8").unwrap(), "8");
    assert_eq!(
        c.set_key("general.residency_profile", "balanced").unwrap(),
        "balanced"
    );
}

#[test]
fn rejects_unknown_and_bad_values() {
    let mut c = Config::default();
    assert!(c.set_key("recognition.model", "llama-70b").is_err());
    assert!(c.set_key("audio.worker_threads", "64").is_err());
    assert!(c.set_key("audio.worker_threads", "abc").is_err());
    assert!(c.set_key("general.residency_profile", "always").is_err());
    assert!(c.set_key("cleanup.endpoint", "ftp://x").is_err());
    assert!(c.set_key("hacker.key", "1").is_err());
    assert!(c.set_key("recognition.language", "auto").is_err());
}

#[test]
fn live_chunk_bounded() {
    let mut c = Config::default();
    assert_eq!(c.general.live_chunk_secs, 1);
    assert_eq!(c.set_key("general.live_chunk_secs", "6").unwrap(), "6");
    assert_eq!(c.set_key("general.live_chunk_secs", "1").unwrap(), "1");
    assert!(c.set_key("general.live_chunk_secs", "30").is_err());
}
