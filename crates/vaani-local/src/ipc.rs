use std::{
    io::{BufRead, BufReader, Write},
    os::unix::net::UnixStream,
    path::PathBuf,
    time::Duration,
};
use vaani_core::protocol::{Request, RequestKind, Response};
pub fn socket_path() -> PathBuf {
    let root = std::env::var_os("XDG_RUNTIME_DIR")
        .map(|p| PathBuf::from(p).join("vaani"))
        .unwrap_or_else(|| {
            PathBuf::from(format!(
                "/tmp/vaani-{}",
                std::env::var("UID").unwrap_or("1000".into())
            ))
        });
    root.join("control.sock")
}
pub fn subscribe(
    mut callback: impl FnMut(vaani_core::protocol::Event) -> bool,
) -> anyhow::Result<()> {
    let mut socket = UnixStream::connect(socket_path())?;
    socket.write_all(Request::new(RequestKind::Subscribe).to_line()?.as_bytes())?;
    let mut reader = BufReader::new(socket);
    loop {
        use std::io::Read;
        let mut line = String::new();
        std::io::Read::by_ref(&mut reader)
            .take(vaani_core::MAX_CONTROL_BYTES as u64 + 1)
            .read_line(&mut line)?;
        anyhow::ensure!(
            !line.is_empty() && line.len() <= vaani_core::MAX_CONTROL_BYTES,
            "subscription ended"
        );
        if let Ok(event) = serde_json::from_str(&line) {
            if !callback(event) {
                return Ok(());
            }
        }
    }
}
pub fn request(kind: RequestKind) -> anyhow::Result<Response> {
    let mut socket = UnixStream::connect(socket_path())?;
    socket.set_read_timeout(Some(Duration::from_secs(8)))?;
    socket.set_write_timeout(Some(Duration::from_secs(8)))?;
    let request = Request::new(kind);
    socket.write_all(request.to_line()?.as_bytes())?;
    let mut reader = BufReader::new(socket);
    for _ in 0..128 {
        let mut line = String::new();
        use std::io::Read;
        std::io::Read::by_ref(&mut reader)
            .take(vaani_core::MAX_CONTROL_BYTES as u64 + 1)
            .read_line(&mut line)?;
        anyhow::ensure!(
            !line.is_empty() && line.len() <= vaani_core::MAX_CONTROL_BYTES,
            "invalid daemon response"
        );
        if let Ok(response) = serde_json::from_str::<Response>(&line) {
            if response.request_id == request.request_id {
                anyhow::ensure!(
                    response.ok,
                    "{}",
                    response.message.as_deref().unwrap_or("Operation failed")
                );
                return Ok(response);
            }
        }
    }
    anyhow::bail!("daemon response limit")
}
