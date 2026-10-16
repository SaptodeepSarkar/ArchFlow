//! CLI: type one text argument after explicit pill-hide confirmation.
//! Usage: type-text --pill-hidden <text>

use std::process::ExitCode;

use typing_helper::type_text;

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    match (args.next().as_deref(), args.next(), args.next()) {
        (Some("--pill-hidden"), Some(text), None) => match type_text(&text, true) {
            Ok(report) => {
                println!(
                    "typed bytes={} clipboard_copied={}",
                    text.len(),
                    report.clipboard_copied
                );
                ExitCode::SUCCESS
            }
            Err(e) => {
                eprintln!("type-text: {e}");
                ExitCode::FAILURE
            }
        },
        _ => {
            eprintln!("usage: type-text --pill-hidden <text>");
            ExitCode::from(2)
        }
    }
}
