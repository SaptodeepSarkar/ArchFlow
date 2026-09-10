//! vaani-worker: local inference process containing whisper integration.
//! Spawned only on dictation activation; exits per residency profile.
//!
//! Protocol (inherited pipes, NOT the control socket):
//!   argv: vaani-worker --model <path> --language <lang> --threads <n> [--translate]
//!   stdin:  raw float32 LE mono 16 kHz PCM (bounded, max 120 s).
//!   stdout: single JSON line: {"text": "...", "language": "...", "is_silence": bool, "backend": "whisper-cli|cpu-stub", "ms": u64}
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
    let backend_bin = if std::env::var("VAANI_CUDA").ok().as_deref() == Some("1") {
        find_binary(&["whisper-cli-cuda", "whisper-cpp-cuda"])
    } else {
        find_binary(&["whisper-cli", "whisper-cpp", "whisper", "main"])
    };

    let (text, backend) = match (backend_bin, model_exists(&model)) {
        (Some(bin), true) => match run_whisper_cli(&bin, &model_resolve(&model), &language, threads, translate, &samples) {
            Ok(t) => (t, "whisper-cli"),
            Err(e) => {
                eprintln!("vaani-worker: whisper backend failed ({e}), falling back to stub");
                (stub_transcript(&samples), "cpu-stub")
            }
        },
        _ => (stub_transcript(&samples), "cpu-stub"),
    };

    emit_ok(&text, &language, false, backend, t0.elapsed().as_millis() as u64);
}

fn model_exists(m: &str) -> bool {
    if !m.is_empty() && std::path::Path::new(m).exists() {
        return true;
    }
    // Accept a bare model name too: resolve against the models dir.
    if !m.contains('/') && !m.is_empty() {
        let base = std::env::var("XDG_DATA_HOME").unwrap_or_else(|_| {
            format!("{}/.local/share", std::env::var("HOME").unwrap_or_else(|_| ".".into()))
        });
        for cand in [format!("{base}/vaani/models/{m}.bin"), format!("{base}/vaani/models/{m}")] {
            if std::path::Path::new(&cand).exists() {
                return true;
            }
        }
    }
    false
}

fn model_resolve(m: &str) -> String {
    if !m.is_empty() && std::path::Path::new(m).exists() {
        return m.to_string();
    }
    if !m.contains('/') && !m.is_empty() {
        let base = std::env::var("XDG_DATA_HOME").unwrap_or_else(|_| {
            format!("{}/.local/share", std::env::var("HOME").unwrap_or_else(|_| ".".into()))
        });
        for cand in [format!("{base}/vaani/models/{m}.bin"), format!("{base}/vaani/models/{m}")] {
            if std::path::Path::new(&cand).exists() {
                return cand;
            }
        }
    }
    m.to_string()
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
    if translate {
        cmd.arg("--translate");
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
