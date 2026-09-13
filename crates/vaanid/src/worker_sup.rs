//! Worker supervision: spawn `vaani-worker` per dictation (Economy default),
//! pipe bounded PCM via inherited stdin, read one JSON line from stdout.
//! A worker crash leaves the controller operational (Err, state -> ERROR).
//!
//! Streaming exception: directory models (fine-tuned CTranslate2) run
//! through a persistent `fw-server.py` sidecar that loads once and answers
//! JSON jobs in ~0.3 s. Per-call reloads (~4.5 s) would make live preview
//! ticks useless. The server is reaped after configured idle seconds, so
//! VRAM is only held while dictating. Must be driven from blocking threads
//! (spawn_blocking): all child IO here is synchronous.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Stdio};
use vaani_core::reconcile::reconcile;
use vaani_core::segment::segment;

#[derive(Debug, Clone)]
pub struct Transcript {
    pub text: String,
    pub language: String,
    pub is_silence: bool,
    pub backend: String,
    pub inference_ms: u64,
}

/// Own a private transient directory containing audio. Removal is guaranteed
/// on every return path, including sidecar and JSON protocol failures.
struct TempAudioDir(std::path::PathBuf);

impl TempAudioDir {
    fn create(prefix: &str, id: u64) -> std::io::Result<Self> {
        let path = std::env::temp_dir().join(format!("{prefix}-{}-{id}", std::process::id()));
        // `create_dir`, rather than create_dir_all, refuses a pre-existing
        // attacker-controlled path in the shared temp directory.
        std::fs::create_dir(&path)?;
        Ok(Self(path))
    }

    fn join(&self, name: &str) -> std::path::PathBuf { self.0.join(name) }
}

impl Drop for TempAudioDir {
    fn drop(&mut self) { let _ = std::fs::remove_dir_all(&self.0); }
}

pub fn worker_bin() -> String {
    // Same install prefix as the daemon: prefer sibling binary on PATH,
    // else VAANI_WORKER_BIN override (packaging/tests).
    if let Ok(p) = std::env::var("VAANI_WORKER_BIN") {
        if !p.is_empty() {
            return p;
        }
    }
    // Sibling of this executable: robust under systemd's minimal PATH for
    // both ~/.local/bin and /usr/bin installs.
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let sib = dir.join("vaani-worker");
            if sib.exists() {
                return sib.to_string_lossy().into_owned();
            }
        }
    }
    "vaani-worker".into()
}

/// Silero VAD binary (whisper.cpp vad-speech-segments) for end-of-speech
/// gating. Env override, user-local bin, daemon sibling dir, then PATH.
pub fn vad_bin() -> Option<String> {
    if let Ok(p) = std::env::var("VAANI_VAD_BIN") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return Some(p);
        }
    }
    let mut dirs: Vec<String> = vec![];
    if let Ok(home) = std::env::var("HOME") {
        dirs.push(format!("{home}/.local/bin"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            dirs.push(dir.to_string_lossy().into_owned());
        }
    }
    dirs.extend(std::env::var("PATH").unwrap_or_default().split(':').map(|s| s.to_string()));
    for dir in &dirs {
        let p = format!("{dir}/vad-speech-segments");
        if std::path::Path::new(&p).exists() {
            return Some(p);
        }
    }
    None
}

/// Silero end-of-speech analysis: returns (speech_seen, trailing_silence_s)
/// for the given mono 16 kHz samples. None = VAD binary unavailable (caller
/// falls back to the energy gate).
pub fn silero_trailing(samples: &[f32]) -> Option<(bool, f32)> {
    let bin = vad_bin()?;
    if samples.len() < 16_000 {
        return Some((false, 0.0)); // too short to judge
    }
    static VAD_JOB_ID: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);
    let jid = VAD_JOB_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dir = TempAudioDir::create("vaani-vad", jid).ok()?;
    let wav = dir.join("in.wav");
    write_wav_mono16(&wav, samples).ok()?;
    let vad_model = vad_model_default();
    let mut cmd = std::process::Command::new(&bin);
    cmd.arg("-t").arg("2").arg("-f").arg(&wav);
    if let Some(vm) = vad_model {
        cmd.arg("-vm").arg(vm);
    }
    let out = cmd.output().ok()?;
    if !out.status.success() {
        return None;
    }
    let text = String::from_utf8_lossy(&out.stdout);
    let total_s = samples.len() as f32 / 16_000.0;
    match parse_vad_ends(&text) {
        Some(last_end_cs) => Some((true, (total_s - last_end_cs / 100.0).max(0.0))),
        None => Some((false, total_s)),
    }
}

