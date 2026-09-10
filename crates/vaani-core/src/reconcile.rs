//! Overlap reconciliation: join per-segment texts, removing duplicated
//! boundary words and normalising whitespace. Mixed scripts preserved.

/// Join segment transcripts. Handles punctuation, duplicate boundary words,
/// and mixed scripts explicitly. Final-segment flush: last segment always kept.
pub fn reconcile(segments: &[&str]) -> String {
    let mut out: Vec<String> = Vec::new();
    for seg in segments {
        let words: Vec<&str> = seg.split_whitespace().collect();
        if words.is_empty() {
            continue;
        }
        // Drop up to 8 leading words of this segment if they repeat the tail
        // of the accumulated output (overlap duplication).
        let mut drop = 0usize;
        let max = words.len().min(8).min(out.len());
        for k in (1..=max).rev() {
            let tail = &out[out.len() - k..];
            let head = &words[..k];
            if tail.iter().zip(head.iter()).all(|(a, b)| norm(a) == norm(b)) {
                drop = k;
                break;
            }
        }
        for w in &words[drop..] {
            out.push(w.to_string());
        }
    }
    // Only normalise outer whitespace (raw mode). Inner single spacing.
    out.join(" ").trim().to_string()
}

/// Normalise for comparison: lowercase, strip surrounding punctuation.
fn norm(w: &str) -> String {
    w.trim_matches(|c: char| c.is_ascii_punctuation() || c == '।' || c == '،')
        .to_lowercase()
}

/// Live dictation: split a cumulative transcript into a committable stable
/// prefix and an unstable tail. Only the stable part may be inserted; the
/// tail stays provisional (never typed into another application).
pub fn stable_prefix(text: &str, tail_words: usize) -> (String, String) {
    let words: Vec<&str> = text.split_whitespace().collect();
    if words.len() <= tail_words {
        return (String::new(), text.trim().to_string());
    }
    let cut = words.len() - tail_words;
    (words[..cut].join(" "), words[cut..].join(" "))
}

/// Delta between already-committed text and a new stable prefix.
/// Returns None when the recognizer revised earlier words (no commit this
/// round — wait for stability rather than duplicating or deleting).
pub fn delta_vs(committed: &str, stable: &str) -> Option<String> {
    let c = committed.trim();
    let s = stable.trim();
    if s.is_empty() {
        return None;
    }
    if c.is_empty() {
        return Some(s.to_string());
    }
    if s == c {
        return None;
    }
    match s.strip_prefix(c) {
        Some(rest) => {
            // Word-boundary safe: committed must end on a boundary.
            if rest.starts_with(char::is_whitespace) {
                let d = rest.trim_start().to_string();
                if d.is_empty() {
                    None
                } else {
                    Some(d)
                }
            } else {
                None
            }
        }
        None => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dedups_overlap() {
        let r = reconcile(&["hello world", "world this is", "is a test"]);
        assert_eq!(r, "hello world this is a test");
    }

    #[test]
    fn keeps_mixed_scripts() {
        let r = reconcile(&["namaste दुनिया", "दुनिया hello"]);
        assert!(r.contains("नमस्ते") || r.contains("namaste"));
        assert!(r.contains("hello"));
    }

    #[test]
    fn empty_segments_ok() {
        assert_eq!(reconcile(&["", "  ", "hi"]), "hi");
        assert_eq!(reconcile(&[]), "");
    }

    #[test]
    fn stable_holds_back_tail() {
        let (s, t) = stable_prefix("one two three four five six", 2);
        assert_eq!(s, "one two three four");
        assert_eq!(t, "five six");
        let (s, t) = stable_prefix("hi there", 4);
        assert_eq!(s, "");
        assert_eq!(t, "hi there");
    }

    #[test]
    fn delta_advances_and_detects_revision() {
        assert_eq!(delta_vs("", "hello world"), Some("hello world".into()));
        assert_eq!(delta_vs("hello world", "hello world of rust"), Some("of rust".into()));
        assert_eq!(delta_vs("hello world", "hello world"), None);
        // Revised earlier words -> None (wait, don't duplicate).
        assert_eq!(delta_vs("hello world", "hello there world peace"), None);
        // Mid-word boundary -> None.
        assert_eq!(delta_vs("hello wor", "hello world peace"), None);
    }
}
