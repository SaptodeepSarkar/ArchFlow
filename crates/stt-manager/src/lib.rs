//! On-demand STT: streams words from 16kHz mono audio, then unloads fully.
//!
//! Engine is Vosk (CPU, reused from Kyuma's install: zero downloads, zero
//! VRAM) driven through `backend/transcribe.py` in a child process. The Rust
//! side owns device pick, word-stream parsing, RTF accounting, and the
//! busy/killable contract the key service polls before offloading (Phase 09).
//! Unload = child reaped + model memory freed on process exit; the gate
//! proves it via `nvidia-smi` back to baseline plus no lingering backend.

use std::io::{BufRead, BufReader};
use std::process::{Child, ChildStdout, Command, Stdio};
use std::sync::mpsc;

/// 16kHz mono s16le: the only format the backend accepts.
pub const SAMPLE_RATE: u32 = 16_000;
/// Gate threshold: decode must cost under 0.3x audio duration on RTX 3050 box.
pub const RTF_LIMIT: f64 = 0.3;
/// Candidate interpreters that may have `vosk` importable.
const KYUMA_VENV_PYTHON: &str = "/home/saptodeep/Projects/Kyuma/.venv/bin/python";
/// Reused model (Kyuma's): 68MB, CPU, no download.
const DEFAULT_MODEL: &str = "/home/saptodeep/Projects/Kyuma/models/vosk-model-small-en-us-0.15";
const FALLBACK_MODEL: &str = "/home/saptodeep/Projects/Kyuma/models/vosk-model-small-en-in-0.4";

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Device {
    /// dGPU present (VRAM untouched: engine is CPU, but tier stays `small`).
    DGpu,
    /// No dGPU: same CPU engine, model tier drops to the fallback if needed.
    Cpu,
}

/// First-run pick: dGPU when `nvidia-smi` lists one, else CPU fallback.
pub fn pick_device() -> Device {
    let dgpu = Command::new("nvidia-smi")
        .arg("-L")
        .output()
        .map(|o| o.status.success() && !o.stdout.is_empty())
        .unwrap_or(false);
    if dgpu {
        Device::DGpu
    } else {
        Device::Cpu
    }
}

