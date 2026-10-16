//! `llm-format`: read raw transcripts (one per stdin line), write the
//! formatted plain text (one per stdout line). Used by `gate-07.sh`.

use std::io::{self, BufRead, Write};

fn main() {
    let stdin = io::stdin();
    let mut out = io::BufWriter::new(io::stdout());
    for line in stdin.lock().lines() {
        let line = line.unwrap_or_default();
        writeln!(out, "{}", llm_formatter::format(&line)).ok();
    }
}
