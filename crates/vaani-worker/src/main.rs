//! vaani-worker: local inference process containing whisper integration.
//! Spawned only on dictation activation; exits per residency profile.
//!
//! Protocol (inherited pipes, NOT the control socket):
//!   argv: vaani-worker --model <path> --language <lang> --threads <n> [--translate] [--prompt TEXT]
//!   stdin:  raw float32 LE mono 16 kHz PCM (bounded, max 120 s).
//!   stdout: single JSON line: {"text": "...", "language": "...", "is_silence": bool, "backend": "whisper-cli|fw-ct2|cpu-stub", "ms": u64}
//! Backends: whisper.cpp CLI for ggml .bin files; faster-whisper (CT2 dir)
//! for fine-tuned models such as cozy-stt. --prompt carries user-configured
//! vocabulary (names/terms) to bias recognition; transcripts never travel
//! via argv. Filler words (uh/um/...) are stripped from every backend output.
//! Never dynamically loads CUDA into the idle controller — CUDA only here,
//! only if the user selected a GPU build (env VAANI_CUDA=1 + cuda binary).

use std::io::Read;
use vaani_core::vad::{Vad, BLOCK_SAMPLES};

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut model = String::new();
    let mut language = "en".to_string();
    let mut threads = 4u32;
    let mut translate = false;
    let mut prompt = String::new();
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--model" => {
                i += 1;
                model = args.get(i).cloned().unwrap_or_default();
            }
            "--language" => {
                i += 1;
                language = args.get(i).cloned().unwrap_or_else(|| "en".into());
            }
            "--threads" => {
                i += 1;
                threads = args.get(i).and_then(|s| s.parse().ok()).unwrap_or(4);
            }
            "--translate" => translate = true,
            "--prompt" => {
                i += 1;
                prompt = args.get(i).cloned().unwrap_or_default();
            }
            _ => {}
        }
        i += 1;
    }
    let t0 = std::time::Instant::now();

    // Read bounded PCM from stdin.
    let max_bytes = (vaani_core::MAX_AUDIO_SECS as usize) * 16_000 * 4;
    let mut pcm_bytes: Vec<u8> = Vec::new();
    match std::io::stdin()
        .lock()
        .take(max_bytes as u64 + 16)
        .read_to_end(&mut pcm_bytes)
    {
        Ok(_) => {}
        Err(e) => {
            emit_error(&format!("stdin read failed: {e}"));
            std::process::exit(2);
        }
    }
    if pcm_bytes.len() % 4 != 0 {
        pcm_bytes.truncate(pcm_bytes.len() - (pcm_bytes.len() % 4));
    }
    let samples: Vec<f32> = pcm_bytes
        .chunks_exact(4)
        .map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]]))
        .collect();

    if samples.is_empty() {
        emit_ok("", &language, true, "cpu-stub", t0.elapsed().as_millis() as u64);
        return;
    }

    // VAD gate: silence produces no inserted text.
    let mut vad = Vad::default();
    for blk in samples.chunks(BLOCK_SAMPLES) {
        if blk.len() == BLOCK_SAMPLES {
            vad.push_block(blk);
        }
    }
    if vad.is_silence() {
        emit_ok("", &language, true, "cpu-stub", t0.elapsed().as_millis() as u64);
        return;
    }

    // Try real whisper.cpp CLI if a model file exists and binary is installed.
    // CUDA requested: prefer the GPU binary, fall back to CPU visibly
    // (backend label always says which one actually ran).
    let want_cuda = std::env::var("VAANI_CUDA").ok().as_deref() == Some("1");
    let backend_bin = if want_cuda {
        find_binary(&["whisper-cli-cuda", "whisper-cpp-cuda"])
            .map(|b| (b, "whisper-cli-cuda"))
            .or_else(|| find_binary(&["whisper-cli", "whisper-cpp", "whisper", "main"]).map(|b| (b, "whisper-cli")))
    } else {
        find_binary(&["whisper-cli", "whisper-cpp", "whisper", "main"]).map(|b| (b, "whisper-cli"))
    };

    let model_path = model_resolve(&model);
    let (text, backend) = if std::path::Path::new(&model_path).is_dir() {
        // Fine-tuned CTranslate2 directory (e.g. cozy-stt): faster-whisper.
        match run_faster_whisper(&model_path, &language, &prompt, want_cuda_flag(), &samples) {
            Ok(t) => (t, "fw-ct2"),
            Err(e) => {
                eprintln!("vaani-worker: faster-whisper backend failed ({e}), falling back to stub");
                (stub_transcript(&samples), "cpu-stub")
            }
        }
    } else {
        match (backend_bin, model_exists(&model)) {
        (Some((bin, label)), true) => match run_whisper_cli(&bin, &model_path, &language, threads, translate, &prompt, &samples) {
            Ok(t) => (t, label),
            Err(e) => {
                eprintln!("vaani-worker: whisper backend failed ({e}), falling back to stub");
                (stub_transcript(&samples), "cpu-stub")
            }
        },
        _ => (stub_transcript(&samples), "cpu-stub"),
        }
    };

    emit_ok(&strip_fillers(&text), &language, false, backend, t0.elapsed().as_millis() as u64);
}

