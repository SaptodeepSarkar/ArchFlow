//! Transcript post-processing shared by every STT backend (whisper.cpp CLI,
//! faster-whisper server/one-shot). Deterministic and conservative:
//! fillers, false starts ("genuine genuinely") and accidental duplicate
//! phrases ("i can't i can't") are removed; intentional emphasis
//! ("very very", "no no") and substrings ("umber") survive. Anything needing
//! judgment (rephrasing, intent) belongs to the opt-in LLM cleanup layer.

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

/// Words that may repeat on purpose (emphasis, affirmation). Single-word
/// duplicates of these are preserved; everything else collapses.
const INTENTIONAL_DOUBLES: &[&str] = &[
    "no", "yes", "yeah", "yep", "nope", "oh", "ha", "hey", "hi", "hello",
    "well", "so", "very", "really", "quite", "far", "long", "many", "much",
    "more", "most", "again", "over", "bye", "please", "thanks", "sorry",
];

/// Collapse repetitions: false starts ("genuine genuinely" — a token that is
/// a strict prefix of the next one) and adjacent exact duplicate phrases of
/// 1–3 words ("i can't i can't move" → "i can't move"). Comparison is
/// case-insensitive; the first occurrence's casing wins.
pub fn collapse_repetitions(text: &str) -> String {
    let mut words: Vec<&str> = text.split_whitespace().collect();
    // Pass 1: false starts.
    let mut i = 0;
    while i + 1 < words.len() {
        let a = words[i].trim_matches(|c: char| !c.is_alphanumeric());
        let b = words[i + 1].trim_matches(|c: char| !c.is_alphanumeric());
        if a.len() >= 4 && b.len() > a.len() && b.to_lowercase().starts_with(&a.to_lowercase()) {
            words.remove(i);
        } else {
            i += 1;
        }
    }
    // Pass 2: duplicate phrases, longest first.
    for n in (1..=3).rev() {
        let mut i = 0;
        while i + 2 * n <= words.len() {
            let same = (0..n).all(|k| {
                words[i + k]
                    .trim_matches(|c: char| !c.is_alphanumeric())
                    .eq_ignore_ascii_case(
                        words[i + n + k].trim_matches(|c: char| !c.is_alphanumeric()),
                    )
            });
            let exempt = n == 1
                && INTENTIONAL_DOUBLES.contains(
                    &words[i]
                        .trim_matches(|c: char| !c.is_alphanumeric())
                        .to_lowercase()
                        .as_str(),
                );
            if same && !exempt {
                words.drain(i + n..i + 2 * n);
            } else {
                i += 1;
            }
        }
    }
    words.join(" ")
}

/// Full local polish: fillers, then repetitions, then spacing.
pub fn polish(text: &str) -> String {
    collapse_repetitions(&strip_fillers(text))
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

    #[test]
    fn repetitions_collapse_but_emphasis_survives() {
        use super::collapse_repetitions;
        assert_eq!(
            collapse_repetitions("i can't i can't move"),
            "i can't move"
        );
        assert_eq!(
            collapse_repetitions("genuine genuinely sorry"),
            "genuinely sorry"
        );
        assert_eq!(collapse_repetitions("the the cat sat"), "the cat sat");
        assert_eq!(
            collapse_repetitions("she sells she sells shells"),
            "she sells shells"
        );
        // Intentional doubles are preserved.
        assert_eq!(collapse_repetitions("very very good"), "very very good");
        assert_eq!(collapse_repetitions("no no don't go"), "no no don't go");
        // Prefix guard: short words are not false starts.
        assert_eq!(collapse_repetitions("an answer came"), "an answer came");
        assert_eq!(
            collapse_repetitions("the theatre was full"),
            "the theatre was full"
        );
        // Full polish chains both passes.
        assert_eq!(
            super::polish("uh i can't i can't move"),
            "i can't move"
        );
    }
}
