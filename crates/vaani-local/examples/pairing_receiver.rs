//! Disposable protocol interoperability harness. Never prints the invitation/token.
use std::{io::Write, sync::atomic::AtomicBool};
fn main() -> anyhow::Result<()> {
    let path = std::env::args()
        .nth(1)
        .ok_or_else(|| anyhow::anyhow!("invitation file required"))?;
    let receiver = vaani_local::pairing::Receiver::new("127.0.0.1")?;
    let mut options = std::fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    options
        .open(&path)?
        .write_all(receiver.invitation.encode()?.as_bytes())?;
    let bundle = receiver.receive(&AtomicBool::new(false))?;
    std::fs::remove_file(path)?;
    println!(
        "Received validated interoperable bundle: {} records",
        bundle.records.len()
    );
    Ok(())
}
