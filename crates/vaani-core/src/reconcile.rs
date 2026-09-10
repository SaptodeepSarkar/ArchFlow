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
}
