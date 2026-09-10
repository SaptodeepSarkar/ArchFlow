//! `vaani`: short-lived CLI. Structured IPC only — never shell text with
//! dictated content. Commands: toggle, start, stop, cancel, status --json,
//! settings, doctor, copy, recover, discard, mic-test.

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
    #[command(name = "config-get")]
    ConfigGet,
    #[command(name = "config-set")]
    ConfigSet {
        key: String,
        value: String,
    },
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
    let kind = match args.cmd {
        Cmd::Toggle => RequestKind::Toggle,
        Cmd::Start => RequestKind::Start,
        Cmd::Stop => RequestKind::Stop,
        Cmd::Cancel => RequestKind::Cancel,
        Cmd::LiveToggle => RequestKind::LiveToggle,
        Cmd::Status { .. } => RequestKind::Status,
        Cmd::Settings => RequestKind::Settings,
        Cmd::Doctor => RequestKind::Doctor,
        Cmd::Copy => RequestKind::CopyPending,
        Cmd::Recover => RequestKind::RecoverPending,
        Cmd::Discard => RequestKind::DiscardPending,
        Cmd::MicTest { secs } => RequestKind::MicTest { secs },
        Cmd::ConfigGet => RequestKind::ConfigGet,
        Cmd::ConfigSet { key, value } => RequestKind::ConfigSet { key, value },
    };
    let as_json = matches!(kind, RequestKind::Status | RequestKind::Doctor | RequestKind::ConfigGet);
    let want_text = matches!(kind, RequestKind::RecoverPending);

    let mut req = Request::new(kind);
    req.session_id = None;

    let mut stream = UnixStream::connect(sock_path())
        .await
        .map_err(|_| anyhow::anyhow!("cannot reach vaanid — is the user service running? (systemctl --user status vaanid)"))?;
    let (r, mut w) = stream.split();
    let mut lines = BufReader::new(r).lines();
    // First line is the state snapshot.
    let snapshot = lines.next_line().await?.unwrap_or_default();
    w.write_all(req.to_line().unwrap().as_bytes()).await?;
    let response = lines.next_line().await?.unwrap_or_default();

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
                    if let Some(t) = v.get("data").and_then(|d| d.get("text")).and_then(|t| t.as_str()) {
                        println!("{t}");
                    } else {
                        println!("no pending text");
                    }
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
