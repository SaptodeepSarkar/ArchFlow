//! Optional conservative text cleanup through an explicitly configured
//! local inference endpoint (e.g. Ollama). Raw is the dependable default.
//! Timeout/invalid output falls back to raw. The transcript is untrusted data:
//! delimited and the model is directed to edit only (no instruction following).

use std::io::Write;

pub fn clean(text: &str, endpoint: &str, timeout_secs: u64, vocabulary: &[String]) -> String {
    if endpoint.is_empty() || text.is_empty() {
        return closed_special(text).unwrap_or_else(|| text.to_string());
    }
    if let Some(special) = closed_special(text) {
        return special;
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
pub(crate) fn semantic_ok(raw: &str, cleaned: &str) -> bool {
    let neg = ["not", "no", "never", "n't", "नहीं", "না"];
    let rl = raw.to_lowercase();
    let cl = cleaned.to_lowercase();
    for w in neg {
        let present = |text: &str| {
            text.split(|c: char| !c.is_alphanumeric() && c != '\'')
                .any(|token| token == w)
        };
        if present(&rl) && !present(&cl) {
            return false;
        }
    }
    // Digits must be preserved (allow reformatting, require same digit sequence).
    let digits = |s: &str| -> String { s.chars().filter(|c| c.is_ascii_digit()).collect() };
    if digits(raw) != digits(cleaned) {
        return false;
    }
    // A cleanup model may remove only the explicitly permitted fillers.  All
    // other source words must remain in order, which prevents a generative
    // model from silently inventing, replacing, or reordering content.
    let words = |text: &str| -> Vec<String> {
        text.split_whitespace()
            .map(|word| {
                word.chars()
                    .filter(|c| c.is_alphanumeric() || *c == '\'')
                    .collect::<String>()
                    .to_lowercase()
            })
            .filter(|word| !word.is_empty())
            .collect()
    };
    let fillers = ["uh", "um", "erm", "hmm", "mmm"];
    let expected: Vec<String> = words(raw)
        .into_iter()
        .filter(|word| !fillers.contains(&word.as_str()))
        .collect();
    let actual = words(cleaned);
    // Exact equality after the permitted filler removal also rejects appended
    // or inserted hallucinated words; punctuation and casing are already
    // discarded by `words`.
    actual == expected
}

/// Handle only explicit, source-grounded structures that do not need a
/// generative model. Unknown text returns `None` and follows the existing
/// cleanup path. Dictated commands remain ordinary text.
pub(crate) fn closed_special(text: &str) -> Option<String> {
    let normalized = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if normalized.is_empty() {
        return None;
    }
    let lower = normalized.to_lowercase();
    let emoji = [
        ("laughing emoji", "😂"),
        ("laugh emoji", "😂"),
        ("thumbs up emoji", "👍"),
        ("heart emoji", "❤️"),
        ("celebration emoji", "🎉"),
        ("smiley emoji", "🙂"),
    ];
    let action_prefixes = ["add ", "add a ", "insert ", "insert a ", "use ", "use a ", "put ", "put a ", "include ", "include a ", "send ", "send a ", "give ", "give a "];
    if let Some((_, symbol)) = emoji.iter().find(|(cue, _)| {
        lower == *cue || action_prefixes.iter().any(|prefix| lower.ends_with(&format!("{prefix}{cue}")))
    }) {
        return Some((*symbol).to_string());
    }

    let markers = ["first", "second", "third", "fourth", "fifth"];
    let words: Vec<&str> = normalized.split_whitespace().collect();
    let positions: Vec<(usize, &str)> = words.iter().enumerate()
        .filter_map(|(i, word)| markers.iter().find(|marker| marker.eq_ignore_ascii_case(word)).map(|_| (i, *word)))
        .collect();
    if positions.len() >= 2 {
        let mut items = Vec::new();
        for (n, (start, _)) in positions.iter().enumerate() {
            let end = positions.get(n + 1).map(|(i, _)| *i).unwrap_or(words.len());
            let item = words[start + 1..end].join(" ").trim_matches(|c: char| ",.;:".contains(c)).to_string();
            if item.is_empty() { return None; }
            let mut chars = item.chars();
            let title = chars.next().map(|c| c.to_uppercase().collect::<String>()).unwrap_or_default() + chars.as_str();
            items.push(format!("{}. {}", n + 1, title));
        }
        return Some(items.join("\n"));
    }
    None
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
        assert!(semantic_ok("a notable result", "A notable result."));
    }
    #[test]
    fn digit_guard() {
        assert!(!semantic_ok("call 911", "call 912"));
    }
    #[test]
    fn content_guard_rejects_invention_and_reordering() {
        assert!(semantic_ok("uh open the browser", "Open the browser."));
        assert!(!semantic_ok("open the browser", "Open Firefox."));
        assert!(!semantic_ok("send the report", "The report sends."));
        assert!(!semantic_ok("open the browser", "Open the browser safely."));
    }

    #[test]
    fn closed_special_handles_only_explicit_cues() {
        assert_eq!(closed_special("please add a laughing emoji"), Some("😂".into()));
        assert_eq!(closed_special("first launch VSCode second inspect logs"), Some("1. Launch VSCode\n2. Inspect logs".into()));
        assert_eq!(closed_special("I do not want a laughing emoji"), None);
        assert_eq!(closed_special("open the browser"), None);
    }
}
