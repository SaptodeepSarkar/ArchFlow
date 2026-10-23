#!/usr/bin/env bash
# Phase 12 gate (names-links): config [names]/[links] expand verbatim end
# to end through crates/llm-formatter/src/vocab.rs fed by the real
# vaani-config parser; longest match wins; empty sections safe.
# Exits 0 (GREEN) only if every check passes. Creates no repo files:
# the harness lives under mktemp and path-depends on crates/vaani-config.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate12.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# 1. module + fixture present (lib.rs stays untouched by design: the
#    coordinator wires `pub mod vocab;` + format_with_vocab per snippet).
[ -f crates/llm-formatter/src/vocab.rs ] \
  && ok "vocab.rs exists" || bad "vocab.rs missing"
[ -f TESTS/fixtures/config-vocab.conf ] \
  && ok "config-vocab.conf exists" || bad "config-vocab.conf missing"

# 2. the real parser is green (harness below feeds on it).
if cargo test -p vaani-config >"$TMP/config-test.log" 2>&1; then
  ok "cargo test -p vaani-config passes"
else
  bad "vaani-config tests fail (see $TMP/config-test.log)"
fi

# 3. end-to-end harness: fixture -> vaani_config::parse_str -> vocab module.
mkdir -p "$TMP/harness/src"
cp crates/llm-formatter/src/vocab.rs "$TMP/harness/src/vocab.rs"
cat > "$TMP/harness/Cargo.toml" <<EOF
[package]
name = "vocab-harness"
version = "0.0.0"
edition = "2021"

[dependencies]
vaani-config = { path = "$ROOT/crates/vaani-config" }

[workspace]
EOF
cat > "$TMP/harness/src/main.rs" <<'EOF'
#[path = "vocab.rs"]
mod vocab;

// Same normalization as llm_formatter::format input stage.
fn tokenize(raw: &str) -> Vec<String> {
    raw.split_whitespace()
        .map(|t| {
            t.trim_matches(|c: char| c.is_ascii_punctuation())
                .to_ascii_lowercase()
        })
        .filter(|t| !t.is_empty())
        .collect()
}

fn expand(raw: &str, pairs: &[(String, String)]) -> String {
    let refs: Vec<(&str, &str)> = pairs.iter().map(|(k, v)| (k.as_str(), v.as_str())).collect();
    vocab::expand_tokens(tokenize(raw), &refs).join(" ")
}

fn check(ok: bool, msg: String, pass: &mut i32, fail: &mut i32) {
    if ok {
        println!("  [GREEN] {msg}");
        *pass += 1;
    } else {
        println!("  [RED] {msg}");
        *fail += 1;
    }
}

fn main() {
    let (mut pass, mut fail) = (0, 0);
    let text = std::fs::read_to_string("TESTS/fixtures/config-vocab.conf").unwrap();
    let o = vaani_config::parse_str(&text);
    check(o.warnings.is_empty(), format!("fixture parses clean: {:?}", o.warnings), &mut pass, &mut fail);
    check(
        o.config.names
            == vec![
                ("saptodeep".to_owned(), "Saptodeep Sarkar".to_owned()),
                ("my advisor".to_owned(), "Dr. Rao".to_owned()),
                ("my advisor smith".to_owned(), "Dr. Alice Smith".to_owned()),
            ],
        format!("names parsed as ordered pairs: {:?}", o.config.names),
        &mut pass, &mut fail,
    );
    check(
        o.config.links == vec![("github".to_owned(), "https://github.com/SaptodeepSarkar".to_owned())],
        format!("links parsed as ordered pairs: {:?}", o.config.links),
        &mut pass, &mut fail,
    );
    let mut vocab: Vec<(String, String)> = Vec::new();
    vocab.extend(o.config.names.iter().cloned());
    vocab.extend(o.config.links.iter().cloned());

    // Every configured pair expands verbatim end to end.
    for (spoken, typed) in &vocab {
        let got = expand(&format!("met {spoken} yesterday"), &vocab);
        check(got.contains(typed), format!("'{spoken}' -> '{typed}' verbatim ({got:?})"), &mut pass, &mut fail);
    }
    // Longest match wins on the overlapping pair.
    let got = expand("met my advisor smith yesterday", &vocab);
    check(
        got.contains("Dr. Alice Smith") && !got.contains("Dr. Rao"),
        format!("longest wins, no partial: {got:?}"),
        &mut pass, &mut fail,
    );
    // ...while the shorter key still fires on its own.
    let got = expand("met my advisor yesterday", &vocab);
    check(got.contains("Dr. Rao"), format!("shorter key alone: {got:?}"), &mut pass, &mut fail);
    // Whole-phrase only: partial word untouched.
    let got = expand("open githubs now", &vocab);
    check(!got.contains("github.com"), format!("no substring expansion: {got:?}"), &mut pass, &mut fail);
    // Missing/empty sections behave as empty, no crash.
    let bare = vaani_config::parse_str("");
    check(bare.config.names.is_empty() && bare.config.links.is_empty(), "missing sections parse as empty".into(), &mut pass, &mut fail);
    let toks = tokenize("met saptodeep yesterday");
    check(vocab::expand_tokens(toks.clone(), &[]) == toks, "empty vocab passes tokens through".into(), &mut pass, &mut fail);
    check(expand("met saptodeep yesterday", &[]) == "met saptodeep yesterday", "empty pairs leave text unchanged".into(), &mut pass, &mut fail);

    println!("harness: {pass} passed, {fail} failed");
    std::process::exit(if fail == 0 { 0 } else { 1 });
}
EOF
if cargo run --quiet --manifest-path "$TMP/harness/Cargo.toml" >"$TMP/harness.log" 2>&1; then
  ok "vocab harness end to end ($(grep -E '^harness' "$TMP/harness.log"))"
else
  bad "vocab harness failed (see $TMP/harness.log)"
fi
cat "$TMP/harness.log"

printf 'gate-12: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-12 GREEN"; exit 0; else echo "gate-12 RED"; exit 1; fi
