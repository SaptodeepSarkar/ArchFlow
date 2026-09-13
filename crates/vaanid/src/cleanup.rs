//! Optional conservative text cleanup through an explicitly configured
//! local inference endpoint (e.g. Ollama). Raw is the dependable default.
//! Timeout/invalid output falls back to raw. The transcript is untrusted data:
//! delimited and the model is directed to edit only (no instruction following).

use std::io::Write;

pub fn clean(text: &str, endpoint: &str, timeout_secs: u64, vocabulary: &[String]) -> String {
    if endpoint.is_empty() || text.is_empty() {
        return text.to_string();
    }
    match try_clean(text, endpoint, timeout_secs, vocabulary) {
        Ok(c) => {
            if semantic_ok(text, &c) {
                c
            } else {
                text.to_string()
            }
        }
        Err(_) => text.to_string(), // fall back to raw, never discard
    }
}

fn try_clean(text: &str, endpoint: &str, timeout_secs: u64, vocab: &[String]) -> anyhow::Result<String> {
    let vocab_hint = if vocab.is_empty() {
        String::new()
    } else {
        format!("\nDomain terms (do not alter their spelling): {}", vocab.join(", "))
    };
    let prompt = format!(
        "You are a conservative transcription editor. Fix ONLY punctuation, capitalization, and obvious filler words (um, uh). Preserve meaning, negation, numbers, names, units, code, paths, and the original language. Do not add facts, do not rephrase claims, do not translate. If unsure, return the input unchanged.\n{vocab_hint}\n<transcript>\n{text}\n</transcript>\nReturn ONLY the edited transcript, no commentary."
    );
    // The request body travels only through curl's stdin. Do not materialize
    // dictated text in /tmp: a failed request must not leave a transcript on
    // disk.
    // Endpoint expected: http://host:port (Ollama-compatible /api/generate).
    let body = serde_json::json!({
        "model": std::env::var("VAANI_CLEAN_MODEL").unwrap_or("qwen2.5:3b".into()),
        "prompt": prompt,
        "stream": false,
    });
    let request = serde_json::to_vec(&body)?;
    let mut child = std::process::Command::new("curl")
        .arg("-sS")
        .arg("--max-time")
        .arg(timeout_secs.clamp(2, 30).to_string())
        .arg(format!("{endpoint}/api/generate"))
        .arg("--data-binary")
        .arg("@-")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(&request)?;
    }
    let out = child.wait_with_output()?;
    if !out.status.success() {
        anyhow::bail!("cleanup endpoint unreachable");
    }
    let v: serde_json::Value = serde_json::from_slice(&out.stdout)?;
    let resp = v.get("response").and_then(|r| r.as_str()).unwrap_or("").trim().to_string();
    if resp.is_empty() {
        anyhow::bail!("empty cleanup output");
    }
    // Bound output: reject absurd expansion (>2x input chars).
    if resp.len() > text.len().max(1) * 2 + 64 {
        anyhow::bail!("cleanup output too long");
    }
    Ok(resp)
}

/// Heuristic semantic guard: negation words, numbers, and length must survive.
/// This is a heuristic, not proof of correctness.
fn semantic_ok(raw: &str, cleaned: &str) -> bool {
    let neg = ["not", "no", "never", "n't", "नहीं", "না"];
    let rl = raw.to_lowercase();
    let cl = cleaned.to_lowercase();
    for w in neg {
        if rl.contains(w) && !cl.contains(w) {
            return false;
        }
    }
    // Digits must be preserved (allow reformatting, require same digit sequence).
    let digits = |s: &str| -> String { s.chars().filter(|c| c.is_ascii_digit()).collect() };
    if digits(raw) != digits(cleaned) {
        return false;
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_endpoint_is_identity() {
        assert_eq!(clean("hello", "", 8, &[]), "hello");
    }
    #[test]
    fn negation_guard() {
        assert!(!semantic_ok("do not delete", "delete"));
        assert!(semantic_ok("hello world", "Hello world."));
    }
    #[test]
    fn digit_guard() {
        assert!(!semantic_ok("call 911", "call 912"));
    }
}