/// Parse `vad-speech-segments` output ("Speech segment N: start = X, end = Y",
/// centiseconds). Returns the last segment end, or None when no speech.
fn parse_vad_ends(text: &str) -> Option<f32> {
    let mut last_end_cs: Option<f32> = None;
    for line in text.lines() {
        // "Speech segment 3: start = 538.00, end = 765.00" (centiseconds)
        if let Some(rest) = line.split("end = ").nth(1) {
            if let Ok(v) = rest.trim().split_whitespace().next().unwrap_or("").parse::<f32>() {
                last_end_cs = Some(v);
            }
        }
    }
    last_end_cs
}

// ---- Persistent faster-whisper server (streaming STT) ----

/// Trim leading/trailing sub-threshold samples, keeping `margin` samples of
/// context on each side. Returns the trimmed slice (possibly empty).
fn trim_silence(samples: &[f32], thresh: f32, margin: usize) -> &[f32] {
    let first = samples.iter().position(|&x| x.abs() >= thresh);
    let last = samples.iter().rposition(|&x| x.abs() >= thresh);
    match (first, last) {
        (Some(f), Some(l)) => {
            let s = f.saturating_sub(margin);
            let e = (l + margin + 1).min(samples.len());
            &samples[s..e]
        }
        _ => &[],
    }
}

struct FwServer {
    child: Child,
    writer: ChildStdin,
    reader: Option<BufReader<ChildStdout>>,
    model_dir: String,
    last_use: std::time::Instant,
}

static FW_SERVER: std::sync::OnceLock<std::sync::Mutex<Option<FwServer>>> =
    std::sync::OnceLock::new();

fn fw_slot() -> &'static std::sync::Mutex<Option<FwServer>> {
    FW_SERVER.get_or_init(|| std::sync::Mutex::new(None))
}

static FW_JOB_ID: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);

fn fw_python_path() -> String {
    if let Ok(p) = std::env::var("VAANI_FW_PYTHON") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return p;
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let venv = format!("{home}/Projects/Cozy/stt-finetune/.venv/bin/python");
        if std::path::Path::new(&venv).exists() {
            return venv;
        }
    }
    "python3".into()
}

fn fw_server_script() -> String {
    if let Ok(p) = std::env::var("VAANI_FW_SCRIPT_SERVER") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return p;
        }
    }
    // Sibling of the daemon binary (user-local install lays both side by side).
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let sib = dir.join("fw-server.py");
            if sib.exists() {
                return sib.to_string_lossy().into_owned();
            }
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let p = format!("{home}/.local/bin/fw-server.py");
        if std::path::Path::new(&p).exists() {
            return p;
        }
    }
    "fw-server.py".into()
}

fn fw_lib_env(cmd: &mut std::process::Command) {
    let mut dirs: Vec<String> = Vec::new();
    if let Ok(cur) = std::env::var("LD_LIBRARY_PATH") {
        dirs.extend(cur.split(':').map(|s| s.to_string()));
    }
    for cand in [
        "/usr/local/lib/ollama/cuda_v12",
        "/opt/cuda/lib64",
        "/usr/local/cuda/lib64",
    ] {
        if std::path::Path::new(cand).exists() && !dirs.iter().any(|d| d == cand) {
            dirs.push(cand.into());
        }
    }
    if !dirs.is_empty() {
        cmd.env("LD_LIBRARY_PATH", dirs.join(":"));
    }
}

