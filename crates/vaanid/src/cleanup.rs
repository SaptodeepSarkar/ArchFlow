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
    let source = words(raw);
    let actual = words(cleaned);
    // Each source filler may either remain in place or be omitted. Requiring
    // every filler to disappear rejects meaningful hesitation and even a
    // safe V6 copy-fallback; non-filler words must still match exactly and in
    // order, with no inserted content.
    let (mut source_index, mut actual_index) = (0, 0);
    while source_index < source.len() {
        if actual.get(actual_index) == Some(&source[source_index]) {
            source_index += 1;
            actual_index += 1;
        } else if fillers.contains(&source[source_index].as_str()) {
            source_index += 1;
        } else {
            return false;
        }
    }
    actual_index == actual.len()
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
    // This fallback must never substitute a dictated word, but casing is a
    // safe mechanical operation.  The generative formatter can be rejected
    // by the source-grounding gate for a single unwanted rewrite; without
    // this pass users would then get an entirely lower-case utterance.
    let mut chars: Vec<char> = out.chars().collect();
    let mut next_sentence = true;
    for index in 0..chars.len() {
        let ch = chars[index];
        if next_sentence && ch.is_alphabetic() {
            chars[index] = ch.to_uppercase().next().unwrap_or(ch);
            next_sentence = false;
        }
        // The pronoun is mechanical normalization, not entity guessing. It
        // is deliberately bounded so code-like identifiers (e.g. `i32`) stay
        // untouched.
        let before_word = index == 0 || !chars[index - 1].is_alphanumeric();
        let after_word = index + 1 == chars.len() || !chars[index + 1].is_alphanumeric();
        if ch == 'i' && before_word && after_word {
            chars[index] = 'I';
        }
        if matches!(ch, '.' | '!' | '?' | '…') {
            next_sentence = true;
        }
    }
    out = chars.into_iter().collect();
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
    // Ordinals occur frequently in ordinary narration ("the first launch
    // failed and the second worked").  They are structure only when the
    // speaker actually requests a list/sequence; otherwise preserve prose.
    let explicit_list_request = lower.contains("list")
        || lower.contains("steps")
        || lower.contains("numbered")
        || lower.contains("sequence");
    if explicit_list_request && positions.len() >= 2 {
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
        assert_eq!(
            conservative_format("i think i can. then i will try"),
            "I think I can. Then I will try."
        );
        assert_eq!(
            conservative_format("use i32 and i as a variable"),
            "Use i32 and I as a variable."
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
        assert!(semantic_ok("um i think so", "Um, I think so."));
        assert!(semantic_ok("um i think so", "I think so."));
        assert!(semantic_ok("the word um matters", "The word um matters."));
        assert!(!semantic_ok("open the browser", "Open Firefox."));
        assert!(!semantic_ok("send the report", "The report sends."));
        assert!(!semantic_ok("open the browser", "Open the browser safely."));
        assert!(!semantic_ok("uh open the browser", "um open the browser."));
    }

    #[test]
    fn closed_special_handles_only_explicit_cues() {
        assert_eq!(
            closed_special("please add a laughing emoji"),
            Some("😂".into())
        );
        assert_eq!(
            closed_special("make a numbered list first launch VSCode second inspect logs"),
            Some("1. Launch VSCode\n2. Inspect logs".into())
        );
        assert_eq!(
            closed_special("the first launch failed and the second one worked"),
            None
        );
        assert_eq!(closed_special("I do not want a laughing emoji"), None);
        assert_eq!(closed_special("open the browser"), None);
    }
}