/// First interpreter whose `import vosk` succeeds.
pub fn resolve_python() -> Option<String> {
    let mut cands = vec![];
    if let Ok(p) = std::env::var("VAANI_STT_PYTHON") {
        cands.push(p);
    }
    cands.push(KYUMA_VENV_PYTHON.into());
    cands.push("python3".into());
    cands.into_iter().find(|p| {
        Command::new(p)
            .args(["-c", "import vosk"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|s| s.success())
            .unwrap_or(false)
    })
}

/// Model dir: env override, else default; falls back to the second
/// Kyuma model when the default is missing (weak-machine tier drop).
pub fn resolve_model() -> Option<String> {
    if let Ok(m) = std::env::var("VAANI_STT_MODEL") {
        if std::path::Path::new(&m).is_dir() {
            return Some(m);
        }
    }
    for m in [DEFAULT_MODEL, FALLBACK_MODEL] {
        if std::path::Path::new(m).is_dir() {
            return Some(m.to_string());
        }
    }
    None
}

fn backend_path() -> std::path::PathBuf {
    // Installed trees set VAANI_STT_BACKEND (install.sh ships the script to
    // share/vaani). The compile-time path is only right for a dev checkout:
    // a release tarball built on a CI runner would otherwise embed the
    // runner's directory.
    if let Ok(p) = std::env::var("VAANI_STT_BACKEND") {
        return p.into();
    }
    let mut p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    p.push("backend/transcribe.py");
    p
}

/// One streamed word; `t` is seconds since stream start.
pub struct Word {
    pub text: String,
    pub t: f64,
}

#[derive(Default)]
pub struct Stats {
    pub words: usize,
    pub audio_secs: f64,
    pub infer_secs: f64,
}

impl Stats {
    pub fn rtf(&self) -> f64 {
        if self.audio_secs > 0.0 {
            self.infer_secs / self.audio_secs
        } else {
            f64::INFINITY
        }
    }
}

/// Live transcription session. Busy while the backend child runs; killable
/// once words are drained and the child is reaped (model memory freed).
pub struct Session {
    child: Option<Child>,
    lines: Option<std::io::Lines<BufReader<ChildStdout>>>,
    stats: Stats,
    done: bool,
    stderr_tail: String,
}

impl Session {
    /// Load the model (backend process start) and open the word stream.
    pub fn start(wav: &str, python: &str, model: &str) -> std::io::Result<Self> {
        let mut child = Command::new(python)
            .arg(backend_path())
            .args(["--wav", wav])
            .env("VAANI_STT_MODEL", model)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .stdin(Stdio::null())
            .spawn()?;
        let out = child.stdout.take();
        Ok(Self {
            child: Some(child),
            lines: out.map(|o| BufReader::new(o).lines()),
            stats: Stats::default(),
            done: false,
            stderr_tail: String::new(),
        })
    }

    /// Next word, or `None` at end of stream. Blocks on the backend.
    pub fn next_word(&mut self) -> Option<Word> {
        loop {
            let line = self.lines.as_mut()?.next()?.ok()?;
            let line = line.trim().to_string();
            if let Some(rest) = line.strip_prefix("W ") {
                let mut it = rest.splitn(2, ' ');
                let t: f64 = it.next()?.parse().ok()?;
                let text = it.next()?.to_string();
                if text.is_empty() {
                    continue;
                }
                self.stats.words += 1;
                return Some(Word { text, t });
            }
            if let Some(rest) = line.strip_prefix("DONE ") {
                for kv in rest.split_whitespace() {
                    let mut kv = kv.splitn(2, '=');
                    let (k, v) = (kv.next()?, kv.next()?);
                    match k {
                        "audio" => self.stats.audio_secs = v.parse().unwrap_or(0.0),
                        "infer" => self.stats.infer_secs = v.parse().unwrap_or(0.0),
                        _ => {}
                    }
                }
                self.done = true;
                return None;
            }
        }
    }

    /// True while decoding. Helpers reporting busy must not be killed.
    pub fn is_busy(&mut self) -> bool {
        if self.done {
            return false;
        }
        match self.child.as_mut() {
            None => false,
            Some(c) => c.try_wait().map(|s| s.is_none()).unwrap_or(false),
        }
    }

    /// True when safe to offload: stream drained or never started.
    pub fn is_killable(&mut self) -> bool {
        !self.is_busy()
    }

    /// Drain remaining words, reap the child (frees model memory), return stats.
    /// Safe to call twice; second call is a no-op.
    pub fn finish(&mut self) -> std::io::Result<Stats> {
        while self.next_word().is_some() {}
        self.unload();
        // Surface backend errors (bad wav, missing model) with its stderr tail.
        if !self.done && !self.stderr_tail.is_empty() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("backend failed: {}", self.stderr_tail),
            ));
        }
        Ok(std::mem::take(&mut self.stats))
    }

    /// Kill + reap the backend. After this the model is fully unloaded.
    pub fn unload(&mut self) {
        self.lines = None;
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            if let Ok(out) = c.wait_with_output() {
                let err = String::from_utf8_lossy(&out.stderr);
                let tail: Vec<&str> = err.lines().collect();
                let n = tail.len();
                self.stderr_tail = tail[n.saturating_sub(3)..].join(" | ");
            }
            if self.done {
                self.stderr_tail.clear();
            }
        }
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        self.unload();
    }
}

/// Event from a [`LiveSession`].
pub enum LiveEvent {
    /// A finalized word (already counted in stats).
    Word(Word),
    /// Current partial phrase: what Vosk thinks is being said right now.
    Partial(String),
    /// Stream ended; final stats.
    Done(Stats),
}

fn parse_word(rest: &str) -> Option<Word> {
    let mut it = rest.splitn(2, ' ');
    let t: f64 = it.next()?.parse().ok()?;
    let text = it.next()?.to_string();
    if text.is_empty() {
        None
    } else {
        Some(Word { text, t })
    }
}

fn parse_done(rest: &str, stats: &mut Stats) {
    for kv in rest.split_whitespace() {
        let mut kv = kv.splitn(2, '=');
        match (kv.next(), kv.next()) {
            (Some("audio"), Some(v)) => stats.audio_secs = v.parse().unwrap_or(0.0),
            (Some("infer"), Some(v)) => stats.infer_secs = v.parse().unwrap_or(0.0),
            _ => {}
        }
    }
}