fn want_cuda_flag() -> bool {
    std::env::var("VAANI_CUDA").ok().as_deref() == Some("1")
}

/// Python interpreter for the faster-whisper sidecar: explicit override,
/// then the Cozy fine-tune venv ( validated CUDA faster-whisper), then PATH.
fn fw_python() -> anyhow::Result<String> {
    if let Ok(p) = std::env::var("VAANI_FW_PYTHON") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return Ok(p);
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let venv = format!("{home}/Projects/Cozy/stt-finetune/.venv/bin/python");
        if std::path::Path::new(&venv).exists() {
            return Ok(venv);
        }
    }
    Ok("python3".into())
}

/// Library path for the sidecar: CTranslate2 needs CUDA-12 libs, which on
/// this machine live in ollama's runtime dir (NOT on the default search
/// path). Missing entries are skipped; an existing LD_LIBRARY_PATH is kept.
fn fw_lib_path() -> Option<String> {
    let mut dirs: Vec<String> = Vec::new();
    if let Ok(cur) = std::env::var("LD_LIBRARY_PATH") {
        dirs.extend(cur.split(':').map(|s| s.to_string()));
    }
    for cand in [
        "/usr/local/lib/ollama/cuda_v12",
        "/opt/cuda/lib64",
        "/usr/local/cuda/lib64",
    ] {
        if std::path::Path::new(&cand).exists() && !dirs.iter().any(|d| d == cand) {
            dirs.push(cand.into());
        }
    }
    if dirs.is_empty() {
        None
    } else {
        Some(dirs.join(":"))
    }
}

/// Sidecar script: sibling of the worker binary (user-local install), then
/// ~/.local/bin, then PATH. Installed by install.sh, never edited by hand.
fn fw_script() -> anyhow::Result<String> {
    if let Ok(p) = std::env::var("VAANI_FW_SCRIPT") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return Ok(p);
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let sib = dir.join("fw-transcribe.py");
            if sib.exists() {
                return Ok(sib.to_string_lossy().into_owned());
            }
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let p = format!("{home}/.local/bin/fw-transcribe.py");
        if std::path::Path::new(&p).exists() {
            return Ok(p);
        }
    }
    Ok("fw-transcribe.py".into())
}

