//! Cleanup-LLM supervision: resident `llm-server.py` sidecar for stream mode.
//!
//! The frozen Qwen3-0.6B base + LoRA adapter loads once (~8 s cold) and then
//! answers cleanup jobs in ~1-2 s. Per-call reloads would make every finish
//! wait on a cold load. The server is reaped after configured idle seconds,
//! so VRAM is only held while dictating. Must be driven from blocking
//! threads (spawn_blocking): all child IO here is synchronous.
//!
//! One-shot `vaani_inject.py` remains the fallback when the server cannot
//! start or a read fails.

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Stdio};
use vaani_core::config::Config;

struct LlmServer {
    child: Child,
    writer: ChildStdin,
    reader: Option<BufReader<ChildStdout>>,
    model_dir: String,
    adapter_dir: String,
    last_use: std::time::Instant,
}

static LLM_SERVER: std::sync::OnceLock<std::sync::Mutex<Option<LlmServer>>> =
    std::sync::OnceLock::new();
static LLM_JOB_ID: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(1);

fn llm_slot() -> &'static std::sync::Mutex<Option<LlmServer>> {
    LLM_SERVER.get_or_init(|| std::sync::Mutex::new(None))
}

fn llm_server_script() -> String {
    if let Ok(p) = std::env::var("VAANI_LLM_SCRIPT_SERVER") {
        if !p.is_empty() && std::path::Path::new(&p).exists() {
            return p;
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let sib = dir.join("llm-server.py");
            if sib.exists() {
                return sib.to_string_lossy().into_owned();
            }
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        let p = format!("{home}/.local/bin/llm-server.py");
        if std::path::Path::new(&p).exists() {
            return p;
        }
    }
    "llm-server.py".into()
}

/// Kill the resident server (if any). Called by the idle sweeper and on
/// failures; VRAM is freed on process exit.
pub fn reap_idle_llm(max_idle_secs: u64) {
    let mut slot = llm_slot().lock().unwrap_or_else(|e| e.into_inner());
    if let Some(srv) = slot.as_mut() {
        if srv.last_use.elapsed().as_secs() >= max_idle_secs {
            let _ = srv.child.kill();
            let _ = srv.child.wait();
            *slot = None;
        }
    }
}

fn llm_kill_locked(slot: &mut Option<LlmServer>) {
    if let Some(mut srv) = slot.take() {
        let _ = srv.child.kill();
        let _ = srv.child.wait();
    }
}

fn llm_paths(cfg: &Config) -> (String, String) {
    let model_dir = if cfg.cleanup.model_path.is_empty() {
        let data_dir = std::env::var_os("XDG_DATA_HOME")
            .map(std::path::PathBuf::from)
            .or_else(|| {
                std::env::var_os("HOME").map(|h| std::path::PathBuf::from(h).join(".local/share"))
            })
            .map(|p| p.join("vaani").join("cleanup").join("base-model"));
        data_dir
            .filter(|p| p.exists())
            .or_else(|| {
                std::env::current_exe()
                    .ok()
                    .and_then(|p| {
                        p.parent().map(|d| {
                            d.join("..")
                                .join("output")
                                .join("base-model")
                                .to_string_lossy()
                                .into_owned()
                        })
                    })
                    .map(std::path::PathBuf::from)
                    .filter(|p| p.exists())
            })
            .unwrap_or_default()
            .to_string_lossy()
            .into_owned()
    } else {
        cfg.cleanup.model_path.clone()
    };
    let adapter_dir = if !cfg.cleanup.adapter_path.is_empty() {
        cfg.cleanup.adapter_path.clone()
    } else if let Ok(data) = std::env::var("XDG_DATA_HOME") {
        let p = std::path::Path::new(&data).join("vaani/cleanup/llm-v1");
        if p.exists() {
            p.to_string_lossy().into_owned()
        } else {
            String::new()
        }
    } else if let Ok(home) = std::env::var("HOME") {
        let p = std::path::Path::new(&home).join(".local/share/vaani/cleanup/llm-v1");
        if p.exists() {
            p.to_string_lossy().into_owned()
        } else {
            String::new()
        }
    } else if !cfg.cleanup.model_path.is_empty() {
        format!("{}/../dpo-sft", cfg.cleanup.model_path)
    } else {
        String::new()
    };
    (model_dir, adapter_dir)
}

fn llm_ensure_locked(
    slot: &mut Option<LlmServer>,
    model_dir: &str,
    adapter_dir: &str,
    threshold: usize,
) -> anyhow::Result<()> {
    let alive = match slot.as_mut() {
        Some(srv) if srv.model_dir == model_dir && srv.adapter_dir == adapter_dir => {
            srv.child.try_wait().map(|s| s.is_none()).unwrap_or(false)
        }
        _ => false,
    };
    if alive {
        return Ok(());
    }
    llm_kill_locked(slot);
    let script = llm_server_script();
    let mut child = std::process::Command::new("python3")
        .arg(&script)
        .arg(model_dir)
        .arg(adapter_dir)
        .arg("--threshold")
        .arg(threshold.to_string())
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| anyhow::anyhow!("llm-server spawn failed: {e}"))?;
    let writer = child
        .stdin
        .take()
        .ok_or_else(|| anyhow::anyhow!("llm-server stdin"))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| anyhow::anyhow!("llm-server stdout"))?;
    let mut reader = BufReader::new(stdout);
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let mut line = String::new();
        let res = reader.read_line(&mut line).map(|_| (reader, line));
        let _ = tx.send(res);
    });
    let (reader_back, line) = rx
        .recv_timeout(std::time::Duration::from_secs(120))
        .map_err(|_| anyhow::anyhow!("llm-server ready timeout"))?
        .map_err(|e| anyhow::anyhow!("llm-server ready failed: {e}"))?;
    if !line.contains("\"ready\"") {
        let _ = child.kill();
        let _ = child.wait();
        anyhow::bail!("llm-server bad ready line: {}", line.trim());
    }
    *slot = Some(LlmServer {
        child,
        writer,
        reader: Some(reader_back),
        model_dir: model_dir.into(),
        adapter_dir: adapter_dir.into(),
        last_use: std::time::Instant::now(),
    });
    Ok(())
}

