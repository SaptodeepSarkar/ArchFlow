//! Config-driven vocabulary expansion (Vaani Phase 12).
//!
//! Whole-phrase match over pre-tokenized (already lowercased) words,
//! longest key wins, replacement spliced in verbatim. Pairs come from
//! `vaani.conf` `[names]`/`[links]` via `vaani-config` (ordered
//! `Vec<(String, String)>`); pass `names` then `links` concatenated.
//! Missing/empty sections are just empty slices: input passes through
//! unchanged. No dependencies, no I/O.
//!
//! NOTE: this module is inert until `lib.rs` declares `pub mod vocab;`
//! and routes the expansion step through [`expand_tokens`] (see the
//! Phase 12 hook snippet in the module report).

/// Expand vocab `pairs` over word `tokens`.
///
/// Keys match whole phrases case-insensitively (config keys may carry
/// capitals; pipeline tokens arrive lowercased); the longest matching
/// key wins, ties keep file order. The replacement is split on spaces
/// and spliced in verbatim — never re-cased or re-punctuated.
pub fn expand_tokens(tokens: Vec<String>, pairs: &[(&str, &str)]) -> Vec<String> {
    if pairs.is_empty() || tokens.is_empty() {
        return tokens;
    }
    // Lowercase keys once; costs one pass, keeps matching case-insensitive.
    let keys: Vec<(Vec<String>, &str)> = pairs
        .iter()
        .map(|(k, v)| {
            (
                k.split(' ').map(|w| w.to_ascii_lowercase()).collect(),
                *v,
            )
        })
        .collect();
    let mut out = Vec::with_capacity(tokens.len() + 2);
    let mut i = 0;
    while i < tokens.len() {
        let mut best: Option<(usize, &str)> = None;
        for (kw, rep) in &keys {
            if kw.is_empty() {
                continue;
            }
            let longer = best.is_none_or(|(n, _)| kw.len() > n);
            if longer
                && i + kw.len() <= tokens.len()
                && tokens[i..i + kw.len()]
                    .iter()
                    .map(|s| s.trim_end_matches(','))
                    .eq(kw.iter().map(String::as_str))
            {
                best = Some((kw.len(), rep));
            }
        }
        if let Some((n, rep)) = best {
            out.extend(rep.split(' ').map(str::to_string));
            i += n;
        } else {
            out.push(tokens[i].clone());
            i += 1;
        }
    }
    out
}