/// Live transcription over a growing PCM stream: the caller feeds mic chunks
/// while recording and gets partial phrases plus finalized words back, so a
/// UI can show words as they are spoken. Unload (child reaped) frees the
/// model exactly like [`Session`].
pub struct LiveSession {
    child: Option<Child>,
    stdin: Option<std::process::ChildStdin>,
    events: mpsc::Receiver<LiveEvent>,
    stderr_tail: String,
}

impl LiveSession {
    /// Load the model and start streaming (`backend/transcribe.py --stream`).
    pub fn start(python: &str, model: &str) -> std::io::Result<Self> {
        let mut child = Command::new(python)
            .arg(backend_path())
            .arg("--stream")
            .env("VAANI_STT_MODEL", model)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .stdin(Stdio::piped())
            .spawn()?;
        let stdin = child.stdin.take();
        let stdout = child.stdout.take();
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let mut stats = Stats::default();
            if let Some(out) = stdout {
                for line in BufReader::new(out).lines() {
                    let Ok(line) = line else { break };
                    let line = line.trim().to_string();
                    if let Some(rest) = line.strip_prefix("W ") {
                        if let Some(w) = parse_word(rest) {
                            stats.words += 1;
                            if tx.send(LiveEvent::Word(w)).is_err() {
                                return;
                            }
                        }
                    } else if let Some(rest) = line.strip_prefix("P ") {
                        // "P <t> <phrase>"; the phrase may be empty.
                        let phrase = rest.splitn(2, ' ').nth(1).unwrap_or("").to_string();
                        if tx.send(LiveEvent::Partial(phrase)).is_err() {
                            return;
                        }
                    } else if let Some(rest) = line.strip_prefix("DONE ") {
                        parse_done(rest, &mut stats);
                        let _ = tx.send(LiveEvent::Done(stats));
                        return;
                    }
                }
            }
            let _ = tx.send(LiveEvent::Done(stats));
        });
        Ok(Self {
            child: Some(child),
            stdin,
            events: rx,
            stderr_tail: String::new(),
        })
    }

    /// Push captured PCM (raw s16le mono 16kHz) into the recognizer.
    pub fn feed(&mut self, pcm: &[u8]) -> std::io::Result<()> {
        use std::io::Write;
        match self.stdin.as_mut() {
            Some(s) => s.write_all(pcm),
            None => Ok(()),
        }
    }

    /// Drain everything decoded so far without blocking.
    pub fn poll(&mut self) -> Vec<LiveEvent> {
        let mut out = Vec::new();
        while let Ok(ev) = self.events.try_recv() {
            out.push(ev);
        }
        out
    }

    /// Close the stream, wait for the backend's finals and reap the child.
    /// Words flushed after the last [`LiveSession::poll`] (which is where
    /// Vosk emits the tail of an utterance) are handed to `on_word`, so they
    /// can never be dropped on the floor.
    /// Safe to call twice; the second call returns empty stats.
    pub fn finish(&mut self, on_word: &mut dyn FnMut(&Word)) -> std::io::Result<Stats> {
        self.stdin = None; // EOF: backend flushes finals and exits
        let mut stats = Stats::default();
        let mut saw_done = false;
        loop {
            match self.events.recv_timeout(std::time::Duration::from_secs(20)) {
                Ok(LiveEvent::Done(s)) => {
                    stats = s;
                    saw_done = true;
                    break;
                }
                Ok(LiveEvent::Word(w)) => {
                    stats.words += 1;
                    on_word(&w);
                }
                Ok(_) => {}
                Err(_) => break,
            }
        }
        self.unload();
        if !saw_done && !self.stderr_tail.is_empty() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("backend failed: {}", self.stderr_tail),
            ));
        }
        Ok(stats)
    }

    /// Kill + reap the backend: after this the model is fully unloaded.
    pub fn unload(&mut self) {
        self.stdin = None;
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            if let Ok(out) = c.wait_with_output() {
                let err = String::from_utf8_lossy(&out.stderr);
                let tail: Vec<&str> = err.lines().collect();
                let n = tail.len();
                self.stderr_tail = tail[n.saturating_sub(3)..].join(" | ");
            }
        }
    }
}