fn llm_read_locked(slot: &mut Option<LlmServer>, secs: u64) -> anyhow::Result<String> {
    let mut reader = slot
        .as_mut()
        .and_then(|srv| srv.reader.take())
        .ok_or_else(|| anyhow::anyhow!("llm-server has no reader"))?;
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
        _ => {
            llm_kill_locked(slot);
            anyhow::bail!("llm-server read failed")
        }
    }
}

/// Cleanup via the resident server (blocking; call from spawn_blocking).
fn llm_server_cleanup(text: &str, cfg: &Config) -> anyhow::Result<String> {
    let (model_dir, adapter_dir) = llm_paths(cfg);
    if model_dir.is_empty() || !std::path::Path::new(&model_dir).exists() {
        anyhow::bail!("no cleanup model dir");
    }
    let id = LLM_JOB_ID.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let mut slot = llm_slot().lock().unwrap_or_else(|e| e.into_inner());
    llm_ensure_locked(
        &mut slot,
        &model_dir,
        &adapter_dir,
        cfg.cleanup.word_threshold,
    )?;
    let job = serde_json::json!({"id": id, "text": text}).to_string() + "\n";
    if let Some(srv) = slot.as_mut() {
        srv.writer.write_all(job.as_bytes())?;
        srv.writer.flush()?;
    }
    let line = llm_read_locked(&mut slot, 120)?;
    let v: serde_json::Value =
        serde_json::from_str(&line).map_err(|e| anyhow::anyhow!("llm-server bad reply: {e}"))?;
    if v.get("id").and_then(|i| i.as_u64()) != Some(id) {
        llm_kill_locked(&mut slot);
        anyhow::bail!("llm-server id mismatch");
    }
    if let Some(err) = v.get("error").and_then(|e| e.as_str()) {
        anyhow::bail!("llm-server error: {err}");
    }
    Ok(v.get("text")
        .and_then(|t| t.as_str())
        .unwrap_or(text)
        .to_string())
}

/// One-shot fallback: single `vaani_inject.py` call (cold load each time).
fn llm_oneshot(text: &str, cfg: &Config) -> String {
    let python_path = if cfg.cleanup.python_path.is_empty() {
        std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("vaani_inject.py")))
    } else {
        Some(std::path::PathBuf::from(&cfg.cleanup.python_path))
    };
    let (model_dir, adapter_dir) = llm_paths(cfg);
    let threshold = cfg.cleanup.word_threshold;
    let text_llm = text.to_string();
    let python = match python_path {
        Some(p) if p.exists() => p,
        _ => return text_llm,
    };
    let mut child = match std::process::Command::new("python3")
        .arg(&python)
        .arg("--adapter")
        .arg(&adapter_dir)
        .arg("--threshold")
        .arg(threshold.to_string())
        .arg("--model-dir")
        .arg(&model_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
    {
        Ok(c) => c,
        Err(_) => return text_llm,
    };
    {
        let mut stdin = match child.stdin.take() {
            Some(s) => s,
            None => return text_llm,
        };
        if stdin.write_all(text_llm.as_bytes()).is_err() {
            return text_llm;
        }
    }
    match child.wait_with_output() {
        Ok(out) => {
            let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if !s.is_empty() {
                s
            } else {
                text_llm
            }
        }
        Err(_) => text_llm,
    }
}

/// Pre-load the cleanup LLM model when Super+H is pressed.
/// This starts the resident server in the background (~8 s cold)
/// so it is ready when the user finishes speaking and calls
/// `llm_cleanup`. The server is reaped after `server_idle_secs`.
/// Must be called from `spawn_blocking` to avoid blocking the async runtime.
pub fn prefill(cfg: &Config) -> anyhow::Result<()> {
    let (model_dir, adapter_dir) = llm_paths(cfg);
    if model_dir.is_empty() || !std::path::Path::new(&model_dir).exists() {
        anyhow::bail!("no cleanup model dir");
    }
    let threshold = cfg.cleanup.word_threshold;
    let mut slot = LLM_SERVER
        .get_or_init(|| std::sync::Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    llm_ensure_locked(&mut slot, &model_dir, &adapter_dir, threshold)?;
    Ok(())
}

/// Stream-mode cleanup entry: resident server first, one-shot fallback,
/// raw text when disabled or everything fails. Blocking — call from
/// spawn_blocking.
pub fn llm_cleanup(text: &str, cfg: &Config) -> String {
    if cfg.cleanup.mode != "stream" {
        return text.to_string();
    }
    // Explicit lists and emoji are handled deterministically before invoking
    // the generative sidecar; dictated commands remain plain text.
    if let Some(special) = crate::cleanup::closed_special(text) {
        return special;
    }
    match llm_server_cleanup(text, cfg) {
        Ok(s) if !s.is_empty() && crate::cleanup::semantic_ok(text, &s) => s,
        _ => {
            let fallback = llm_oneshot(text, cfg);
            if crate::cleanup::semantic_ok(text, &fallback) {
                fallback
            } else {
                text.to_string()
            }
        }
    }
}