/// Kill the resident server (if any). Called periodically by the daemon and
/// on failures; VRAM is freed on process exit.
pub fn reap_idle_servers(max_idle_secs: u64) {
    let mut slot = fw_slot().lock().unwrap_or_else(|e| e.into_inner());
    if let Some(srv) = slot.as_mut() {
        if srv.last_use.elapsed().as_secs() >= max_idle_secs {
            let _ = srv.child.kill();
            let _ = srv.child.wait();
            *slot = None;
        }
    }
}

fn fw_kill_locked(slot: &mut Option<FwServer>) {
    if let Some(mut srv) = slot.take() {
        let _ = srv.child.kill();
        let _ = srv.child.wait();
    }
}

fn fw_ensure_locked(
    slot: &mut Option<FwServer>,
    model_dir: &str,
    cuda: bool,
) -> anyhow::Result<()> {
    let alive = match slot.as_mut() {
        Some(srv) if srv.model_dir == model_dir => srv
            .child
            .try_wait()
            .map(|s| s.is_none())
            .unwrap_or(false),
        _ => false,
    };
    if alive {
        return Ok(());
    }
    fw_kill_locked(slot);
    let script = fw_server_script();
    let mut cmd = std::process::Command::new(fw_python_path());
    cmd.arg(&script)
        .arg(model_dir)
        .arg("--device")
        .arg(if cuda { "cuda" } else { "cpu" })
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    fw_lib_env(&mut cmd);
    let mut child = cmd.spawn().map_err(|e| anyhow::anyhow!("fw-server spawn failed: {e}"))?;
    let writer = child.stdin.take().ok_or_else(|| anyhow::anyhow!("fw-server stdin"))?;
    let stdout = child.stdout.take().ok_or_else(|| anyhow::anyhow!("fw-server stdout"))?;
    let mut reader = BufReader::new(stdout);
    // Wait for the ready line (model load ~4 s; generous ceiling).
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let mut line = String::new();
        let res = reader.read_line(&mut line).map(|_| (reader, line));
        let _ = tx.send(res);
    });
    let (reader_back, line) = rx
        .recv_timeout(std::time::Duration::from_secs(120))
        .map_err(|_| anyhow::anyhow!("fw-server ready timeout"))?
        .map_err(|e| anyhow::anyhow!("fw-server ready failed: {e}"))?;
    if !line.contains("\"ready\"") {
        let _ = child.kill();
        let _ = child.wait();
        anyhow::bail!("fw-server bad ready line: {}", line.trim());
    }
    *slot = Some(FwServer {
        child,
        writer,
        reader: Some(reader_back),
        model_dir: model_dir.into(),
        last_use: std::time::Instant::now(),
    });
    Ok(())
}

fn fw_read_line_locked(
    slot: &mut Option<FwServer>,
    secs: u64,
) -> anyhow::Result<String> {
    let mut reader = slot
        .as_mut()
        .and_then(|srv| srv.reader.take())
        .ok_or_else(|| anyhow::anyhow!("fw-server has no reader"))?;
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let mut line = String::new();
        let res = reader.read_line(&mut line).map(|_| (reader, line));
        let _ = tx.send(res);
    });
    match rx.recv_timeout(std::time::Duration::from_secs(secs)) {
        Ok(Ok((reader_back, line))) => {
            if let Some(srv) = slot.as_mut() {
                srv.reader = Some(reader_back);
                srv.last_use = std::time::Instant::now();
            }
            Ok(line)
        }
        // Error or timeout: the reader is stuck inside the helper thread;
        // the server is unusable — kill it so the next call respawns.
        _ => {
            fw_kill_locked(slot);
            anyhow::bail!("fw-server read failed")
        }
    }
}

