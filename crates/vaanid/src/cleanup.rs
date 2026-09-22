//! Deterministic guardrails for the always-on local transcript formatter.
//! The formatter may alter only permitted fillers, punctuation, and casing;
//! rejected output retains the raw text.

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

/// A source-preserving fallback for when a generative rewrite is rejected.
/// It changes only whitespace, the initial letter's casing, and a final
/// sentence mark on ordinary prose. URLs, paths, code-like text, and
/// multi-line content are left without a synthetic terminal mark.
pub(crate) fn conservative_format(text: &str) -> String {
    let technical_or_multiline = text.contains('\n')
        || text.contains("://")
        || text.trim_start().starts_with('/')
        || text.trim_start().starts_with('~')
        || text.contains('=')
        || text.contains("::");
    if technical_or_multiline {
        return text.trim().to_string();
    }
    let mut out = text.split_whitespace().collect::<Vec<_>>().join(" ");
    if out.is_empty() {
        return out;
    }
    if let Some((index, ch)) = out.char_indices().find(|(_, ch)| ch.is_alphabetic()) {
        let upper = ch.to_uppercase().to_string();
        out.replace_range(index..index + ch.len_utf8(), &upper);
    }
    if !matches!(out.chars().last(), Some('.' | '!' | '?' | '…' | '।')) {
        out.push('.');
    }
    out
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
    let action_prefixes = [
        "add ",
        "add a ",
        "insert ",
        "insert a ",
        "use ",
        "use a ",
        "put ",
        "put a ",
        "include ",
        "include a ",
        "send ",
        "send a ",
        "give ",
        "give a ",
    ];
    if let Some((_, symbol)) = emoji.iter().find(|(cue, _)| {
        lower == *cue
            || action_prefixes
                .iter()
                .any(|prefix| lower.ends_with(&format!("{prefix}{cue}")))
    }) {
        return Some((*symbol).to_string());
    }

    let markers = ["first", "second", "third", "fourth", "fifth"];
    let words: Vec<&str> = normalized.split_whitespace().collect();
    let positions: Vec<(usize, &str)> = words
        .iter()
        .enumerate()
        .filter_map(|(i, word)| {
            markers
                .iter()
                .find(|marker| marker.eq_ignore_ascii_case(word))
                .map(|_| (i, *word))
        })
        .collect();
    if positions.len() >= 2 {
        let mut items = Vec::new();
        for (n, (start, _)) in positions.iter().enumerate() {
            let end = positions.get(n + 1).map(|(i, _)| *i).unwrap_or(words.len());
            let item = words[start + 1..end]
                .join(" ")
                .trim_matches(|c: char| ",.;:".contains(c))
                .to_string();
            if item.is_empty() {
                return None;
            }
            let mut chars = item.chars();
            let title = chars
                .next()
                .map(|c| c.to_uppercase().collect::<String>())
                .unwrap_or_default()
                + chars.as_str();
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
    fn safety_guard_allows_punctuation_only() {
        assert!(semantic_ok("hello", "Hello."));
    }

    #[test]
    fn conservative_fallback_formats_prose_without_rewriting_words() {
        assert_eq!(
            conservative_format("hello this is a test"),
            "Hello this is a test."
        );
        assert_eq!(
            conservative_format("https://example.test/path"),
            "https://example.test/path"
        );
        assert_eq!(
            conservative_format("first item\nsecond item"),
            "first item\nsecond item"
        );
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
        assert_eq!(
            closed_special("please add a laughing emoji"),
            Some("😂".into())
        );
        assert_eq!(
            closed_special("first launch VSCode second inspect logs"),
            Some("1. Launch VSCode\n2. Inspect logs".into())
        );
        assert_eq!(closed_special("I do not want a laughing emoji"), None);
        assert_eq!(closed_special("open the browser"), None);
    }
}