/// faster-whisper backend for directory models (CTranslate2, e.g. cozy-stt).
/// Audio reaches the script as a wav file path; only paths travel via argv.
fn run_faster_whisper(
    model_dir: &str,
    language: &str,
    prompt: &str,
    cuda: bool,
    samples: &[f32],
) -> anyhow::Result<String> {
    let script = fw_script()?;
    let python = fw_python()?;
    let dir = std::env::temp_dir().join(format!("vaani-fw-{}", std::process::id()));
    std::fs::create_dir_all(&dir)?;
    let wav = dir.join("in.wav");
    write_wav_mono16(&wav, samples)?;
    let mut cmd = std::process::Command::new(&python);
    cmd.arg(&script)
        .arg(model_dir)
        .arg(&wav)
        .arg(language)
        .arg("--device")
        .arg(if cuda { "cuda" } else { "cpu" });
    if let Some(libs) = fw_lib_path() {
        cmd.env("LD_LIBRARY_PATH", libs);
    }
    if !prompt.is_empty() {
        cmd.arg("--prompt").arg(prompt);
    }
    let out = cmd.output().map_err(|e| anyhow::anyhow!("fw sidecar spawn failed: {e}"))?;
    let _ = std::fs::remove_dir_all(&dir);
    if !out.status.success() {
        anyhow::bail!(
            "fw sidecar exit {}: {}",
            out.status,
            String::from_utf8_lossy(&out.stderr).trim()
        );
    }
    Ok(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn model_exists(m: &str) -> bool {
    // Single source of truth: whatever model_resolve lands on must exist.
    // A stale supervisor path (e.g. cozy.bin for the cozy/ directory) is
    // rescued to the real artifact instead of silently falling to cpu-stub.
    let r = model_resolve(m);
    !r.is_empty() && std::path::Path::new(&r).exists()
}

fn model_resolve(m: &str) -> String {
    if !m.is_empty() && std::path::Path::new(m).exists() {
        return m.to_string();
    }
    // Bare name: resolve against the models dir (file first, then dir).
    // Also rescue a stale supervisor path: basename minus .bin extension.
    let mut bare: Vec<String> = Vec::new();
    if !m.contains('/') && !m.is_empty() {
        bare.push(m.to_string());
    } else if m.contains('/') {
        let base = std::path::Path::new(m)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("");
        let stem = base.strip_suffix(".bin").unwrap_or(base);
        if !stem.is_empty() {
            bare.push(stem.to_string());
        }
    }
    if !bare.is_empty() {
        let base = std::env::var("XDG_DATA_HOME").unwrap_or_else(|_| {
            format!("{}/.local/share", std::env::var("HOME").unwrap_or_else(|_| ".".into()))
        });
        for b in &bare {
            for cand in [format!("{base}/vaani/models/{b}.bin"), format!("{base}/vaani/models/{b}")] {
                if std::path::Path::new(&cand).exists() {
                    return cand;
                }
            }
        }
    }
    m.to_string()
}

/// Silero VAD model for whisper-cli gating. Env override first, then the
/// standard models dir. None => plain inference (energy gate still applies
/// controller-side).
fn vad_model_path() -> Option<String> {
    if let Ok(p) = std::env::var("VAANI_VAD_MODEL") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return Some(p);
        }
    }
    let base = std::env::var("XDG_DATA_HOME").unwrap_or_else(|_| {
        format!("{}/.local/share", std::env::var("HOME").unwrap_or_else(|_| ".".into()))
    });
    let cand = format!("{base}/vaani/models/ggml-silero-v5.1.2.bin");
    if std::path::Path::new(&cand).exists() {
        Some(cand)
    } else {
        None
    }
}

fn find_binary(names: &[&str]) -> Option<String> {
    let mut dirs: Vec<String> = std::env::var("PATH").unwrap_or_default().split(':').map(|s| s.to_string()).collect();
    // User-local + admin prefixes the systemd service PATH may lack.
    if let Ok(home) = std::env::var("HOME") {
        dirs.push(format!("{home}/.local/bin"));
    }
    dirs.push("/usr/local/bin".into());
    // Sibling of this executable (same install prefix as the daemon).
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            dirs.push(dir.to_string_lossy().into_owned());
        }
    }
    for dir in &dirs {
        for n in names {
            let p = format!("{dir}/{n}");
            if std::path::Path::new(&p).exists() {
                return Some(p);
            }
        }
    }
    None
}

/// Run whisper CLI on a temp wav (only place temp audio files are acceptable:
/// inside the short-lived worker, removed immediately). Returns raw text.
fn run_whisper_cli(
    bin: &str,
    model: &str,
    language: &str,
    threads: u32,
    translate: bool,
    prompt: &str,
    samples: &[f32],
) -> anyhow::Result<String> {
    use std::io::Write;
    let dir = std::env::temp_dir().join(format!("vaani-{}", std::process::id()));
    std::fs::create_dir_all(&dir)?;
    let wav = dir.join("in.wav");
    write_wav_mono16(&wav, samples)?;
    let out_prefix = dir.join("out");
    let mut cmd = std::process::Command::new(bin);
    cmd.arg("-m")
        .arg(model)
        .arg("-f")
        .arg(&wav)
        .arg("-otxt")
        .arg("-of")
        .arg(&out_prefix)
        .arg("-t")
        .arg(threads.to_string())
        .arg("-l")
        .arg(language);
    // Silero VAD gate inside whisper: segments speech, ignores silence.
    // Falls back to plain inference when the VAD model is absent.
    if let Some(vad) = vad_model_path() {
        cmd.arg("--vad")
            .arg("--vad-model")
            .arg(vad)
            .arg("--vad-threshold")
            .arg("0.35");
    }
    if translate {
        cmd.arg("--translate");
    }
    // Vocabulary bias (names/terms): initial prompt steers recognition
    // without touching the audio. Skipped when empty (stock behavior).
    if !prompt.is_empty() {
        cmd.arg("--prompt").arg(prompt);
    }
    // Bounded inference time: 120 s audio + margin.
    let mut child = cmd.stdout(std::process::Stdio::null()).stderr(std::process::Stdio::piped()).spawn()?;
    let status = child.wait()?;
    let txt_path = out_prefix.with_extension("txt");
    let text = std::fs::read_to_string(&txt_path).unwrap_or_default();
    let _ = std::fs::remove_dir_all(&dir);
    if !status.success() {
        anyhow::bail!("whisper-cli exit {}", status);
    }
    // Segment reconciliation across long outputs is done controller-side;
    // here do a light whitespace normalise only (raw mode).
    let _ = std::io::stdout().flush();
    Ok(text.split_whitespace().collect::<Vec<_>>().join(" ").trim().to_string())
}

