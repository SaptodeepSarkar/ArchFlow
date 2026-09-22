//! Cleanup-LLM supervision: resident `llm-server.py` sidecar for the
//! always-on source-grounded formatter.
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
/// Leave enough context for the formatter's instructions and an output that
/// preserves every source word. Long dictation is formatted as sequential,
/// independently guarded pieces instead of producing a truncated response.
const MAX_FORMAT_WORDS_PER_CHUNK: usize = 72;

/// A formatter result with a non-sensitive route identifier. The identifier
/// is safe to expose through diagnostics: it never includes dictated text.
pub struct CleanupResult {
    pub text: String,
    pub outcome: &'static str,
}

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

fn v6_package_path() -> Option<std::path::PathBuf> {
    let base = std::env::var_os("XDG_DATA_HOME")
        .map(std::path::PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| std::path::PathBuf::from(h).join(".local/share")))?;
    let path = base.join("vaani/cleanup/model.v6tg");
    path.is_file().then_some(path)
}

fn v6_cleanup(text: &str) -> Option<String> {
    let package = v6_package_path().and_then(|path| std::fs::read(path).ok())
        .and_then(|bytes| vaani_core::v6_tagger::parse(&bytes).ok())?;
    let words: Vec<&str> = text.split_whitespace().collect();
    if words.is_empty() { return Some(String::new()); }
    let (tokens, punctuation) = vaani_core::v6_tagger::predict(&package, &words).ok()?;
    let mut output = String::new();
    for (index, word) in words.iter().enumerate() {
        if matches!(tokens[index], 1 | 2 | 3) { continue; }
        if !output.is_empty() { output.push(' '); }
        if tokens[index] == 4 {
            let mut chars = word.chars();
            if let Some(first) = chars.next() { output.extend(first.to_uppercase()); output.extend(chars); }
        } else { output.push_str(word); }
        output.push_str(match punctuation[index] { 1 => ",", 2 => ".", 3 => "?", 4 => "!", 5 => ":", 6 => ";", _ => "" });
    }
    crate::cleanup::semantic_ok(text, &output).then_some(output)
}

fn llm_ensure_locked(
    slot: &mut Option<LlmServer>,
    model_dir: &str,
    adapter_dir: &str,
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
    llm_ensure_locked(&mut slot, &model_dir, &adapter_dir)?;
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
    let text_llm = text.to_string();
    let python = match python_path {
        Some(p) if p.exists() => p,
        _ => return text_llm,
    };
    let mut child = match std::process::Command::new("python3")
        .arg(&python)
        .arg("--adapter")
        .arg(&adapter_dir)
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
    let mut slot = LLM_SERVER
        .get_or_init(|| std::sync::Mutex::new(None))
        .lock()
        .unwrap_or_else(|e| e.into_inner());
    llm_ensure_locked(&mut slot, &model_dir, &adapter_dir)?;
    Ok(())
}

/// Format every non-empty final transcript: resident server first, then the
/// one-shot formatter after a server failure. A rejected generative rewrite
/// receives a deterministic, source-preserving punctuation/casing fallback.
/// Blocking — call from `spawn_blocking`.
pub fn llm_cleanup(text: &str, cfg: &Config) -> CleanupResult {
    let chunks = format_chunks(text, MAX_FORMAT_WORDS_PER_CHUNK);
    let formatted = if chunks.len() > 1 {
        let mut outcomes = Vec::with_capacity(chunks.len());
        let text = chunks
            .iter()
            .map(|chunk| {
                let result = llm_cleanup_one(chunk, cfg);
                outcomes.push(result.outcome);
                result.text
            })
            .collect::<Vec<_>>()
            .join(" ");
        CleanupResult {
            text,
            outcome: if outcomes
                .iter()
                .all(|outcome| *outcome == "sidecar_accepted")
            {
                "chunked_sidecar_accepted"
            } else {
                "chunked_with_safe_fallback"
            },
        }
    } else {
        llm_cleanup_one(text, cfg)
    };
    // Economy means no formatter model stays resident between dictations.
    // Unlike the periodic reaper, this runs immediately after the request.
    if cfg.effective_server_idle_secs() == 0 {
        reap_idle_llm(0);
    }
    tracing::info!(formatter_outcome = formatted.outcome, "formatter completed");
    formatted
}

fn llm_cleanup_one(text: &str, cfg: &Config) -> CleanupResult {
    match crate::cleanup::closed_special(text) {
        Some(special) => CleanupResult {
            text: special,
            outcome: "deterministic_structure",
        },
        None => match v6_cleanup(text) {
            Some(s) => CleanupResult { text: s, outcome: "v6_native_accepted" },
            None => match llm_server_cleanup(text, cfg) {
            Ok(s) if !s.is_empty() && crate::cleanup::semantic_ok(text, &s) => CleanupResult {
                text: s,
                outcome: "sidecar_accepted",
            },
            Ok(_) => CleanupResult {
                text: crate::cleanup::conservative_format(text),
                outcome: "sidecar_rejected_deterministic_fallback",
            },
            Err(_) => one_shot_result(text, cfg, "sidecar_failed"),
            },
        },
    }
}

fn format_chunks(text: &str, max_words: usize) -> Vec<String> {
    let words = text.split_whitespace().collect::<Vec<_>>();
    if words.len() <= max_words {
        return vec![text.to_string()];
    }
    words
        .chunks(max_words)
        .map(|chunk| chunk.join(" "))
        .collect()
}

fn one_shot_result(text: &str, cfg: &Config, prefix: &'static str) -> CleanupResult {
    let fallback = llm_oneshot(text, cfg);
    if crate::cleanup::semantic_ok(text, &fallback) {
        CleanupResult {
            text: fallback,
            outcome: if prefix == "sidecar_rejected" {
                "sidecar_rejected_oneshot_accepted"
            } else {
                "sidecar_failed_oneshot_accepted"
            },
        }
    } else {
        CleanupResult {
            text: crate::cleanup::conservative_format(text),
            outcome: "sidecar_failed_oneshot_rejected_deterministic_fallback",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::format_chunks;

    #[test]
    fn long_format_input_is_bounded_without_losing_words() {
        let source = (0..145)
            .map(|n| format!("word{n}"))
            .collect::<Vec<_>>()
            .join(" ");
        let chunks = format_chunks(&source, 72);
        assert_eq!(chunks.len(), 3);
        assert!(chunks
            .iter()
            .all(|chunk| chunk.split_whitespace().count() <= 72));
        assert_eq!(chunks.join(" "), source);
    }
}
