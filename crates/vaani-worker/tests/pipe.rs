//! Worker pipe tests: silence in -> silence out; stub labelling honest.
//! Uses the freshly built binary via CARGO_BIN_EXE_vaani-worker.
use std::io::Write;
use std::process::Stdio;

fn run_worker(pcm: &[f32]) -> serde_json::Value {
    run_worker_with_text(pcm, None)
}

fn run_worker_with_text(pcm: &[f32], text: Option<&str>) -> serde_json::Value {
    let bin = env!("CARGO_BIN_EXE_vaani-worker");
    let mut command = std::process::Command::new(bin);
    command
        .arg("--model")
        .arg("/nonexistent.bin")
        .arg("--language")
        .arg("en")
        .arg("--threads")
        .arg("2")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    if let Some(text) = text {
        command.env("VAANI_WORKER_STUB_TEXT", text);
    } else {
        command.env_remove("VAANI_WORKER_STUB_TEXT");
    }
    let mut child = command.spawn().unwrap();
    let bytes: Vec<u8> = pcm.iter().flat_map(|x| x.to_le_bytes()).collect();
    child.stdin.take().unwrap().write_all(&bytes).unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success());
    serde_json::from_str(String::from_utf8(out.stdout).unwrap().trim()).unwrap()
}

#[test]
fn empty_is_silence() {
    let v = run_worker(&[]);
    assert_eq!(v["is_silence"], true);
    assert_eq!(v["text"], "");
}

#[test]
fn digital_silence_inserts_nothing() {
    let v = run_worker(&vec![0.0f32; 16_000]);
    assert_eq!(v["is_silence"], true);
    assert_eq!(v["text"], "");
}

#[test]
fn stub_never_invents_words() {
    // Loud tone without a model must NOT fabricate transcription.
    let tone: Vec<f32> = (0..16_000).map(|n| 0.3 * (n as f32 * 0.05).sin()).collect();
    let v = run_worker(&tone);
    assert_eq!(v["backend"], "cpu-stub");
    assert_eq!(v["text"], "");
}

#[test]
fn raw_stt_preserves_quoted_fillers_and_repeated_words() {
    let tone: Vec<f32> = (0..16_000).map(|n| 0.3 * (n as f32 * 0.05).sin()).collect();
    let raw = "the word um matters I I said no no and very very slowly";
    let result = run_worker_with_text(&tone, Some(raw));
    assert_eq!(result["text"], raw);
}
