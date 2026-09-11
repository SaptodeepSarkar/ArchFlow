//! Transcript post-processing shared by every STT backend (whisper.cpp CLI,
//! faster-whisper server/one-shot). Conservative by design: only standalone
//! filler tokens vanish; substrings ("umber", "mummy") and sentence position
//! are untouched.

/// Drop spoken filler words (whole tokens, case-insensitive): uh/um/er
/// variants and mm-hesitations carry no information. Trailing/leading
/// punctuation on the token is tolerated ("uh," still counts).
pub fn strip_fillers(text: &str) -> String {
    const FILLERS: &[&str] = &[
        "uh", "uhh", "uhhh", "um", "umm", "ummm", "uhm", "er", "erm", "ah", "mmm",
    ];
    let kept: Vec<&str> = text
        .split_whitespace()
        .filter(|tok| {
            let core = tok
                .trim_matches(|c: char| !c.is_alphanumeric())
                .to_lowercase();
            !(core.len() >= 2 && FILLERS.contains(&core.as_str()))
        })
        .collect();
    // Rejoin and tidy spaces left before punctuation.
    let mut out = kept.join(" ");
    for p in [",", ".", "!", "?", ";", ":", ")", "]"] {
        out = out.replace(&format!(" {p}"), p);
    }
    out = out.replace("( ", "(").replace("[ ", "[");
    out.split_whitespace().collect::<Vec<_>>().join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fillers_removed_whole_tokens_only() {
        assert_eq!(
            strip_fillers("Uh, I um think er this is fine"),
            "I think this is fine"
        );
        assert_eq!(
            strip_fillers("well UMM let me see mmm ok"),
            "well let me see ok"
        );
        // Substrings and short tokens survive.
        assert_eq!(strip_fillers("umber mummy a I"), "umber mummy a I");
        assert_eq!(strip_fillers(""), "");
        // Punctuation spacing tidied.
        assert_eq!(strip_fillers("hello , uh world ."), "hello, world.");
    }
}