/// Transcribe via the resident server (blocking; call from spawn_blocking).
/// Falls back to the one-shot path on any server failure.
fn fw_server_transcribe(
    samples: &[f32],
    model_dir: &str,
    language: &str,
    translate: bool,
    vocab: &[String],
    cuda: bool,
) -> anyhow::Result<(String, u64)> {
    let t0 = std::time::Instant::now();
    // Near-silence short-circuits without waking the GPU.
    if !samples.is_empty() {
        let peak = samples.iter().fold(0.0f32, |a, &x| a.max(x.abs()));
        if peak < 0.002 {
            return Ok((String::new(), t0.elapsed().as_millis() as u64));
        }
    }
    // Trim leading/trailing silence (keep 0.2 s margins): inference on
    // silence padding is where phantom phrases ("i'm gonna…", trailing
    // echoes of nothing said) come from. Too-short remainders are noise.
    // Threshold stays conservative (0.004) so quiet speech is never cut.
    let samples = trim_silence(samples, 0.004, 3200);
    if samples.len() < 4800 {
        return Ok((String::new(), t0.elapsed().as_millis() as u64));
    }
    let id = FW_JOB_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    // Unique dir per call: concurrent jobs (live tick vs finalize) share
    // nothing, so a finished call can never delete a sibling's wav.
    let dir = TempAudioDir::create("vaani-fwjob", id)?;
    let wav = dir.join("in.wav");
    write_wav_mono16(&wav, samples)?;
    let mut prompt = String::new();
    if !vocab.is_empty() {
        prompt = vocab.join(", ");
    }
    let job = serde_json::json!({
        "id": id,
        "wav": wav.to_string_lossy(),
        "lang": language,
        "prompt": prompt,
        "task": if translate { "translate" } else { "transcribe" },
    });
    let mut slot = fw_slot().lock().unwrap_or_else(|e| e.into_inner());
    fw_ensure_locked(&mut slot, model_dir, cuda)?;
    let srv = slot.as_mut().ok_or_else(|| anyhow::anyhow!("fw-server missing"))?;
    srv.writer
        .write_all(format!("{}\n", job).as_bytes())
        .map_err(|e| anyhow::anyhow!("fw-server write failed: {e}"))?;
    srv.writer.flush().map_err(|e| anyhow::anyhow!("fw-server flush failed: {e}"))?;
    let mut answer = String::new();
    for _ in 0..32 {
        let line = fw_read_line_locked(&mut slot, 120)?;
        if line.trim().is_empty() {
            continue;
        }
        let v: serde_json::Value =
            serde_json::from_str(line.trim()).map_err(|e| anyhow::anyhow!("fw-server protocol error: {e}"))?;
        if v.get("id").and_then(|x| x.as_u64()) != Some(id) {
            continue; // stale line from a previous job; keep reading
        }
        if let Some(err) = v.get("error").and_then(|e| e.as_str()) {
            anyhow::bail!("fw-server job failed: {err}");
        }
        answer = v.get("text").and_then(|t| t.as_str()).unwrap_or("").to_string();
        break;
    }
    Ok((answer, t0.elapsed().as_millis() as u64))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn parses_silero_segments() {
        let out = "Detected 5 speech segments:\n\
            Speech segment 0: start = 29.00, end = 221.00\n\
            Speech segment 4: start = 816.00, end = 1059.00\n";
        assert_eq!(parse_vad_ends(out), Some(1059.0));
        assert_eq!(parse_vad_ends("Detected 0 speech segments:\n"), None);
        assert_eq!(parse_vad_ends("garbage"), None);
    }

    /// Hardware streaming test: requires CUDA GPU, the cozy CT2 model in
    /// ~/.local/share/vaani/models/cozy, the Cozy venv python, and an
    /// installed fw-server.py. Run explicitly after `./install.sh`:
    /// `cargo test -p vaanid -- --ignored fw_server_streams`.
    /// Proves the resident model answers the second call without a reload.
    #[test]
    #[ignore]
    fn fw_server_streams_without_reload() {
        fn jfk_samples() -> Vec<f32> {
            let path = format!(
                "{}/../../native/worker/upstream/samples/jfk.wav",
                env!("CARGO_MANIFEST_DIR")
            );
            let bytes = std::fs::read(&path).expect("jfk.wav fixture");
            // Minimal RIFF parse: locate the data chunk.
            let mut pos = 12;
            let mut pcm: &[u8] = &[];
            while pos + 8 <= bytes.len() {
                let tag = &bytes[pos..pos + 4];
                let len = u32::from_le_bytes(bytes[pos + 4..pos + 8].try_into().unwrap()) as usize;
                if tag == b"data" {
                    pcm = &bytes[pos + 8..(pos + 8 + len).min(bytes.len())];
                    break;
                }
                pos += 8 + len;
            }
            assert!(!pcm.is_empty(), "no data chunk in jfk.wav");
            pcm.chunks_exact(2)
                .map(|c| i16::from_le_bytes([c[0], c[1]]) as f32 / 32768.0)
                .collect()
        }
        let samples = jfk_samples();
        assert!(samples.len() > 16_000);
        // Two-second slice: warm inference is well under a second, so the
        // threshold below has wide margin against the ~4 s cold reload.
        let short: Vec<f32> = samples[..32_000].to_vec();
        let t0 = std::time::Instant::now();
        let a = transcribe(&short, "cozy", "en", false, 4, true, &[], 90).unwrap();
        let first_ms = t0.elapsed().as_millis();
        assert_eq!(a.backend, "fw-ct2");
        assert!(!a.text.is_empty(), "cozy heard nothing on jfk.wav");
        let t1 = std::time::Instant::now();
        let b = transcribe(&short, "cozy", "en", false, 4, true, &[], 90).unwrap();
        let second_ms = t1.elapsed().as_millis();
        assert_eq!(b.backend, "fw-ct2");
        assert!(
            second_ms < 2000,
            "resident model should answer fast: second={second_ms}ms first={first_ms}ms"
        );
        // Silence padding must not hallucinate: padded input trims to the
        // same speech, so the transcript matches the unpadded one.
        let mut padded = vec![0.0f32; 16_000];
        padded.extend_from_slice(&short);
        padded.extend(vec![0.0f32; 16_000]);
        let c = transcribe(&padded, "cozy", "en", false, 4, true, &[], 90).unwrap();
        assert_eq!(c.backend, "fw-ct2");
        assert_eq!(
            c.text, a.text,
            "padded speech must transcribe identically: {:?} vs {:?}",
            c.text, a.text
        );
        reap_idle_servers(0);
    }
}