impl Drop for LiveSession {
    fn drop(&mut self) {
        self.unload();
    }
}

/// One-shot helper: transcribe `wav`, calling `on_word` per streamed word.
pub fn transcribe_wav(
    wav: &str,
    python: &str,
    model: &str,
    on_word: &mut dyn FnMut(&Word),
) -> std::io::Result<Stats> {
    let mut s = Session::start(wav, python, model)?;
    while let Some(w) = s.next_word() {
        on_word(&w);
    }
    s.finish()
}

/// One-shot helper: transcribe RAM-held PCM (16kHz mono s16le) via the
/// backend's `--stdin` mode. Nothing touches disk: bytes go through the
/// child pipe. This is the live-daemon path (audio-helper hands RAM here).
pub fn transcribe_pcm(
    pcm: &[i16],
    python: &str,
    model: &str,
    on_word: &mut dyn FnMut(&Word),
) -> std::io::Result<Stats> {
    run_stdin(
        pcm,
        python,
        &backend_path(),
        &[("VAANI_STT_MODEL", model.to_string())],
        on_word,
    )
}

/// End-of-utterance re-decode with the fine-tuned model.
///
/// Separate from `transcribe_pcm` because it runs a *different* backend (the
/// re-decode client) and the model itself lives in a resident server, not in
/// this process: only its endpoint is handed to the child.
pub fn refine_pcm(
    pcm: &[i16],
    python: &str,
    backend: &str,
    endpoint: &str,
    on_word: &mut dyn FnMut(&Word),
) -> std::io::Result<Stats> {
    run_stdin(
        pcm,
        python,
        std::path::Path::new(backend),
        &[("VAANI_STT_REFINE_ENDPOINT", endpoint.to_string())],
        on_word,
    )
}

/// Raw captured bytes -> i16 samples a backend accepts (odd byte dropped).
pub fn bytes_to_pcm(bytes: &[u8]) -> Vec<i16> {
    bytes[..bytes.len() & !1]
        .chunks_exact(2)
        .map(|b| i16::from_le_bytes([b[0], b[1]]))
        .collect()
}

/// Everything the optional second pass needs to run.
pub struct Refine {
    pub python: String,
    pub backend: String,
    pub endpoint: String,
}

/// The fine-tuned re-decode is opt-in: `None` here leaves the pipeline exactly
/// as it was, streaming words are the final words. Enabled only when
/// `VAANI_STT_REFINE_BACKEND` names a script that exists, so a box without the
/// model behaves as before instead of failing runs.
pub fn resolve_refine(default_python: &str) -> Option<Refine> {
    let backend = std::env::var("VAANI_STT_REFINE_BACKEND").ok()?;
    if !std::path::Path::new(&backend).is_file() {
        return None;
    }
    Some(Refine {
        python: std::env::var("VAANI_STT_REFINE_PYTHON")
            .unwrap_or_else(|_| default_python.to_string()),
        backend,
        endpoint: std::env::var("VAANI_STT_REFINE_ENDPOINT")
            .unwrap_or_else(|_| "http://127.0.0.1:8083".to_string()),
    })
}

