//! Live checks against a local formatter LLM. These need an OpenAI-compatible
//! server on VAANI_LLM_ENDPOINT (default 127.0.0.1:8082), so they are
//! `#[ignore]`d and never run in CI. Run them on a box that has the model:
//!     cargo test -p llm-formatter --test live_llm -- --ignored
//! They assert *properties* (fillers gone, names expanded, no commentary),
//! not exact wording: a generative formatter cannot guarantee a fixed string.

use llm_formatter::format_pipeline;

fn pairs() -> Vec<(&'static str, &'static str)> {
    vec![("saptodeep", "Saptodeep Sarkar")]
}

#[test]
#[ignore = "requires a local llama-server"]
fn filler_and_correction_are_cleaned() {
    let (out, backend) = format_pipeline("umm so i think hmm we should ship it", &pairs());
    assert_eq!(backend, "llm", "expected the LLM path: {out}");
    let lower = out.to_lowercase();
    for filler in ["umm", "hmm", "uh", "er"] {
        assert!(!lower.contains(filler), "filler {filler} survived: {out}");
    }
}

#[test]
#[ignore = "requires a local llama-server"]
fn configured_names_are_expanded() {
    let (out, backend) = format_pipeline("send it to saptodeep please", &pairs());
    assert_eq!(backend, "llm", "expected the LLM path: {out}");
    assert!(
        out.contains("Saptodeep Sarkar"),
        "name was not expanded: {out}"
    );
}

#[test]
#[ignore = "requires a local llama-server"]
fn output_is_never_commentary() {
    let (out, _) = format_pipeline("the build passed", &pairs());
    let lower = out.to_lowercase();
    for bad in ["here is", "sure", "as an ai", "i cannot"] {
        assert!(!lower.starts_with(bad), "model answered with chatter: {out}");
    }
}

#[test]
fn falls_back_to_rules_when_the_endpoint_is_dead() {
    // Hermetic: no server on this port, so the deterministic engine answers.
    // Safety net for "dictation must still work with no LLM around".
    std::env::set_var("VAANI_LLM_ENDPOINT", "http://127.0.0.1:1");
    let (out, backend) = format_pipeline("umm hello there", &pairs());
    std::env::remove_var("VAANI_LLM_ENDPOINT");
    assert_eq!(backend, "rules");
    assert_eq!(out, "Hello there.");
}