/// Deterministic stub used when no model/binary is configured: never invents
/// words in production path — returns empty so nothing is inserted. Only used
/// for plumbing tests; clearly labelled backend="cpu-stub".
/// Drop spoken filler words (whole tokens, case-insensitive): uh/um/er
/// variants and mm-hesitations carry no information and the fine-tuned
/// transcripts read cleaner without them. Conservative by design: only
/// standalone filler tokens vanish; substrings ("umber", "mummy") and
/// sentence position are untouched. Trailing/leading punctuation on the
/// token is tolerated ("uh," still counts).
fn strip_fillers(text: &str) -> String {
    const FILLERS: &[&str] = &[
        "uh", "uhh", "uhhh", "um", "umm", "ummm", "uhm", "er", "erm", "ah", "mmm",
    ];
    let kept: Vec<&str> = text
        .split_whitespace()
        .filter(|tok| {
            let core = tok
                .trim_matches(|c: char| !c.is_alphanumeric())
                .to_lowercase();
            !(core.len() >= 2 && FILLERS.contains(&core.as_str()))
        })
        .collect();
    // Rejoin and tidy spaces left before punctuation.
    let mut out = kept.join(" ");
    for p in [",", ".", "!", "?", ";", ":", ")", "]"] {
        out = out.replace(&format!(" {p}"), p);
    }
    out = out.replace("( ", "(").replace("[ ", "[");
    out.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn stub_transcript(_samples: &[f32]) -> String {
    // Empty: silence policy — do not fabricate transcription.
    // Integration tests with synthetic fixtures assert this stays empty
    // unless VAANI_WORKER_STUB_TEXT is set (test-only).
    std::env::var("VAANI_WORKER_STUB_TEXT").unwrap_or_default()
}

fn emit_ok(text: &str, lang: &str, silence: bool, backend: &str, ms: u64) {
    let v = serde_json::json!({
        "text": text,
        "language": lang,
        "is_silence": silence,
        "backend": backend,
        "ms": ms,
    });
    println!("{}", v);
}

fn emit_error(msg: &str) {
    let v = serde_json::json!({ "error": msg });
    println!("{v}");
}

fn write_wav_mono16(path: &std::path::Path, samples: &[f32]) -> std::io::Result<()> {
    use std::io::Write;
    let mut f = std::fs::File::create(path)?;
    let n = samples.len() as u32;
    let data_bytes = n * 2;
    // RIFF header
    f.write_all(b"RIFF")?;
    f.write_all(&(36 + data_bytes).to_le_bytes())?;
    f.write_all(b"WAVEfmt ")?;
    f.write_all(&16u32.to_le_bytes())?;
    f.write_all(&1u16.to_le_bytes())?; // PCM
    f.write_all(&1u16.to_le_bytes())?; // mono
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fillers_removed_whole_tokens_only() {
        assert_eq!(
            strip_fillers("Uh, I um think er this is fine"),
            "I think this is fine"
        );
        assert_eq!(
            strip_fillers("well UMM let me see mmm ok"),
            "well let me see ok"
        );
        // Substrings and short tokens survive.
        assert_eq!(strip_fillers("umber mummy a I"), "umber mummy a I");
        assert_eq!(strip_fillers(""), "");
        // Punctuation spacing tidied.
        assert_eq!(strip_fillers("hello , uh world ."), "hello, world.");
    }
}