fn vad_model_default() -> Option<String> {
    if let Ok(p) = std::env::var("VAANI_VAD_MODEL") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return Some(p);
        }
    }
    let base = std::env::var("XDG_DATA_HOME")
        .unwrap_or_else(|_| format!("{}/.local/share", std::env::var("HOME").unwrap_or_else(|_| ".".into())));
    let cand = format!("{base}/vaani/models/ggml-silero-v5.1.2.bin");
    if std::path::Path::new(&cand).exists() {
        Some(cand)
    } else {
        None
    }
}

fn write_wav_mono16(path: &std::path::Path, samples: &[f32]) -> std::io::Result<()> {
    use std::io::Write;
    let mut f = std::fs::File::create(path)?;
    let n = samples.len() as u32;
    let data_bytes = n * 2;
    f.write_all(b"RIFF")?;
    f.write_all(&(36 + data_bytes).to_le_bytes())?;
    f.write_all(b"WAVEfmt ")?;
    f.write_all(&16u32.to_le_bytes())?;
    f.write_all(&1u16.to_le_bytes())?;
    f.write_all(&1u16.to_le_bytes())?;
    f.write_all(&16_000u32.to_le_bytes())?;
    f.write_all(&(16_000u32 * 2).to_le_bytes())?;
    f.write_all(&2u16.to_le_bytes())?;
    f.write_all(&16u16.to_le_bytes())?;
    f.write_all(b"data")?;
    f.write_all(&data_bytes.to_le_bytes())?;
    for &s in samples {
        let v = (s.clamp(-1.0, 1.0) * 32767.0) as i16;
        f.write_all(&v.to_le_bytes())?;
    }
    Ok(())
}

