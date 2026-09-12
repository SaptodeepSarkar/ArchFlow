mod capture;
mod clipboard;
mod cleanup;
mod daemon;
mod focus;
mod inserter;
mod llm_sup;
mod paths;
mod worker_sup;

use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "vaanid", about = "Vaani voice dictation controller")]
struct Args {
    #[arg(long)]
    foreground: bool,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let _args = Args::parse();
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "vaanid=info".into()),
        )
        .init();
    // Logs: state, timings, versions only. Never audio/transcripts/titles.
    tracing::info!(
        version = env!("CARGO_PKG_VERSION"),
        protocol = vaani_core::PROTOCOL_VERSION,
        "vaanid starting"
    );
    daemon::run().await
}
