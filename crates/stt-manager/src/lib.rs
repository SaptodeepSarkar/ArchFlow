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
