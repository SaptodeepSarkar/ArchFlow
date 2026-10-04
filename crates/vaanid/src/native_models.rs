//! Model leases over private inherited pipes. One owner, bounded RPC and idle expiry.
use std::{
    io::{BufReader, Read, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{Arc, Condvar, Mutex, OnceLock},
    time::{Duration, Instant},
};

pub enum Kind {
    Speech,
    Formatter,
}
struct State {
    process: Option<Session>,
    deadline: Option<Instant>,
    timer: bool,
}
struct Cache {
    state: Mutex<State>,
    changed: Condvar,
}
impl Cache {
    fn new() -> Self {
        Self {
            state: Mutex::new(State {
                process: None,
                deadline: None,
                timer: false,
            }),
            changed: Condvar::new(),
        }
    }
}
static SPEECH: OnceLock<Arc<Cache>> = OnceLock::new();
static FORMATTER: OnceLock<Arc<Cache>> = OnceLock::new();
fn cache(kind: &Kind) -> Arc<Cache> {
    match kind {
        Kind::Speech => &SPEECH,
        Kind::Formatter => &FORMATTER,
    }
    .get_or_init(|| Arc::new(Cache::new()))
    .clone()
}
fn helper(kind: &Kind) -> PathBuf {
    let name = match kind {
        Kind::Speech => "vaani-whisper-session",
        Kind::Formatter => "vaani-llama-session",
    };
    if let Some(dir) = std::env::var_os("VAANI_NATIVE_RUNTIME_DIR") {
        return PathBuf::from(dir).join(name);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let path = dir.join(name);
            if path.is_file() {
                return path;
            }
        }
    }
    PathBuf::from(name)
}
pub struct Session {
    child: Child,
    input: Option<ChildStdin>,
    output: Option<BufReader<ChildStdout>>,
    identity: String,
}
impl Drop for Session {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}
impl Session {
    fn open(binary: &Path, model: &Path, identity: String) -> anyhow::Result<Self> {
        let mut child = Command::new(binary)
            .arg(model)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?;
        Ok(Self {
            input: child.stdin.take(),
            output: child.stdout.take().map(BufReader::new),
            child,
            identity,
        })
    }
    pub fn request(
        &mut self,
        metadata: serde_json::Value,
        pcm: Option<Vec<u8>>,
    ) -> anyhow::Result<serde_json::Value> {
        let body = serde_json::to_vec(&metadata)?;
        anyhow::ensure!(
            body.len() <= 65536 && pcm.as_ref().is_none_or(|p| p.len() <= 120 * 16000 * 4),
            "native input limit"
        );
        let mut input = self
            .input
            .take()
            .ok_or_else(|| anyhow::anyhow!("native input unavailable"))?;
        let mut output = self
            .output
            .take()
            .ok_or_else(|| anyhow::anyhow!("native output unavailable"))?;
        let (tx, rx) = std::sync::mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let result = (|| -> anyhow::Result<serde_json::Value> {
                input.write_all(&(body.len() as u32).to_be_bytes())?;
                input.write_all(&body)?;
                if let Some(pcm) = pcm {
                    input.write_all(&(pcm.len() as u32).to_be_bytes())?;
                    input.write_all(&pcm)?;
                }
                input.flush()?;
                let mut header = [0; 4];
                output.read_exact(&mut header)?;
                let size = u32::from_be_bytes(header) as usize;
                anyhow::ensure!(size > 0 && size <= 65536, "native output limit");
                let mut body = vec![0; size];
                output.read_exact(&mut body)?;
                let value: serde_json::Value = serde_json::from_slice(&body)?;
                anyhow::ensure!(value.get("error").is_none(), "native inference failed");
                Ok(value)
            })();
            let _ = tx.send((input, output, result));
        });
        match rx.recv_timeout(Duration::from_secs(60)) {
            Ok((input, output, result)) => {
                self.input = Some(input);
                self.output = Some(output);
                result
            }
            Err(_) => {
                let _ = self.child.kill();
                let _ = self.child.wait();
                anyhow::bail!("native inference timed out")
            }
        }
    }
}
fn expire(cache: Arc<Cache>) {
    let mut state = cache.state.lock().unwrap_or_else(|e| e.into_inner());
    loop {
        let Some(deadline) = state.deadline else {
            state.timer = false;
            return;
        };
        let wait = deadline.saturating_duration_since(Instant::now());
        if wait.is_zero() {
            state.process = None;
            state.deadline = None;
            state.timer = false;
            return;
        }
        state = cache
            .changed
            .wait_timeout(state, wait)
            .unwrap_or_else(|e| e.into_inner())
            .0;
    }
}
pub fn with_session<T>(
    kind: Kind,
    model: &Path,
    seconds: u64,
    operation: impl FnOnce(&mut Session) -> anyhow::Result<T>,
) -> anyhow::Result<T> {
    with_cache(cache(&kind), &helper(&kind), model, seconds, operation)
}
fn with_cache<T>(
    cache: Arc<Cache>,
    binary: &Path,
    model: &Path,
    seconds: u64,
    operation: impl FnOnce(&mut Session) -> anyhow::Result<T>,
) -> anyhow::Result<T> {
    let metadata = std::fs::metadata(model)?;
    let identity = format!(
        "{}:{}:{:?}",
        model.display(),
        metadata.len(),
        metadata.modified()?
    );
    let mut state = cache
        .state
        .lock()
        .map_err(|_| anyhow::anyhow!("native ownership poisoned"))?;
    if state
        .process
        .as_ref()
        .is_none_or(|p| p.identity != identity)
    {
        state.process = None;
        state.deadline = None;
        state.process = Some(Session::open(binary, model, identity)?);
    }
    let result = operation(state.process.as_mut().unwrap());
    if result.is_err() || seconds == 0 {
        state.process = None;
        state.deadline = None;
    } else {
        state.deadline = Some(Instant::now() + Duration::from_secs(seconds.min(120)));
        if !state.timer {
            state.timer = true;
            let timer = cache.clone();
            std::thread::spawn(move || expire(timer));
        }
    }
    cache.changed.notify_all();
    result
}
pub fn unload() {
    for slot in [&SPEECH, &FORMATTER] {
        if let Some(cache) = slot.get() {
            let mut state = cache.state.lock().unwrap_or_else(|e| e.into_inner());
            state.process = None;
            state.deadline = None;
            cache.changed.notify_all();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn lease_reuses_process_and_economy_releases_it() {
        use std::os::unix::fs::PermissionsExt;
        let root = std::env::temp_dir().join(format!("vaani-model-lease-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(&root).unwrap();
        let binary = root.join("fake");
        let model = root.join("model");
        std::fs::write(&model, b"fixture").unwrap();
        std::fs::write(&binary,"#!/usr/bin/env python3\nimport sys,struct,json,os\nwhile True:\n h=sys.stdin.buffer.read(4)\n if not h: break\n n=struct.unpack('>I',h)[0];sys.stdin.buffer.read(n)\n b=json.dumps({'pid':os.getpid()}).encode();sys.stdout.buffer.write(struct.pack('>I',len(b))+b);sys.stdout.buffer.flush()\n").unwrap();
        std::fs::set_permissions(&binary, std::fs::Permissions::from_mode(0o700)).unwrap();
        let cache = Arc::new(Cache::new());
        let first = with_cache(cache.clone(), &binary, &model, 1, |p| {
            p.request(serde_json::json!({}), None)
        })
        .unwrap();
        let second = with_cache(cache.clone(), &binary, &model, 1, |p| {
            p.request(serde_json::json!({}), None)
        })
        .unwrap();
        assert_eq!(first, second);
        std::thread::sleep(Duration::from_millis(1250));
        assert!(cache.state.lock().unwrap().process.is_none());
        with_cache(cache.clone(), &binary, &model, 0, |p| {
            p.request(serde_json::json!({}), None)
        })
        .unwrap();
        assert!(cache.state.lock().unwrap().process.is_none());
        std::fs::remove_dir_all(root).unwrap();
    }
}