/// Resolve a configured model to a filesystem path. Prefers an existing
/// ggml file (`{m}.bin`), then an existing model directory (`{m}`, e.g. a
/// fine-tuned CTranslate2 dir for faster-whisper). Falls back to the .bin
/// string so failures stay visible (worker reports cpu-stub, never invents).
pub fn model_path_for(model: &str) -> String {
    let lookup = |dir: &str| {
        let file = format!("{dir}/{model}.bin");
        if std::path::Path::new(&file).is_file() {
            return Some(file);
        }
        let direct = format!("{dir}/{model}");
        if std::path::Path::new(&direct).exists() {
            return Some(direct);
        }
        None
    };
    if let Ok(dir) = std::env::var("VAANI_MODELS_DIR") {
        if !dir.is_empty() {
            if let Some(p) = lookup(&dir) {
                return p;
            }
            return format!("{dir}/{model}.bin");
        }
    }
    let base = std::env::var("XDG_DATA_HOME")
        .unwrap_or_else(|_| format!("{}/.local/share", std::env::var("HOME").unwrap_or_else(|_| ".".into())));
    let dir = format!("{base}/vaani/models");
    lookup(&dir).unwrap_or_else(|| format!("{dir}/{model}.bin"))
}

/// Transcribe complete utterance (stop-gated, max 120 s). Long audio uses
/// bounded segments with overlap + reconciliation (never full-buffer
/// re-inference per frame). `vocab` (names/terms) becomes the recognizer's
/// initial prompt on backends that support it.
pub fn transcribe(
    samples: &[f32],
    model: &str,
    language: &str,
    translate: bool,
    threads: u32,
    cuda: bool,
    vocab: &[String],
    server_idle_secs: u64,
) -> anyhow::Result<Transcript> {
    if samples.is_empty() {
        return Ok(Transcript {
            text: String::new(),
            language: language.into(),
            is_silence: true,
            backend: "cpu-stub".into(),
            inference_ms: 0,
        });
    }
    // Directory models (fine-tuned CT2) go through the resident server.
    // Long audio is split into overlapping 30 s segments (same-model exact
    // overlap dedups cleanly); short audio is one call. One-shot binary is
    // the fallback. Short-window accumulation is preview-only and must never
    // feed the final transcript (windows diverge; merging them makes salad).
    let resolved = model_path_for(model);
    if server_idle_secs > 0 && std::path::Path::new(&resolved).is_dir() {
        let segs = segment(samples);
        let mut parts: Vec<String> = Vec::new();
        let mut ms_total = 0u64;
        let mut failed = false;
        for (s, e) in &segs {
            match fw_server_transcribe(&samples[*s..*e], &resolved, language, translate, vocab, cuda) {
                Ok((text, ms)) => {
                    ms_total += ms;
                    parts.push(text);
                }
                Err(e) => {
                    eprintln!("vaani: fw-server failed ({e:#}), one-shot fallback");
                    failed = true;
                    break;
                }
            }
        }
        if !failed {
            let refs: Vec<&str> = parts.iter().map(|s| s.as_str()).collect();
            let t = vaani_core::transcript::polish(&vaani_core::reconcile::reconcile(&refs));
            let empty = t.is_empty();
            return Ok(Transcript {
                text: t,
                language: language.into(),
                is_silence: empty,
                backend: "fw-ct2".into(),
                inference_ms: ms_total,
            });
        }
    }
    // Short path: single worker call.
    if samples.len() <= vaani_core::segment::SEGMENT_SAMPLES {
        return run_once(samples, model, language, translate, threads, cuda, vocab);
    }
    // Long path: bounded segments, reconcile.
    let mut parts: Vec<String> = Vec::new();
    let mut lang = language.to_string();
    let mut silence_all = true;
    let mut backend = "cpu-stub".to_string();
    let mut ms_total = 0u64;
    for (s, e) in segment(samples) {
        let t = run_once(&samples[s..e], model, language, translate, threads, cuda, vocab)?;
        if !t.is_silence {
            silence_all = false;
        }
        lang = t.language.clone();
        backend = t.backend.clone();
        ms_total += t.inference_ms;
        parts.push(t.text);
    }
    let refs: Vec<&str> = parts.iter().map(|s| s.as_str()).collect();
    Ok(Transcript {
        text: reconcile(&refs),
        language: lang,
        is_silence: silence_all,
        backend,
        inference_ms: ms_total,
    })
}

