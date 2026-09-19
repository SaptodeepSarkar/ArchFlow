//! Portable, deterministic personalization primitives.
//!
//! This module deliberately has no database or platform dependency. Android
//! and desktop repositories can persist these records and feed a snapshot to
//! the same renderer, keeping behavior consistent across shells.

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct VocabularyEntry {
    pub id: String,
    pub canonical: String,
    #[serde(default)]
    pub spoken_aliases: Vec<String>,
    #[serde(default)]
    pub category: Option<String>,
    pub created_at_ms: i64,
    pub updated_at_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Snippet {
    pub id: String,
    pub trigger: String,
    pub value: String,
    pub created_at_ms: i64,
    pub updated_at_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Replacement {
    pub id: String,
    pub source: String,
    pub target: String,
    pub created_at_ms: i64,
    pub updated_at_ms: i64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct PersonalizationSnapshot {
    #[serde(default)]
    pub vocabulary: Vec<VocabularyEntry>,
    #[serde(default)]
    pub snippets: Vec<Snippet>,
    #[serde(default)]
    pub replacements: Vec<Replacement>,
}

/// Applies vocabulary canonicalization, snippets, then replacements. Rules are
/// longest-first and each rule is applied once, so a replacement cannot
/// recursively loop.
pub fn render(text: &str, snapshot: &PersonalizationSnapshot) -> String {
    let mut rendered = text.to_owned();
    let mut vocabulary = snapshot
        .vocabulary
        .iter()
        .flat_map(|entry| entry.spoken_aliases.iter().map(move |alias| (alias, &entry.canonical)))
        .collect::<Vec<_>>();
    vocabulary.sort_by_key(|(alias, _)| std::cmp::Reverse(alias.chars().count()));
    for (alias, canonical) in vocabulary {
        rendered = replace_bounded(&rendered, alias, canonical);
    }

    let mut snippets = snapshot.snippets.iter().collect::<Vec<_>>();
    snippets.sort_by_key(|entry| std::cmp::Reverse(entry.trigger.chars().count()));
    for snippet in snippets {
        rendered = replace_bounded(&rendered, &snippet.trigger, &snippet.value);
    }

    let mut replacements = snapshot.replacements.iter().collect::<Vec<_>>();
    replacements.sort_by_key(|entry| std::cmp::Reverse(entry.source.chars().count()));
    for replacement in replacements {
        rendered = replace_bounded(&rendered, &replacement.source, &replacement.target);
    }
    rendered
}

fn replace_bounded(text: &str, needle: &str, replacement: &str) -> String {
    if needle.is_empty() {
        return text.to_owned();
    }
    let mut out = String::with_capacity(text.len());
    let mut cursor = 0;
    while let Some(relative) = find_case_insensitive(&text[cursor..], needle) {
        let start = cursor + relative;
        let end = start
            + text[start..]
                .char_indices()
                .nth(needle.chars().count())
                .map_or(text.len() - start, |(offset, _)| offset);
        if is_boundary(text, start, end) {
            out.push_str(&text[cursor..start]);
            out.push_str(replacement);
            cursor = end;
        } else {
            out.push_str(
                &text[cursor..start + text[start..].chars().next().map_or(0, char::len_utf8)],
            );
            cursor = start + text[start..].chars().next().map_or(0, char::len_utf8);
        }
    }
    out.push_str(&text[cursor..]);
    out
}

fn find_case_insensitive(haystack: &str, needle: &str) -> Option<usize> {
    let wanted = needle
        .chars()
        .flat_map(char::to_lowercase)
        .collect::<Vec<_>>();
    let chars = haystack.char_indices().collect::<Vec<_>>();
    for (index, (byte, _)) in chars.iter().enumerate() {
        let candidate = haystack[*byte..]
            .chars()
            .flat_map(char::to_lowercase)
            .take(wanted.len())
            .collect::<Vec<_>>();
        if candidate == wanted {
            return Some(*byte);
        }
        if index == chars.len() {
            break;
        }
    }
    None
}

fn is_boundary(text: &str, start: usize, end: usize) -> bool {
    let before = text[..start].chars().next_back();
    let after = text[end..].chars().next();
    before.is_none_or(|c| !c.is_alphanumeric() && c != '_')
        && after.is_none_or(|c| !c.is_alphanumeric() && c != '_')
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snapshot(snippets: Vec<Snippet>, replacements: Vec<Replacement>) -> PersonalizationSnapshot {
        PersonalizationSnapshot {
            snippets,
            replacements,
            ..Default::default()
        }
    }

    #[test]
    fn snippets_expand_before_replacements() {
        let s = snapshot(
            vec![Snippet {
                id: "1".into(),
                trigger: "my github".into(),
                value: "https://github.com/example/repo".into(),
                created_at_ms: 0,
                updated_at_ms: 0,
            }],
            vec![Replacement {
                id: "2".into(),
                source: "hyper land".into(),
                target: "Hyprland".into(),
                created_at_ms: 0,
                updated_at_ms: 0,
            }],
        );
        assert_eq!(
            render("Send them my GitHub; hyper land is cool", &s),
            "Send them https://github.com/example/repo; Hyprland is cool"
        );
    }

    #[test]
    fn rules_respect_word_boundaries_and_are_not_recursive() {
        let s = snapshot(
            vec![],
            vec![
                Replacement {
                    id: "1".into(),
                    source: "cat".into(),
                    target: "dog".into(),
                    created_at_ms: 0,
                    updated_at_ms: 0,
                },
                Replacement {
                    id: "2".into(),
                    source: "dog".into(),
                    target: "wolf".into(),
                    created_at_ms: 0,
                    updated_at_ms: 0,
                },
            ],
        );
        assert_eq!(render("concatenate cat", &s), "concatenate wolf");
    }

    #[test]
    fn vocabulary_aliases_canonicalize_before_other_rules() {
        let s = PersonalizationSnapshot {
            vocabulary: vec![VocabularyEntry {
                id: "hyprland".into(),
                canonical: "Hyprland".into(),
                spoken_aliases: vec!["hyper land".into()],
                category: Some("technical".into()),
                created_at_ms: 0,
                updated_at_ms: 0,
            }],
            ..Default::default()
        };
        assert_eq!(render("hyper land is fast", &s), "Hyprland is fast");
    }
}
