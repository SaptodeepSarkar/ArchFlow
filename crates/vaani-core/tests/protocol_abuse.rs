use vaani_core::protocol::{Request, RequestKind};

#[test]
fn malformed_rejected() {
    assert!(Request::validate_line("not json").is_err());
    assert!(Request::validate_line("").is_err());
    assert!(Request::validate_line("{\"op\":1}").is_err());
}

#[test]
fn wrong_version_rejected() {
    let s = r#"{"protocol_version":999,"request_id":"r","kind":{"op":"toggle"}}"#;
    assert!(Request::validate_line(s).is_err());
}

#[test]
fn oversize_rejected() {
    let big = "A".repeat(vaani_core::MAX_CONTROL_BYTES + 8);
    assert!(Request::validate_line(&big).is_err());
}

#[test]
fn all_ops_roundtrip() {
    for kind in [
        RequestKind::Toggle,
        RequestKind::Start,
        RequestKind::Stop,
        RequestKind::Cancel,
        RequestKind::Status,
        RequestKind::Settings,
        RequestKind::Doctor,
        RequestKind::CopyPending,
        RequestKind::RecoverPending,
        RequestKind::DiscardPending,
        RequestKind::Subscribe,
        RequestKind::MicTest { secs: 3 },
        RequestKind::ConfigGet,
        RequestKind::ConfigSet {
            key: "recognition.model".into(),
            value: "small".into(),
        },
    ] {
        let r = Request::new(kind);
        let line = r.to_line().unwrap();
        let back = Request::validate_line(line.trim_end()).unwrap();
        assert_eq!(back.protocol_version, vaani_core::PROTOCOL_VERSION);
    }
}

#[test]
fn silence_shortcircuit_reaches_idle() {
    // Regression: stop on silence must land back in IDLE, not stick.
    use vaani_core::state::{Session, State};
    let mut s = Session::new(1);
    s.transition(State::Starting).unwrap();
    s.transition(State::Recording).unwrap();
    s.transition(State::Transcribing).unwrap();
    s.transition(State::Idle).unwrap();
}

#[test]
fn duplicate_commands_do_not_duplicate() {
    // stop is idempotent: Idle stays Idle, Transcribing stays Transcribing.
    use vaani_core::state::{Session, State};
    let mut s = Session::new(1);
    s.transition(State::Starting).unwrap();
    assert!(s.transition(State::Starting).is_err()); // no double-start
    s.transition(State::Recording).unwrap();
    s.transition(State::Transcribing).unwrap();
    assert!(s.transition(State::Transcribing).is_ok()); // idempotent stop
}
