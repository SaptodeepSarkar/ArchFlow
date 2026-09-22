//! `vaani`: short-lived CLI. Structured IPC only — never shell text with
//! dictated content. Commands: toggle, start, stop, cancel, status --json,
//! settings, doctor, copy, recover, discard, mic-test, inject.

use clap::{Parser, Subcommand};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;
use vaani_core::protocol::{Request, RequestKind};

#[derive(Parser, Debug)]
#[command(name = "vaani", about = "Vaani voice dictation CLI")]
struct Args {
    #[command(subcommand)]
    cmd: Cmd,
}

#[derive(Subcommand, Debug)]
enum Cmd {
    Toggle,
    Start,
    Stop,
    Cancel,
    #[command(name = "live-toggle")]
    LiveToggle,
    Status {
        #[arg(long)]
        json: bool,
    },
    Settings,
    Doctor,
    Copy,
    Recover,
    Discard,
    #[command(name = "mic-test")]
    MicTest {
        #[arg(long, default_value = "3")]
        secs: u32,
    },
    #[command(name = "inject")]
    Inject,
    #[command(name = "config-get")]
    ConfigGet,
    #[command(name = "config-set")]
    ConfigSet {
        key: String,
        value: String,
    },
}

fn open_settings_window() -> anyhow::Result<()> {
    std::process::Command::new("vaani-desktop")
        .arg("app")
        .spawn()
        .map_err(|error| anyhow::anyhow!("could not open Vaani settings: {error}"))?;
    Ok(())
}

fn sock_path() -> String {
    let base = std::env::var("XDG_RUNTIME_DIR").unwrap_or_else(|_| "/tmp".into());
    if std::env::var("XDG_RUNTIME_DIR").is_err() {
        let uid = std::env::var("UID").unwrap_or("1000".into());
        format!("/tmp/vaani-{uid}/control.sock")
    } else {
        format!("{base}/vaani/control.sock")
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = Args::parse();
    if matches!(&args.cmd, Cmd::Settings) {
        return open_settings_window();
    }
    let kind = match args.cmd {
        Cmd::Toggle => RequestKind::Toggle,
        Cmd::Start => RequestKind::Start,
        Cmd::Stop => RequestKind::Stop,
        Cmd::Cancel => RequestKind::Cancel,
        Cmd::LiveToggle => RequestKind::LiveToggle,
        Cmd::Status { .. } => RequestKind::Status,
        Cmd::Settings => unreachable!("handled before IPC"),
        Cmd::Doctor => RequestKind::Doctor,
        Cmd::Copy => RequestKind::CopyPending,
        Cmd::Recover => RequestKind::RecoverPending,
        Cmd::Discard => RequestKind::DiscardPending,
        Cmd::MicTest { secs } => RequestKind::MicTest { secs },
        Cmd::Inject => RequestKind::Inject,
        Cmd::ConfigGet => RequestKind::ConfigGet,
        Cmd::ConfigSet { key, value } => RequestKind::ConfigSet { key, value },
    };
    let as_json = matches!(
        kind,
        RequestKind::Status | RequestKind::Doctor | RequestKind::ConfigGet
    );
    let want_text = matches!(kind, RequestKind::RecoverPending | RequestKind::Inject);

    let mut req = Request::new(kind);
    req.session_id = None;

    let mut stream = UnixStream::connect(sock_path()).await.map_err(|_| {
        anyhow::anyhow!(
            "cannot reach vaanid — is the user service running? (systemctl --user status vaanid)"
        )
    })?;
    let (r, mut w) = stream.split();
    let mut lines = BufReader::new(r).lines();
    // First line is the state snapshot.
    let snapshot = lines.next_line().await?.unwrap_or_default();
    let want_id = req.request_id.clone();
    w.write_all(req.to_line().unwrap().as_bytes()).await?;
    // The connection also carries async event lines (state/amplitude/
    // provisional have no request_id). Skip them until OUR response.
    let mut response = String::new();
    loop {
        let line = lines.next_line().await?.unwrap_or_default();
        if line.trim().is_empty() {
            continue;
        }
        let is_ours = serde_json::from_str::<serde_json::Value>(&line)
            .ok()
            .and_then(|v| {
                v.get("request_id")
                    .and_then(|id| id.as_str())
                    .map(|s| s.to_string())
            })
            == Some(want_id.clone());
        if is_ours {
            response = line;
            break;
        }
        // Otherwise: an async event interleaved — ignore on the CLI path.
    }

    if as_json {
        println!("{response}");
    } else {
        // Human-readable: state + message, never dump raw transcript unless
        // recover/copy explicitly requested.
        match serde_json::from_str::<serde_json::Value>(&response) {
            Ok(v) => {
                let state = v.get("state").and_then(|s| s.as_str()).unwrap_or("?");
                let msg = v.get("message").and_then(|s| s.as_str()).unwrap_or("");
                let ok = v.get("ok").and_then(|b| b.as_bool()).unwrap_or(false);
                if want_text {
                    if let Some(t) = v
                        .get("data")
                        .and_then(|d| d.get("text"))
                        .and_then(|t| t.as_str())
                    {
                        println!("{t}");
                    } else {
                        println!("no pending text");
                    }
                } else if ok && v.get("data").and_then(|d| d.get("peak")).is_some() {
                    // mic-test: show levels so users can judge gain/source.
                    let d = v.get("data").unwrap();
                    let peak = d.get("peak").and_then(|x| x.as_f64()).unwrap_or(0.0);
                    let rms = d.get("rms").and_then(|x| x.as_f64()).unwrap_or(0.0);
                    let verdict = if rms > 0.02 {
                        "level OK"
                    } else {
                        "very quiet — check input gain/source"
                    };
                    println!("peak {peak:.3} rms {rms:.3} — {verdict}");
                } else if ok {
                    println!("{state}: {msg}");
                } else {
                    eprintln!("{state}: {msg}");
                    std::process::exit(1);
                }
            }
            Err(_) => println!("{response}"),
        }
        let _ = snapshot;
    }
    Ok(())
}