fn run_once(
    samples: &[f32],
    model: &str,
    language: &str,
    translate: bool,
    threads: u32,
    cuda: bool,
    vocab: &[String],
) -> anyhow::Result<Transcript> {
    let t0 = std::time::Instant::now();
    let mut command = std::process::Command::new(worker_bin());
    if translate { command.arg("--translate"); }
    if !vocab.is_empty() {
        // Names/terms bias (whisper initial prompt / fw initial_prompt).
        // Configured vocabulary only — transcripts never travel via argv.
        command.arg("--prompt").arg(vocab.join(", "));
    }
    let mut child = command
        .arg("--model")
        .arg(model_path_for(model))
        .arg("--language")
        .arg(language)
        .arg("--threads")
        .arg(threads.to_string())
        .env("VAANI_CUDA", if cuda { "1" } else { "0" })
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| anyhow::anyhow!("worker spawn failed: {e}"))?;

    // Write PCM (f32 LE) then close stdin = EOF frame boundary.
    let bytes: Vec<u8> = samples.iter().flat_map(|x| x.to_le_bytes()).collect();
    // Bound write: worker takes max 120 s; write in one go (bounded ~7.7 MiB).
    if let Some(mut stdin) = child.stdin.take() {
        // A worker may stop consuming stdin. Keep the writer independent,
        // enforce a hard child deadline, then kill it to release the pipe.
        std::thread::scope(|s| {
            s.spawn(move || { let _ = stdin.write_all(&bytes); });
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(125);
            loop {
                match child.try_wait() {
                    Ok(Some(_)) => break,
                    Ok(None) if std::time::Instant::now() >= deadline => {
                        let _ = child.kill();
                        let _ = child.wait();
                        break;
                    }
                    Ok(None) => std::thread::sleep(std::time::Duration::from_millis(25)),
                    Err(_) => break,
                }
            }
        });
    }
    let out = child.wait_with_output()?;
    if !out.status.success() {
        anyhow::bail!("worker exited with {}", out.status);
    }
    let line = String::from_utf8_lossy(&out.stdout);
    let v: serde_json::Value = serde_json::from_str(line.trim())
        .map_err(|e| anyhow::anyhow!("worker protocol error: {e}"))?;
    if let Some(err) = v.get("error").and_then(|e| e.as_str()) {
        anyhow::bail!("worker error: {err}");
    }
    let mut text = v.get("text").and_then(|t| t.as_str()).unwrap_or("").to_string();
    // Bound transcript size.
    if text.len() > vaani_core::MAX_TRANSCRIPT_CHARS {
        let mut boundary = vaani_core::MAX_TRANSCRIPT_CHARS;
        while !text.is_char_boundary(boundary) { boundary -= 1; }
        text.truncate(boundary);
    }
    // Raw mode: only outer whitespace normalisation.
    let trimmed = text.trim().to_string();
    let empty = trimmed.is_empty();
    Ok(Transcript {
        text: trimmed,
        language: v
            .get("language")
            .and_then(|l| l.as_str())
            .unwrap_or(language)
            .to_string(),
        is_silence: v.get("is_silence").and_then(|b| b.as_bool()).unwrap_or(false)
            || empty,
        backend: v
            .get("backend")
            .and_then(|b| b.as_str())
            .unwrap_or("unknown")
            .to_string(),
        inference_ms: v.get("ms").and_then(|m| m.as_u64()).unwrap_or(
            t0.elapsed().as_millis() as u64,
        ),
    })
}