/// Shared `--stdin` driver: spawn a backend, hand it PCM, collect `W`/`DONE`.
fn run_stdin(
    pcm: &[i16],
    python: &str,
    backend: &std::path::Path,
    env: &[(&str, String)],
    on_word: &mut dyn FnMut(&Word),
) -> std::io::Result<Stats> {
    use std::io::Write;
    let mut cmd = Command::new(python);
    cmd.arg(backend)
        .arg("--stdin")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .stdin(Stdio::piped());
    for (k, v) in env {
        cmd.env(k, v);
    }
    let mut child = cmd.spawn()?;
    if let Some(mut stdin) = child.stdin.take() {
        let mut bytes = Vec::with_capacity(pcm.len() * 2);
        for s in pcm {
            bytes.extend_from_slice(&s.to_le_bytes());
        }
        let _ = stdin.write_all(&bytes);
    }
    let out = child.stdout.take();
    let mut lines = out.map(|o| BufReader::new(o).lines());
    let mut stats = Stats::default();
    let mut done = false;
    let mut stderr_tail = String::new();
    while let Some(line) = lines.as_mut().and_then(|l| l.next()) {
        let line = line.unwrap_or_default();
        let line = line.trim().to_string();
        if let Some(rest) = line.strip_prefix("W ") {
            let mut it = rest.splitn(2, ' ');
            if let (Some(t), Some(text)) = (it.next(), it.next()) {
                if let Ok(t) = t.parse::<f64>() {
                    if !text.is_empty() {
                        stats.words += 1;
                        on_word(&Word { text: text.to_string(), t });
                    }
                }
            }
        } else if let Some(rest) = line.strip_prefix("DONE ") {
            for kv in rest.split_whitespace() {
                let mut kv = kv.splitn(2, '=');
                match (kv.next(), kv.next()) {
                    (Some("audio"), Some(v)) => stats.audio_secs = v.parse().unwrap_or(0.0),
                    (Some("infer"), Some(v)) => stats.infer_secs = v.parse().unwrap_or(0.0),
                    _ => {}
                }
            }
            done = true;
        }
    }
    if let Ok(out) = child.wait_with_output() {
        let err = String::from_utf8_lossy(&out.stderr);
        let tail: Vec<&str> = err.lines().collect();
        let n = tail.len();
        stderr_tail = tail[n.saturating_sub(3)..].join(" | ");
    }
    if !done && !stderr_tail.is_empty() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::Other,
            format!("backend failed: {stderr_tail}"),
        ));
    }
    Ok(stats)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Set env vars for the duration of `f`, then put them back. Tests in a
    /// crate share a process, so every caller passes the keys it depends on.
    fn with_env<T>(vars: &[(&str, Option<&str>)], f: impl FnOnce() -> T) -> T {
        let old: Vec<(String, Option<String>)> = vars
            .iter()
            .map(|(k, _)| (k.to_string(), std::env::var(k).ok()))
            .collect();
        for (k, v) in vars {
            match v {
                Some(v) => std::env::set_var(k, v),
                None => std::env::remove_var(k),
            }
        }
        let out = f();
        for (k, v) in old {
            match v {
                Some(v) => std::env::set_var(&k, v),
                None => std::env::remove_var(&k),
            }
        }
        out
    }

    #[test]
    fn bytes_to_pcm_pairs_little_endian_and_drops_a_stray_byte() {
        assert_eq!(bytes_to_pcm(&[0x01, 0x00, 0xff, 0xff]), vec![1, -1]);
        assert_eq!(bytes_to_pcm(&[0x01, 0x00, 0x7f]), vec![1]);
        assert!(bytes_to_pcm(&[]).is_empty());
    }

    #[test]
    fn refine_stays_off_unless_a_real_script_is_configured() {
        // The default must be the single-pass pipeline: a stale or wrong path
        // would otherwise turn every run into a failed second pass.
        let off = with_env(
            &[
                ("VAANI_STT_REFINE_BACKEND", None),
                ("VAANI_STT_REFINE_ENDPOINT", None),
                ("VAANI_STT_REFINE_PYTHON", None),
            ],
            || resolve_refine("python3"),
        );
        assert!(off.is_none(), "unset backend must keep the pipeline single-pass");

        let missing = with_env(
            &[("VAANI_STT_REFINE_BACKEND", Some("/nonexistent/refine.py"))],
            || resolve_refine("python3"),
        );
        assert!(missing.is_none(), "a backend path that does not exist is ignored");

        // Any existing file stands in for the client script.
        let script = concat!(env!("CARGO_MANIFEST_DIR"), "/src/lib.rs");
        let on = with_env(
            &[
                ("VAANI_STT_REFINE_BACKEND", Some(script)),
                ("VAANI_STT_REFINE_ENDPOINT", None),
                ("VAANI_STT_REFINE_PYTHON", None),
            ],
            || resolve_refine("python3"),
        )
        .expect("an existing backend enables the second pass");
        assert_eq!(on.python, "python3");
        assert_eq!(on.endpoint, "http://127.0.0.1:8083");
        assert_eq!(on.backend, script);
    }
}
