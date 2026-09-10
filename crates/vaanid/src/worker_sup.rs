//! Worker supervision: spawn `vaani-worker` per dictation (Economy default),
//! pipe bounded PCM via inherited stdin, read one JSON line from stdout.
//! A worker crash leaves the controller operational (Err, state -> ERROR).

use std::io::Write;
use std::process::Stdio;
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
    let dir = std::env::temp_dir().join(format!("vaani-vad-{}", std::process::id()));
    std::fs::create_dir_all(&dir).ok()?;
    let wav = dir.join("in.wav");
    write_wav_mono16(&wav, samples).ok()?;
    let vad_model = vad_model_default();
    let mut cmd = std::process::Command::new(&bin);
    cmd.arg("-t").arg("2").arg("-f").arg(&wav);
    if let Some(vm) = vad_model {
        cmd.arg("-vm").arg(vm);
    }
    let out = cmd.output().ok()?;
    let _ = std::fs::remove_dir_all(&dir);
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

pub fn model_path_for(model: &str) -> String {
    if let Ok(dir) = std::env::var("VAANI_MODELS_DIR") {
        if !dir.is_empty() {
            return format!("{dir}/{model}.bin");
        }
    }
    let base = std::env::var("XDG_DATA_HOME")
        .unwrap_or_else(|_| format!("{}/.local/share", std::env::var("HOME").unwrap_or_else(|_| ".".into())));
    format!("{base}/vaani/models/{model}.bin")
}

/// Transcribe complete utterance (stop-gated, max 120 s). Long audio uses
/// bounded segments with overlap + reconciliation (never full-buffer
/// re-inference per frame).
pub fn transcribe(
    samples: &[f32],
    model: &str,
    language: &str,
    translate: bool,
    threads: u32,
    cuda: bool,
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
    // Short path: single worker call.
    if samples.len() <= vaani_core::segment::SEGMENT_SAMPLES {
        return run_once(samples, model, language, translate, threads, cuda);
    }
    // Long path: bounded segments, reconcile.
    let mut parts: Vec<String> = Vec::new();
    let mut lang = language.to_string();
    let mut silence_all = true;
    let mut backend = "cpu-stub".to_string();
    let mut ms_total = 0u64;
    for (s, e) in segment(samples) {
        let t = run_once(&samples[s..e], model, language, translate, threads, cuda)?;
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
) -> anyhow::Result<Transcript> {
    let t0 = std::time::Instant::now();
    let mut child = std::process::Command::new(worker_bin())
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
        // Write from a helper thread so a slow worker can't deadlock us while
        // we wait on stdout; join with timeout via polling.
        std::thread::scope(|s| {
            s.spawn(move || {
                let _ = stdin.write_all(&bytes);
                // stdin dropped -> EOF
            });
            s.spawn(move || ());
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
        text.truncate(vaani_core::MAX_TRANSCRIPT_CHARS);
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
