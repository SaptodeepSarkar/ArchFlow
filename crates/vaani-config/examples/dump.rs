use std::path::PathBuf;
use vaani_config::load;

fn usage() -> ! {
    eprintln!("usage: dump [--roundtrip] <path>");
    std::process::exit(2);
}

fn main() {
    let args = std::env::args().skip(1);
    let mut roundtrip = false;
    let mut path: Option<String> = None;
    for a in args {
        if a == "--roundtrip" {
            roundtrip = true;
        } else if path.is_none() {
            path = Some(a);
        } else {
            usage();
        }
    }
    let path = path.unwrap_or_else(|| usage());
    let outcome = load(PathBuf::from(&path).as_path());
    for w in &outcome.warnings {
        eprintln!("warning: {w}");
    }
    if roundtrip {
        let again = vaani_config::parse_str(&outcome.config.to_canonical());
        if again.config == outcome.config && again.warnings.is_empty() {
            println!("ROUNDTRIP-OK");
        } else {
            println!("ROUNDTRIP-FAIL");
            std::process::exit(1);
        }
    } else {
        print!("{}", outcome.config.to_canonical());
    }
}
