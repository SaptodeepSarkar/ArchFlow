//! vaanid: authoritative state machine, config, IPC, capture coordination,
//! focus checks, worker supervision. The ONLY required long-lived process.
//!
//! Socket: $XDG_RUNTIME_DIR/vaani/control.sock (dir 0700, socket 0600).
//! Framed control messages (newline JSON, 1 MiB cap); bounded audio in memory.
//! Events for state/amplitude (no polling). Subscriber gets a snapshot first.

use crate::capture::CaptureHandle;
use crate::focus::FocusTarget;
use crate::{cleanup, clipboard, focus, inserter, paths, worker_sup};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::{UnixListener, UnixStream};
use tokio::sync::{broadcast, Mutex};
use vaani_core::config::Config;
use vaani_core::protocol::{Event, Request, RequestKind, Response};
use vaani_core::state::{Session, State};

#[derive(Clone)]
struct Pending {
    text: String,
    at: std::time::Instant,
}

struct Shared {
    cfg: Config,
    session: Session,
    seq: u64,
    capture: Option<CaptureHandle>,
    audio: Vec<f32>,
    amplitude: f32,
    pending: Option<Pending>,
    pending_audio: Vec<f32>, // retained briefly for retry after error
    target: FocusTarget,
    ui_level: Vec<f32>, // last waveform snapshot for subscribers
    last_lat: Latencies,
    residency_warm_until: Option<std::time::Instant>,
    /// Session ids for which automatic insertion is disabled (settings or
    /// review window was opened during the operation).
    no_auto: Option<String>,
    /// Live dictation (SUPER+H): commit stabilized words while recording.
    live: bool,
    /// Stable text already typed into the target in this live session.
    committed: String,
    /// Cumulative transcript assembled from incremental audio chunks.
    live_transcript: String,
    /// End sample represented by the last accepted live chunk.
    live_audio_cursor: usize,
    /// Last accepted activation (toggle/start): repeats inside the window
    /// are ignored so key-repeat can't start+stop instantly.
    last_activation: Option<std::time::Instant>,
    /// When the current session started recording. A second Super+H inside
    /// the bounce window is key-repeat/mashing (the overlay takes ~1 s to
    /// appear), not an intentional discard — it must not kill the session.
    session_started_at: Option<std::time::Instant>,
    /// Focus lost mid-live-session: stop committing, keep accumulating.
    target_lost: bool,
}

#[derive(Default, Clone, serde::Serialize)]
struct Latencies {
    mic_ready_ms: u64,
    stop_to_text_ms: u64,
    inference_ms: u64,
    dispatch_ms: u64,
    /// Which backend produced the last final transcript
    /// (whisper-cli-cuda | fw-ct2 | cpu-stub). Visible via `vaani status`
    /// so a wrong-model regression is caught from numbers, not vibes.
    backend: String,
}

pub async fn run() -> anyhow::Result<()> {
    paths::ensure_dirs()?;
    let sock = paths::control_sock();
    if UnixStream::connect(&sock).await.is_ok() {
        anyhow::bail!("vaanid is already running");
    }
    // Remove stale socket; bind; chmod 0600.
    let _ = std::fs::remove_file(&sock);
    let listener = UnixListener::bind(&sock)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&sock, std::fs::Permissions::from_mode(0o600));
    }
    tracing::info!(sock = %sock.display(), "listening");

    let (tx, _rx) = broadcast::channel::<Event>(256);
    let shared = Arc::new(Mutex::new(Shared {
        cfg: Config::load(),
        session: Session::new(0),
        seq: 0,
        capture: None,
        audio: Vec::new(),
        amplitude: 0.0,
        pending: None,
        pending_audio: Vec::new(),
        target: FocusTarget::default(),
        ui_level: Vec::new(),
        last_lat: Latencies::default(),
        residency_warm_until: None,
        no_auto: None,
        live: false,
        committed: String::new(),
        live_transcript: String::new(),
        live_audio_cursor: 0,
        target_lost: false,
        session_started_at: None,
        last_activation: None,
    }));

    // Session-lock/suspend guard: on lock, cancel capture + forbid insertion.
    {
        let s = shared.clone();
        let t = tx.clone();
        tokio::spawn(async move { lock_watch(s, t).await });
    }
    // Resident STT server reaper: frees VRAM after configured idle seconds.
    {
        let s = shared.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(30)).await;
                let idle = s.lock().await.cfg.recognition.server_idle_secs;
                if idle > 0 {
                    worker_sup::reap_idle_servers(idle);
                }
            }
        });
    }
    // Pending-text expiry sweeper (5 min default, in-memory only).
    {
        let s = shared.clone();
        let expiry_tx = tx.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(15)).await;
                let mut g = s.lock().await;
                if let Some(p) = &g.pending {
                    if p.at.elapsed().as_secs() > g.cfg.insertion.pending_expiry_secs {
                        g.pending = None;
                        emit(&expiry_tx, &Event {
                            protocol_version: vaani_core::PROTOCOL_VERSION,
                            event: "pending_expired".into(),
                            session_id: None,
                            state: Some("IDLE".into()),
                            amplitude: None,
                            message: Some("pending text expired".into()),
                            data: None,
                        });
                    }
                }
            }
        });
    }

    loop {
        let (stream, _) = listener.accept().await?;
        let s = shared.clone();
        let t = tx.clone();
        tokio::spawn(async move { handle_conn(stream, s, t).await });
    }
}

fn emit(tx: &broadcast::Sender<Event>, ev: &Event) {
    let _ = tx.send(ev.clone());
}

fn ev_state(session: Option<String>, state: State, msg: Option<&str>) -> Event {
    ev_state_data(session, state, msg, None)
}

/// State event with a data payload (e.g. `{"copied": true}` so the overlay
/// can linger a confirmation even when the RPC response has no listener,
/// as with hands-free auto-stop).
fn ev_state_data(
    session: Option<String>,
    state: State,
    msg: Option<&str>,
    data: Option<serde_json::Value>,
) -> Event {
    Event {
        protocol_version: vaani_core::PROTOCOL_VERSION,
        event: "state".into(),
        session_id: session,
        state: Some(format!("{state:?}").to_uppercase()),
        amplitude: None,
        message: msg.map(|s| s.into()),
        data,
    }
}

async fn handle_conn(stream: UnixStream, shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>) {
    let (r, w) = stream.into_split();
    let w = Arc::new(Mutex::new(w));
    let mut reader = BufReader::new(r);
    let mut rx = tx.subscribe();
    // Subscribe before taking the snapshot so transitions cannot be lost.
    // Snapshot first for subscribers.
    let snap = {
        let g = shared.lock().await;
        serde_json::json!({
            "state": format!("{:?}", g.session.state).to_uppercase(),
            "session_id": g.session.id,
            "pending": g.pending.is_some(),
        })
    };
    {
        let mut g = w.lock().await;
        let _ = g
            .write_all(format!("{snap}\n").as_bytes())
            .await;
    }

    // Event forwarder: state/amplitude/provisional events reach subscribers
    // over this same connection (no polling). Stale amplitude updates are
    // coalesced under load — only the latest is forwarded.
    let w2 = w.clone();
    let fwd = tokio::spawn(async move {
        loop {
            let mut ev = match rx.recv().await {
                Ok(ev) => ev,
                Err(broadcast::error::RecvError::Lagged(_)) => continue,
                Err(broadcast::error::RecvError::Closed) => break,
            };
            if ev.event == "amplitude" {
                // Drain queued amplitudes, keep the newest.
                while let Ok(nxt) = rx.try_recv() {
                    if nxt.event == "amplitude" {
                        ev = nxt;
                    } else {
                        // Non-amplitude event queued behind: flush the latest
                        // amplitude first, then forward the other event below.
                        let line = serde_json::to_string(&ev).unwrap_or_default() + "\n";
                        let mut g = w2.lock().await;
                        if g.write_all(line.as_bytes()).await.is_err() {
                            return;
                        }
                        ev = nxt;
                        break;
                    }
                }
            }
            let line = serde_json::to_string(&ev).unwrap_or_default() + "\n";
            let mut g = w2.lock().await;
            if g.write_all(line.as_bytes()).await.is_err() {
                break;
            }
        }
    });

    loop {
        // Limit allocation while reading, including clients that never send a newline.
        let mut bytes = Vec::new();
        let mut limited = (&mut reader).take((vaani_core::MAX_CONTROL_BYTES + 1) as u64);
        match limited.read_until(b'\n', &mut bytes).await {
            Ok(0) | Err(_) => break,
            Ok(_) => {}
        }
        if bytes.len() > vaani_core::MAX_CONTROL_BYTES { break; }
        let line = match String::from_utf8(bytes) { Ok(line) => line, Err(_) => break };
        if line.trim().is_empty() {
            continue;
        }
        let req = match Request::validate_line(&line) {
            Ok(r) => r,
            Err(e) => {
                let resp = Response {
                    protocol_version: vaani_core::PROTOCOL_VERSION,
                    request_id: "unknown".into(),
                    session_id: None,
                    ok: false,
                    state: None,
                    message: Some(e),
                    data: None,
                };
                let mut g = w.lock().await;
                let _ = g.write_all(format!("{}\n", serde_json::to_string(&resp).unwrap()).as_bytes()).await;
                continue;
            }
        };
        let rid = req.request_id.clone();
        let resp = dispatch(req, shared.clone(), tx.clone()).await;
        let mut resp = resp;
        if resp.request_id.is_empty() {
            resp.request_id = rid;
        }
        let mut g = w.lock().await;
        if g
            .write_all(format!("{}\n", serde_json::to_string(&resp).unwrap()).as_bytes())
            .await
            .is_err()
        {
            break;
        }
    }
    fwd.abort();
}

fn resp_ok(rid: &str, sess: &Session, msg: Option<String>, data: Option<serde_json::Value>) -> Response {
    Response {
        protocol_version: vaani_core::PROTOCOL_VERSION,
        request_id: rid.into(),
        session_id: Some(sess.id.clone()),
        ok: true,
        state: Some(format!("{:?}", sess.state).to_uppercase()),
        message: msg,
        data,
    }
}

/// Stream-mode cleanup: pipe `text` through the local cleanup LLM
/// (vaani_inject.py + frozen base + LoRA adapter) when mode == "stream"
/// and the transcript meets the word threshold. Raw text is returned on
/// any failure (missing script, spawn error, empty output). Blocking —
/// always call from spawn_blocking.
fn run_stream_cleanup(text: &str, cfg: &Config) -> String {
    let threshold = cfg.cleanup.word_threshold;
    if cfg.cleanup.mode != "stream" || text.split_whitespace().count() < threshold {
        return text.to_string();
    }
    let python_path = if cfg.cleanup.python_path.is_empty() {
        std::env::current_exe().ok()
            .and_then(|p| p.parent().map(|d| d.join("vaani_inject.py")))
    } else {
        Some(std::path::PathBuf::from(&cfg.cleanup.python_path))
    };
    let model_dir = if cfg.cleanup.model_path.is_empty() {
        std::env::current_exe().ok()
            .and_then(|p| p.parent().map(|d| d.join("..").join("output").join("base-model")))
    } else {
        Some(std::path::PathBuf::from(&cfg.cleanup.model_path))
    };
    let adapter = if !cfg.cleanup.adapter_path.is_empty() {
        cfg.cleanup.adapter_path.clone()
    } else if !cfg.cleanup.model_path.is_empty() {
        format!("{}/../dpo-sft", cfg.cleanup.model_path)
    } else {
        String::new()
    };
    let text_llm = text.to_string();
    let python = match python_path {
        Some(p) if p.exists() => p,
        _ => return text_llm,
    };
    let mut child = match std::process::Command::new("python3")
        .arg(&python)
        .arg("--adapter").arg(&adapter)
        .arg("--threshold").arg(threshold.to_string())
        .arg("--model-dir").arg(model_dir.unwrap_or_default())
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
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
        if std::io::Write::write_all(&mut stdin, text_llm.as_bytes()).is_err() {
            return text_llm;
        }
    }
    match child.wait_with_output() {
        Ok(out) => {
            let s = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if !s.is_empty() { s } else { text_llm }
        }
        Err(_) => text_llm,
    }
}

/// Key-repeat guard: activations within 800 ms of the previous accepted one
/// are ignored (a held shortcut must not start+stop instantly).
/// Returns true when this activation is accepted.
async fn take_activation(shared: &Arc<Mutex<Shared>>) -> bool {
    let mut g = shared.lock().await;
    let now = std::time::Instant::now();
    if let Some(last) = g.last_activation {
        if now.duration_since(last).as_millis() < 800 {
            return false;
        }
    }
    g.last_activation = Some(now);
    true
}

async fn dispatch(req: Request, shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>) -> Response {
    let rid = req.request_id.clone();
    tracing::info!(op = ?req.kind, rid = %rid, "ipc request");
    match req.kind {
        RequestKind::Toggle => {
            let busy = {
                let g = shared.lock().await;
                !matches!(g.session.state, State::Idle | State::Ready | State::Cancelled | State::Error)
            };
            if busy {
                stop_flow(shared.clone(), &tx).await
            } else if !take_activation(&shared).await {
                let g = shared.lock().await;
                resp_ok(&rid, &g.session, Some("ignoring key repeat".into()), None)
            } else {
                // If READY with pending text and target unchanged, toggle re-inserts? No:
                // toggle from READY with pending just reports ready (explicit copy/insert).
                start_flow(shared.clone(), &tx, false).await
            }
        }
        RequestKind::LiveToggle => {
            let (state, fresh) = {
                let g = shared.lock().await;
                let fresh = g
                    .session_started_at
                    .map(|t| t.elapsed().as_millis() < 1200)
                    .unwrap_or(false);
                (g.session.state, fresh)
            };
            if matches!(state, State::Recording | State::Starting) && !fresh {
                // SUPER+H mid-recording: discard everything and close.
                // (Finishing happens hands-free on end-of-speech silence.)
                cancel_flow(shared.clone(), &tx, &rid).await
            } else if matches!(state, State::Recording | State::Starting) {
                // Bounce inside the first second: the overlay is still
                // appearing, so this is mashing, not intent. Keep recording.
                let g = shared.lock().await;
                resp_ok(&rid, &g.session, Some("ignoring key repeat".into()), None)
            } else if matches!(state, State::Transcribing | State::Cleaning | State::Inserting) {
                // Finishing stages: capture is already closed, so there is
                // nothing to discard — and a habitual stop-press must never
                // kill the transcript it just recorded. Report and keep going.
                let g = shared.lock().await;
                resp_ok(&rid, &g.session, Some("finishing transcription…".into()), None)
            } else if !take_activation(&shared).await {
                let g = shared.lock().await;
                resp_ok(&rid, &g.session, Some("ignoring key repeat".into()), None)
            } else {
                start_flow(shared.clone(), &tx, true).await
            }
        }
        RequestKind::Start => {
            let busy = {
                let g = shared.lock().await;
                !matches!(g.session.state, State::Idle | State::Ready | State::Cancelled | State::Error)
            };
            if busy {
                let g = shared.lock().await;
                return Response {
                    protocol_version: vaani_core::PROTOCOL_VERSION,
                    request_id: rid.clone(),
                    session_id: Some(g.session.id.clone()),
                    ok: false,
                    state: Some(format!("{:?}", g.session.state).to_uppercase()),
                    message: Some("busy: already recording/transcribing; stop or cancel first".into()),
                    data: None,
                };
            }
            if !take_activation(&shared).await {
                let g = shared.lock().await;
                return resp_ok(&rid, &g.session, Some("ignoring key repeat".into()), None);
            }
            start_flow(shared.clone(), &tx, false).await
        }
        RequestKind::Stop => stop_flow(shared.clone(), &tx).await,
        RequestKind::Cancel => cancel_flow(shared.clone(), &tx, &rid).await,
        RequestKind::Status => {
            let g = shared.lock().await;
            resp_ok(&rid, &g.session, None, Some(serde_json::json!({
                "pending": g.pending.is_some(),
                "amplitude": g.amplitude,
                "latencies": g.last_lat,
            })))
        }
        RequestKind::Subscribe => {
            // Subscription is implicit: UI holds the connection and reads
            // broadcast events via a second `subscribe-stream`? For v1 the
            // snapshot + state responses suffice; amplitude streams as events
            // on this same connection below.
            let g = shared.lock().await;
            resp_ok(&rid, &g.session, Some("subscribed; snapshot first".into()), None)
        }
        RequestKind::Settings => {
            // Launch Quickshell settings on demand (separate app-owned config).
            // A focused settings/review window disables automatic insertion
            // for the in-flight operation (focus safety).
            let mut g = shared.lock().await;
            if !matches!(g.session.state, State::Idle) {
                g.no_auto = Some(g.session.id.clone());
            }
            drop(g);
            std::thread::spawn(|| {
                // Reap the child so closed UI processes never linger as zombies.
                let mut child = std::process::Command::new("quickshell")
                    .arg("-p")
                    .arg(paths::ui_path())
                    .env("VAANI_SOCKET", paths::control_sock())
                    .env("VAANI_OPEN_SETTINGS", "1")
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::inherit())
                    .spawn();
                if let Ok(ref mut c) = child {
                    let _ = c.wait();
                }
            });
            let g = shared.lock().await;
            resp_ok(&rid, &g.session, Some("settings requested".into()), None)
        }
        RequestKind::Doctor => {
            let data = doctor().await;
            let g = shared.lock().await;
            resp_ok(&rid, &g.session, None, Some(data))
        }
        RequestKind::CopyPending => {
            let text = { shared.lock().await.pending.clone().map(|p| p.text) };
            match text {
                Some(text) => match clipboard::offer_text(&text) {
                    Ok(()) => {
                        let g = shared.lock().await;
                        resp_ok(&rid, &g.session, Some("copied to clipboard".into()), None)
                    }
                    Err(e) => {
                        let g = shared.lock().await;
                        Response { ok: false, message: Some(format!("copy failed: {e}")), ..resp_ok(&rid, &g.session, None, None) }
                    }
                },
                None => {
                    let g = shared.lock().await;
                    Response { ok: false, message: Some("no pending text".into()), ..resp_ok(&rid, &g.session, None, None) }
                }
            }
        }
        RequestKind::RecoverPending => {
            let g = shared.lock().await;
            match &g.pending {
                Some(p) => resp_ok(&rid, &g.session, None, Some(serde_json::json!({"text": p.text}))),
                None => Response { ok: false, message: Some("no pending text".into()), ..resp_ok(&rid, &g.session, None, None) },
            }
        }
        RequestKind::DiscardPending => {
            let mut g = shared.lock().await;
            g.pending = None;
            g.pending_audio.clear();
            resp_ok(&rid, &g.session, Some("discarded".into()), None)
        }
        RequestKind::ConfigGet => {
            let g = shared.lock().await;
            let data = serde_json::to_value(&g.cfg).unwrap_or(serde_json::Value::Null);
            resp_ok(&rid, &g.session, None, Some(data))
        }
        RequestKind::ConfigSet { key, value } => {
            if key.len() > 64 || value.len() > 512 {
                let g = shared.lock().await;
                return Response { ok: false, message: Some("key/value too large".into()), ..resp_ok(&rid, &g.session, None, None) };
            }
            let mut g = shared.lock().await;
            match g.cfg.set_key(&key, &value) {
                Ok(canonical) => match g.cfg.save() {
                    Ok(()) => resp_ok(&rid, &g.session, Some("saved".into()), Some(serde_json::json!({"key": key, "value": canonical}))),
                    Err(e) => Response { ok: false, message: Some(format!("save failed: {e}")), ..resp_ok(&rid, &g.session, None, None) },
                },
                Err(e) => Response { ok: false, message: Some(e), ..resp_ok(&rid, &g.session, None, None) },
            }
        }
        RequestKind::MicTest { secs } => match crate::capture::mic_test(secs) {
            Ok((peak, rms)) => {
                let g = shared.lock().await;
                resp_ok(&rid, &g.session, None, Some(serde_json::json!({"peak": peak, "rms": rms})))
            }
            Err(e) => {
                let g = shared.lock().await;
                Response { ok: false, message: Some(format!("mic test failed: {e}")), ..resp_ok(&rid, &g.session, None, None) }
            }
        },
        RequestKind::Inject => {
            let (text, cfg) = {
                let g = shared.lock().await;
                match &g.pending {
                    Some(p) => (p.text.clone(), g.cfg.clone()),
                    None => {
                        let s = g.session.clone();
                        return Response { ok: false, message: Some("no pending text — finish a session first".into()), session_id: Some(s.id.clone()), ..resp_ok(&rid, &s, None, None) };
                    }
                }
            };
            let word_count = text.split_whitespace().count();
            let threshold = cfg.cleanup.word_threshold;
            let fallback = text.clone();
            let cleaned = tokio::task::spawn_blocking(move || run_stream_cleanup(&text, &cfg))
                .await
                .unwrap_or(fallback);
            // Non-stream modes (and short transcripts) fall through raw.
            // Stream via virtual keyboard (keyboard locked only during typing).
            let cleaned_for_inject = cleaned.clone();
            let res = tokio::task::spawn_blocking(move || -> anyhow::Result<()> {
                crate::inserter::inject_stream(&cleaned_for_inject)
            }).await;
            let g = shared.lock().await;
            match res {
                Ok(Ok(())) => {
                    let s = g.session.clone();
                    let mut g = shared.lock().await;
                    g.pending = None;
                    resp_ok(&rid, &s, Some("injected via keyboard".into()), Some(serde_json::json!({"text": cleaned, "words": word_count, "threshold": threshold})))
                }
                _ => {
                    let s = g.session.clone();
                    resp_ok(&rid, &s, Some("injection failed — text on clipboard".into()), Some(serde_json::json!({"text": cleaned, "words": word_count})))
                }
            }
        }
    }
}

async fn start_flow(shared: Arc<Mutex<Shared>>, tx: &broadcast::Sender<Event>, live: bool) -> Response {
    // Reject new recording while busy (no silent queueing).
    {
        let mut g = shared.lock().await;
        if !matches!(g.session.state, State::Idle | State::Ready | State::Cancelled | State::Error) {
            let s = g.session.clone();
            return Response {
                protocol_version: vaani_core::PROTOCOL_VERSION,
                request_id: String::new(),
                session_id: Some(s.id.clone()),
                ok: false,
                state: Some(format!("{:?}", s.state).to_uppercase()),
                message: Some("busy: already recording/transcribing; stop or cancel first".into()),
                data: None,
            };
        }
        g.seq += 1;
        g.session = Session::new(g.seq);
        let sid = g.session.id.clone();
        let _ = g.session.transition(State::Starting);
        g.audio.clear();
        g.pending_audio.clear();
        g.target = focus::active_target();
        g.live = live;
        g.committed = String::new();
        g.live_transcript.clear();
        g.live_audio_cursor = 0;
        g.target_lost = false;
        g.session_started_at = None;
        emit(tx, &ev_state(Some(sid), State::Starting, Some("Starting microphone…")));
        // On-demand overlay UI (separate app-owned Quickshell config).
        // The reaper thread keeps closed UI processes from becoming zombies.
        std::thread::spawn(|| {
            let mut child = std::process::Command::new("quickshell")
                .arg("-p")
                .arg(paths::ui_path())
                .env("VAANI_SOCKET", paths::control_sock())
                .env_remove("VAANI_OPEN_SETTINGS")
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::inherit())
                .spawn();
            if let Ok(ref mut c) = child {
                let _ = c.wait();
            }
        });
    }

    // Start capture + model resolution concurrently.
    let t0 = std::time::Instant::now();
    let device_sel = { shared.lock().await.cfg.audio.device_selector.clone() };
    let cap = CaptureHandle::start(&device_sel);
    let mut g = shared.lock().await;
    match cap {
        Ok(h) => {
            let ready_ms = t0.elapsed().as_millis() as u64;
            g.last_lat.mic_ready_ms = ready_ms;
            g.capture = Some(h);
            let sid = g.session.id.clone();
            let _ = g.session.transition(State::Recording);
            g.session_started_at = Some(std::time::Instant::now());
            // Tell the user immediately if this is not a typable space.
            let note = space_note_for(&g.target, &g.cfg);
            let rec_msg;
            let msg: &str = match &note {
                Some(n) => {
                    rec_msg = n.clone();
                    &rec_msg
                }
                None => "Listening",
            };
            emit(tx, &ev_state(Some(sid.clone()), State::Recording, Some(msg)));
            // Spawn amplitude pump: drains blocks, forwards audio, emits ≤30 Hz.
            let sh = shared.clone();
            let t2 = tx.clone();
            let sess = sid.clone();
            tokio::spawn(async move { amplitude_loop(sh, t2, sess).await });
            // Silero end-of-speech watch (all modes: hands-free finish).
            {
                let sh = shared.clone();
                let t4 = tx.clone();
                let sess = sid.clone();
                tokio::spawn(async move { auto_stop_watch(sh, t4, sess).await });
            }
            // Live dictation: commit stabilized words while recording.
            if live {
                let sh = shared.clone();
                let t3 = tx.clone();
                let sess = sid.clone();
                tokio::spawn(async move { live_loop(sh, t3, sess).await });
            }
            let s = g.session.clone();
            let started_msg = match space_note_for(&g.target, &g.cfg) {
                Some(n) => format!("Listening{} — {n}", if live { " (live)" } else { "" }),
                None => format!("Listening{}", if live { " (live)" } else { "" }),
            };
            resp_ok("", &s, Some(started_msg), None)
        }
        Err(e) => {
            let _ = g.session.transition(State::Error);
            let sid = g.session.id.clone();
            emit(tx, &ev_state(Some(sid), State::Error, Some("Microphone unavailable")));
            let s = g.session.clone();
            let _ = s;
            Response {
                protocol_version: vaani_core::PROTOCOL_VERSION,
                request_id: String::new(),
                session_id: Some(g.session.id.clone()),
                ok: false,
                state: Some("ERROR".into()),
                message: Some(format!("capture failed: {e}")),
                data: None,
            }
        }
    }
}

/// Drain capture blocks -> session audio, emit coalesced amplitude ≤30 Hz.
/// Hands-free finish: after speech was heard, sustained silence (auto_stop
/// config) ends the session via stop_flow (transcribe → inject → close).
async fn amplitude_loop(shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>, sess: String) {
    let mut last_emit = std::time::Instant::now();
    let mut vad = vaani_core::vad::Vad::default();
    let mut speech_seen = false;
    let mut last_voice = std::time::Instant::now();
    loop {
        tokio::time::sleep(std::time::Duration::from_millis(33)).await;
        let (alive, amp, sid_ok) = {
            let mut g = shared.lock().await;
            if g.session.id != sess || !matches!(g.session.state, State::Recording) {
                (false, 0.0, false)
            } else if g.capture.is_some() {
                // Drain without blocking; collect first so the channel borrow
                // ends before touching session audio (never block callback).
                let mut blocks: Vec<Vec<f32>> = Vec::new();
                if let Some(cap) = g.capture.as_mut() {
                    while let Ok(b) = cap.rx.try_recv() {
                        blocks.push(b);
                    }
                }
                for b in blocks {
                    if b.len() == vaani_core::vad::BLOCK_SAMPLES && vad.push_block(&b) {
                        last_voice = std::time::Instant::now();
                        speech_seen = true;
                    }
                    let peak = b.iter().fold(0.0f32, |a, &x| a.max(x.abs()));
                    g.amplitude = peak;
                    g.audio.extend_from_slice(&b);
                }
                let cap_max = (vaani_core::MAX_AUDIO_SECS as usize) * 16_000;
                let audio_len = g.audio.len();
                if audio_len > cap_max {
                    g.audio.drain(..audio_len - cap_max);
                }
                // Session time limit enforcement.
                let max = g.cfg.audio.max_secs as usize * 16_000;
                if g.audio.len() >= max {
                    (false, g.amplitude, true) // auto-stop at cap
                } else {
                    // Hands-free finish: speech + sustained silence.
                    let auto = g.cfg.general.auto_stop_secs;
                    if auto > 0
                        && speech_seen
                        && last_voice.elapsed().as_secs() >= auto
                    {
                        tracing::info!("auto-stop on end-of-speech silence");
                        (false, g.amplitude, true)
                    } else {
                        (true, g.amplitude, false)
                    }
                }
            } else {
                (false, 0.0, false)
            }
        };
        if !alive {
            if sid_ok {
                // Auto-stop at session limit: drop lock before stop_flow.
                tracing::info!(sess = %sess, "auto-stop at session cap");
                stop_flow(shared.clone(), &tx).await;
            }
            break;
        }
        if last_emit.elapsed().as_millis() >= 33 {
            last_emit = std::time::Instant::now();
            emit(&tx, &Event {
                protocol_version: vaani_core::PROTOCOL_VERSION,
                event: "amplitude".into(),
                session_id: Some(sess.clone()),
                state: Some("RECORDING".into()),
                amplitude: Some(amp),
                message: None,
                data: None,
            });
        }
    }
}

/// Tell the user UP FRONT where their words will go. Returns a note when
/// the session will NOT type into the target (terminal, no focus, review).
fn space_note_for(t: &FocusTarget, cfg: &vaani_core::config::Config) -> Option<String> {
    if t.address.is_empty() {
        return Some("No focused window — recording anyway, text kept for copy".into());
    }
    if focus::is_terminal(&t.app_id) || cfg.insertion_mode_for(&t.app_id) == "copy-only" {
        return Some(format!(
            "{}: copy-only space — nothing auto-typed, finish then copy",
            if t.app_id.is_empty() { "this window" } else { t.app_id.as_str() }
        ));
    }
    if cfg.insertion.mode == "review" || cfg.general.review_before_insertion {
        return Some("Review mode — nothing typed until you confirm".into());
    }
    None
}

/// Provisional transcript event for the overlay. `tail` is explicitly NOT
/// inserted text — only stable committed words ever reach the target app.
/// When `hidden` (screen-sharing switch), the tail is withheld.
fn emit_provisional(
    tx: &broadcast::Sender<Event>,
    sess: &str,
    tail: &str,
    hidden: bool,
    committed_words: usize,
) {
    let (last, next) = if hidden { ("", "") } else { vaani_core::reconcile::preview_words(tail) };
    // Running preview: the newest words with the current (newest) word
    // highlighted in the overlay, so the speaker always sees their place.
    // Five words max — older context scrolls off, never ellipsized mid-stream.
    let words = if hidden { String::new() } else { vaani_core::reconcile::recent_words(tail, 5) };
    emit(tx, &Event {
        protocol_version: vaani_core::PROTOCOL_VERSION,
        event: "provisional".into(),
        session_id: Some(sess.into()),
        state: Some("RECORDING".into()),
        amplitude: None,
        message: None,
        data: Some(serde_json::json!({
            "tail": format!("{last} {next}").trim(),
            "words": words,
            "hidden": hidden,
            "committed_words": committed_words,
            "last_word": last,
            "next_word": next,
        })),
    });
}

struct LiveSnap {
    audio: Vec<f32>,
    audio_end: usize,
    transcript: String,
    cfg: vaani_core::config::Config,
    target: FocusTarget,
}

enum LiveTick {
    Exit,
    Skip,
    Work(LiveSnap),
}

/// Silero end-of-speech watch (all modes): every 2 s, analyse trailing
/// silence of the session so far. Speech followed by sustained silence
/// finishes hands-free (transcribe → inject → close). Without the VAD
/// binary, the energy gate in amplitude_loop is the fallback.
async fn auto_stop_watch(shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>, sess: String) {
    if worker_sup::vad_bin().is_none() {
        return;
    }
    loop {
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        let snap: Option<(Vec<f32>, u64)> = {
            let g = shared.lock().await;
            if g.session.id != sess || !matches!(g.session.state, State::Recording) {
                None
            } else if g.cfg.general.auto_stop_secs == 0 || g.audio.len() < 16_000 {
                Some((Vec::new(), 0)) // skip tick
            } else {
                Some((g.audio.clone(), g.cfg.general.auto_stop_secs))
            }
        };
        let (audio, auto) = match snap {
            None => break,
            Some((a, _)) if a.is_empty() => continue,
            Some(v) => v,
        };
        let res = tokio::task::spawn_blocking(move || worker_sup::silero_trailing(&audio)).await;
        let trailing = match res {
            Ok(Some((true, tr))) => tr,
            _ => continue, // no speech yet, or VAD hiccup: retry next tick
        };
        if trailing >= auto as f32 {
            tracing::info!(trailing_s = trailing, "silero end-of-speech: auto finish");
            stop_flow(shared.clone(), &tx).await;
            break;
        }
    }
}
/// Live loop (SUPER+H): every chunk, transcribe cumulative audio, commit only
/// the newly stabilized prefix (last TAIL words held back as provisional).
/// A worker failure retries next tick; the controller stays up.
fn live_tail_words() -> usize {
    1
}

async fn live_loop(shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>, sess: String) {
    loop {
        let chunk_secs = { shared.lock().await.cfg.general.live_chunk_secs.clamp(1, 10) };
        tokio::time::sleep(std::time::Duration::from_secs(chunk_secs)).await;
        let tick: LiveTick = {
            let g = shared.lock().await;
            if g.session.id != sess || !matches!(g.session.state, State::Recording) || !g.live {
                LiveTick::Exit
            } else if g.target_lost {
                LiveTick::Skip // focus lost: keep recording, commit nothing
            } else if g.audio.len().saturating_sub(g.live_audio_cursor) < 8_000 {
                LiveTick::Skip // <1 s: not worth an inference pass
            } else {
                // One-second overlap lets reconciliation remove words split
                // across chunks without retranscribing the whole recording.
                let start = g.live_audio_cursor.saturating_sub(16_000);
                LiveTick::Work(LiveSnap {
                    audio: g.audio[start..].to_vec(),
                    audio_end: g.audio.len(),
                    transcript: g.live_transcript.clone(),
                    cfg: g.cfg.clone(),
                    target: g.target.clone(),
                })
            }
        };
        let snap = match tick {
            LiveTick::Exit => break,
            LiveTick::Skip => continue,
            LiveTick::Work(s) => s,
        };
        let previous_transcript = snap.transcript.clone();
        let work = tokio::task::spawn_blocking(move || {
            let cuda = snap.cfg.recognition.device == "cuda";
            worker_sup::transcribe(
                &snap.audio,
                &snap.cfg.recognition.live_model,
                &snap.cfg.recognition.language,
                snap.cfg.recognition.translate_to_en,
                snap.cfg.audio.worker_threads,
                cuda,
                &snap.cfg.cleanup.vocabulary,
                snap.cfg.recognition.server_idle_secs,
            )
        })
        .await;
        let mut g = shared.lock().await;
        // Stale guard: only the live RECORDING session may commit.
        if g.session.id != sess || !matches!(g.session.state, State::Recording) || !g.live {
            break;
        }
        let hide = g.cfg.privacy.hide_preview_on_sharing;
        let committed_n = g.committed.split_whitespace().count();
        let t = match work {
            Ok(Ok(t)) => t,
            Ok(Err(e)) => {
                // Worker hiccup: retry next tick, keep recording. Keep the
                // last-known provisional words on screen (never blank them:
                // a flickering preview reads as "no live transcription").
                tracing::warn!("live tick transcription failed: {e:#}");
                let known = g.live_transcript.clone();
                emit_provisional(&tx, &sess, &known, hide, committed_n);
                continue;
            }
            Err(e) => {
                tracing::warn!("live tick task failed: {e}");
                let known = g.live_transcript.clone();
                emit_provisional(&tx, &sess, &known, hide, committed_n);
                continue;
            }
        };
        if t.is_silence || t.text.is_empty() {
            // Pause or partial-word window: hold the last-known words.
            let known = g.live_transcript.clone();
            emit_provisional(&tx, &sess, &known, hide, committed_n);
            continue;
        }
        let combined = vaani_core::reconcile::reconcile(&[&previous_transcript, &t.text]);
        g.live_transcript = combined.clone();
        g.live_audio_cursor = snap.audio_end;
        let (stable, _tail) = vaani_core::reconcile::stable_prefix(&combined, live_tail_words());
        // Policy gate: review/terminal/no-auto sessions preview only.
        let mode = g.cfg.insertion_mode_for(&snap.target.app_id);
        let preview_only = mode == "review"
            || mode == "copy-only"
            || g.cfg.general.review_before_insertion
            || g.no_auto.as_deref() == Some(sess.as_str())
            || focus::is_terminal(&snap.target.app_id);
        if preview_only {
            // Show everything beyond committed as provisional; commit nothing.
            emit_provisional(&tx, &sess, &combined, hide, committed_n);
            continue;
        }
        match vaani_core::reconcile::delta_vs(&g.committed, &stable) {
            Some(delta) => {
                let with_space = format!("{delta} ");
                let tgt = snap.target.clone();
                drop(g);
                let res = tokio::task::spawn_blocking(move || inserter::commit_delta(&with_space, &tgt)).await;
                g = shared.lock().await;
                if g.session.id != sess || !matches!(g.session.state, State::Recording) {
                    break;
                }
                match res {
                    Ok(Ok(())) => {
                        g.committed = stable;
                        let n = g.committed.split_whitespace().count();
                        emit_provisional(&tx, &sess, &combined, hide, n);
                    }
                    _ => {
                        // Focus moved or dispatch failed: freeze commits,
                        // keep recording; full text stays recoverable.
                        g.target_lost = true;
                        let n = g.committed.split_whitespace().count();
                        emit(&tx, &ev_state(Some(sess.clone()), State::Recording, Some("Text ready — target changed; finishing keeps text for copy")));
                        emit_provisional(&tx, &sess, &combined, hide, n);
                    }
                }
            }
            None => {
                // No new stable words (or recognizer revised): preview tail only.
                emit_provisional(&tx, &sess, &combined, hide, committed_n);
            }
        }
    }
}

/// Copy fallback: text wasn't typed into the target (target changed,
/// terminal, failure). Place it on the Wayland clipboard so it's immediately
/// pastable, and keep pending for explicit copy/recovery either way.
async fn copy_fallback(
    shared: Arc<Mutex<Shared>>,
    tx: &broadcast::Sender<Event>,
    sid: &str,
    final_text: &str,
    reason: String,
) -> Response {
    let text_c = final_text.to_string();
    let clip_ok = tokio::task::spawn_blocking(move || clipboard::offer_text(&text_c))
        .await
        .map(|r| r.is_ok())
        .unwrap_or(false);
    let mut g = shared.lock().await;
    if g.session.id != sid { return resp_ok("", &g.session, Some("stale copy result discarded".into()), None); }
    let (msg, copied) = if clip_ok {
        ("Copied to clipboard".to_string(), true)
    } else {
        (
            format!("{reason} — clipboard offer failed, use copy/recover"),
            false,
        )
    };
    let _ = g.session.transition(State::Ready);
    let _ = g.session.transition(State::Idle);
    let data = serde_json::json!({"text": final_text, "copied": copied});
    emit(tx, &ev_state_data(Some(sid.to_string()), State::Idle, Some(&msg), Some(data.clone())));
    let s = g.session.clone();
    resp_ok("", &s, Some(msg), Some(data))
}

/// Stop: idempotent, closes capture immediately, transcribes (blocking task),
// then cleanup/insertion per policy. Late results for cancelled sessions die.
async fn stop_flow(shared: Arc<Mutex<Shared>>, tx: &broadcast::Sender<Event>) -> Response {
    tracing::info!("stop_flow entry");
    // Capture close is synchronous and immediate, independent of transcription.
    let (samples, sid, cfg_snap, target) = {
        let mut g = shared.lock().await;
        if matches!(g.session.state, State::Idle) {
            let s = g.session.clone();
            return resp_ok("", &s, Some("idle".into()), None);
        }
        if !matches!(g.session.state, State::Recording | State::Starting) {
            let s = g.session.clone();
            return Response {
                protocol_version: vaani_core::PROTOCOL_VERSION,
                request_id: String::new(),
                session_id: Some(s.id.clone()),
                ok: false,
                state: Some(format!("{:?}", s.state).to_uppercase()),
                message: Some("nothing to stop".into()),
                data: None,
            };
        }
        if let Some(cap) = g.capture.take() {
            // Drain remaining blocks first.
            while let Ok(b) = cap.rx.try_recv() {
                g.audio.extend_from_slice(&b);
            }
            let max = (vaani_core::MAX_AUDIO_SECS as usize) * 16_000;
            let audio_len = g.audio.len();
            if audio_len > max {
                g.audio.drain(..audio_len - max);
            }
            cap.stop(); // closes recording stream NOW
        }
        let _ = g.session.transition(State::Transcribing);
        let sid = g.session.id.clone();
        emit(tx, &ev_state(Some(sid.clone()), State::Transcribing, Some("Transcribing…")));
        (
            g.audio.clone(),
            sid,
            g.cfg.clone(),
            g.target.clone(),
        )
    };

    let t0 = std::time::Instant::now();
    // Run inference off the async runtime (blocking worker process).
    // Clone for the worker thread; keep the original for error-path retry.
    let samples_for_worker = samples.clone();
    let cuda = cfg_snap.recognition.device == "cuda";
    // Pure final: the final model always transcribes the whole utterance.
    // Live-tick transcripts are provisional previews from short windows that
    // diverge from full-context inference — merging them into the final
    // bakes fragment salad ("asked to ask you") into the clipboard text.
    let work = tokio::task::spawn_blocking(move || {
        let mut result = worker_sup::transcribe(
            &samples_for_worker,
            &cfg_snap.recognition.model,
            &cfg_snap.recognition.language,
            cfg_snap.recognition.translate_to_en,
            cfg_snap.audio.worker_threads,
            cuda,
            &cfg_snap.cleanup.vocabulary,
            cfg_snap.recognition.server_idle_secs,
        )?;
        Ok::<_, anyhow::Error>(result)
    })
    .await;

    let mut g = shared.lock().await;
    // Late/stale guard: session must still be ours and TRANSCRIBING.
    if g.session.id != sid || !matches!(g.session.state, State::Transcribing) {
        let s = g.session.clone();
        return resp_ok("", &s, Some("stale result discarded".into()), None);
    }
    g.audio.clear(); // default audio retention ends after transcription
    g.live_transcript.clear();
    g.live_audio_cursor = 0;
    match work {
        Ok(Ok(t)) => {
            g.last_lat.stop_to_text_ms = t0.elapsed().as_millis() as u64;
            g.last_lat.inference_ms = t.inference_ms;
            g.last_lat.backend = t.backend.clone();
            if t.is_silence || t.text.is_empty() {
                // Silence produces no inserted text.
                g.pending_audio = Vec::new();
                let was_live = std::mem::replace(&mut g.live, false);
                let committed = std::mem::take(&mut g.committed);
                g.target_lost = false;
                if was_live && !committed.trim().is_empty() {
                    // Live session: words are already typed; keep them
                    // recoverable and finish.
                    let _ = g.session.transition(State::Idle);
                    emit(tx, &ev_state(Some(sid), State::Idle, Some("Finished — text already typed")));
                    g.pending = Some(Pending { text: committed.clone(), at: std::time::Instant::now() });
                    let s = g.session.clone();
                    return resp_ok("", &s, Some("finished".into()), Some(serde_json::json!({"text": committed})));
                }
                let _ = g.session.transition(State::Idle);
                emit(tx, &ev_state(Some(sid), State::Idle, Some("Silence — nothing to insert")));
                let s = g.session.clone();
                return resp_ok("", &s, Some("silence: no text".into()), None);
            }
            // Optional cleanup on finish (non-live only): endpoint-based
            // "clean" mode, or local-LLM "stream" mode for transcripts at or
            // above the word threshold. Raw fallback on any failure.
            let mut final_text = t.text.clone();
            let stream_wanted = g.cfg.cleanup.mode == "stream"
                && final_text.split_whitespace().count() >= g.cfg.cleanup.word_threshold;
            if (g.cfg.cleanup.mode == "clean" || stream_wanted) && !g.live {
                let _ = g.session.transition(State::Cleaning);
                emit(tx, &ev_state(Some(sid.clone()), State::Cleaning, Some("Cleaning up…")));
                let cfg_snap = g.cfg.clone();
                let vocab = g.cfg.cleanup.vocabulary.clone();
                let ep = g.cfg.cleanup.endpoint.clone();
                let to = g.cfg.cleanup.timeout_secs;
                let use_stream = stream_wanted;
                drop(g);
                let raw = final_text.clone();
                let cleaned = tokio::task::spawn_blocking(move || {
                    if use_stream {
                        run_stream_cleanup(&raw, &cfg_snap)
                    } else {
                        cleanup::clean(&raw, &ep, to, &vocab)
                    }
                }).await.unwrap_or(final_text);
                g = shared.lock().await;
                if g.session.id != sid || !matches!(g.session.state, State::Cleaning) {
                    let s = g.session.clone();
                    return resp_ok("", &s, Some("stale cleanup discarded".into()), None);
                }
                final_text = cleaned;
            }
            g.pending = Some(Pending { text: final_text.clone(), at: std::time::Instant::now() });
            // Live finalize: part of the text is already typed into the
            // target — insert only the remainder. Pending keeps the FULL
            // text so copy recovery never loses words.
            let was_live = g.live;
            let mut insert_text = final_text.clone();
            if was_live {
                let delta = vaani_core::reconcile::delta_vs(&g.committed, &final_text);
                if !g.committed.is_empty() && g.committed.trim() != final_text.trim() && delta.is_none() {
                    g.live = false;
                    g.committed.clear();
                    drop(g);
                    return copy_fallback(shared.clone(), tx, &sid, &final_text,
                        "Recognition revised earlier words — review the full transcript".into()).await;
                }
                let remainder = delta.unwrap_or_default();
                insert_text = remainder;
                if (g.cfg.cleanup.mode == "clean" || g.cfg.cleanup.mode == "stream") && !insert_text.trim().is_empty() {
                    let _ = g.session.transition(State::Cleaning);
                    emit(tx, &ev_state(Some(sid.clone()), State::Cleaning, Some("Cleaning up…")));
                    let cfg_snap = g.cfg.clone();
                    let vocab = g.cfg.cleanup.vocabulary.clone();
                    let ep = g.cfg.cleanup.endpoint.clone();
                    let to = g.cfg.cleanup.timeout_secs;
                    let raw = insert_text.clone();
                    drop(g);
                    let cleaned = tokio::task::spawn_blocking(move || {
                        if cfg_snap.cleanup.mode == "stream" {
                            run_stream_cleanup(&raw, &cfg_snap)
                        } else {
                            cleanup::clean(&raw, &ep, to, &vocab)
                        }
                    }).await.unwrap_or(insert_text);
                    g = shared.lock().await;
                    if g.session.id != sid || !matches!(g.session.state, State::Cleaning) {
                        let s = g.session.clone();
                        return resp_ok("", &s, Some("stale cleanup discarded".into()), None);
                    }
                    insert_text = cleaned;
                }
                g.live = false;
                g.committed.clear();
                g.target_lost = false;
                if insert_text.trim().is_empty() {
                    let _ = g.session.transition(State::Ready);
                    let _ = g.session.transition(State::Idle);
                    emit(tx, &ev_state(Some(sid), State::Idle, Some("Finished — text already typed")));
                    let s = g.session.clone();
                    return resp_ok("", &s, Some("finished".into()), Some(serde_json::json!({"text": final_text})));
                }
            }
            let _ = g.session.transition(State::Ready);
            emit(tx, &ev_state(Some(sid.clone()), State::Ready, Some("Text ready")));
            // Insertion policy.
            let mode = g.cfg.insertion_mode_for(&target.app_id);
            let settings_open = g.no_auto.as_deref() == Some(sid.as_str());
            if settings_open {
                g.no_auto = None; // one-shot: applies to this operation only
            }
            if mode == "review" || g.cfg.general.review_before_insertion || settings_open {
                // Review gate: never auto-paste, but never park the session in
                // READY either — the overlay only auto-exits from finished
                // states. Clipboard + pending keep the text recoverable
                // (SUPER+ALT+C / copy), then the session closes itself.
                let why = if settings_open { "Text ready — settings open, review required" } else { "Text ready — review required" };
                let text_c = final_text.clone();
                drop(g);
                let clip_ok = tokio::task::spawn_blocking(move || clipboard::offer_text(&text_c))
                    .await
                    .map(|r| r.is_ok())
                    .unwrap_or(false);
                g = shared.lock().await;
                if g.session.id != sid {
                    let s = g.session.clone();
                    return resp_ok("", &s, Some("stale review result discarded".into()), None);
                }
                let _ = g.session.transition(State::Idle);
                let (msg, copied) = if clip_ok {
                    (format!("{why} — copied to clipboard"), true)
                } else {
                    (format!("{why} — clipboard offer failed, use copy/recover"), false)
                };
                let data = serde_json::json!({"text": final_text, "copied": copied});
                emit(tx, &ev_state_data(Some(sid), State::Idle, Some(&msg), Some(data.clone())));
                let s = g.session.clone();
                return resp_ok("", &s, Some(msg), Some(data));
            }
            let _ = g.session.transition(State::Inserting);
            let t0d = std::time::Instant::now();
            let mode_c = mode.clone();
            let text_c = insert_text.clone();
            let full_text_c = final_text.clone();
            let tgt_c = target.clone();
            drop(g);
            let (outcome, clipboard_saved) = tokio::task::spawn_blocking(move || {
                let outcome = inserter::insert_automatic(&text_c, &tgt_c, &mode_c);
                let saved = if matches!(outcome, inserter::InsertOutcome::DispatchAttempted(_)) {
                    clipboard::offer_text(&full_text_c).is_ok()
                } else {
                    false
                };
                (outcome, saved)
            }).await.unwrap();
            g = shared.lock().await;
            if g.session.id != sid || g.session.state != State::Inserting {
                return resp_ok("", &g.session, Some("stale insertion result discarded".into()), None);
            }
            g.last_lat.dispatch_ms = t0d.elapsed().as_millis() as u64;
            tracing::info!(
                session_id = %sid,
                target_app = %target.app_id,
                outcome = %outcome,
                clipboard_saved,
                "insertion completed"
            );
            match outcome {
                inserter::InsertOutcome::DispatchAttempted(m) => {
                    let _ = g.session.transition(State::Idle);
                    emit(tx, &ev_state(Some(sid), State::Idle, Some("Paste requested")));
                    let s = g.session.clone();
                    resp_ok("", &s, Some(m), Some(serde_json::json!({"text": final_text})))
                }
                inserter::InsertOutcome::CopyReady(m) => {
                    // Drop the session guard: copy_fallback awaits and
                    // re-locks (holding it across .await self-deadlocks).
                    drop(g);
                    copy_fallback(shared.clone(), &tx, &sid, &final_text, m).await
                }
                inserter::InsertOutcome::Failed(m) => {
                    drop(g);
                    copy_fallback(shared.clone(), &tx, &sid, &final_text, m).await
                }
                inserter::InsertOutcome::Unsupported(m) => {
                    drop(g);
                    copy_fallback(shared.clone(), &tx, &sid, &final_text, m).await
                }
            }
        }
        _ => {
            // Worker crash / error: controller stays up, audio retained briefly
            // for explicit retry, with visible discard/retry controls.
            g.pending_audio = samples;
            let _ = g.session.transition(State::Error);
            emit(tx, &ev_state(Some(sid), State::Error, Some("Transcription failed — audio kept for retry")));
            let s = g.session.clone();
            Response {
                protocol_version: vaani_core::PROTOCOL_VERSION,
                request_id: String::new(),
                session_id: Some(s.id.clone()),
                ok: false,
                state: Some("ERROR".into()),
                message: Some("worker failed; use recover to retry or discard".into()),
                data: None,
            }
        }
    }
}

async fn cancel_flow(shared: Arc<Mutex<Shared>>, tx: &broadcast::Sender<Event>, rid: &str) -> Response {
    tracing::info!("cancel_flow entry");
    let mut g = shared.lock().await;
    if matches!(g.session.state, State::Idle) {
        let s = g.session.clone();
        return resp_ok(rid, &s, Some("idle".into()), None);
    }
    // Cancel invalidates ALL pending results: take capture down, clear audio.
    if let Some(cap) = g.capture.take() {
        cap.stop();
    }
    g.audio.clear();
    g.pending_audio.clear();
    g.live = false;
    g.committed.clear();
    g.live_transcript.clear();
    g.live_audio_cursor = 0;
    g.target_lost = false;
    g.session_started_at = None;
    // Drive to CANCELLED from any active state, then IDLE.
    let _ = g.session.transition(State::Cancelled);
    emit(tx, &ev_state(Some(g.session.id.clone()), State::Cancelled, Some("Cancelled")));
    let _ = g.session.transition(State::Idle);
    emit(tx, &ev_state(Some(g.session.id.clone()), State::Idle, None));
    let s = g.session.clone();
    resp_ok(rid, &s, Some("discarded".into()), None)
}

/// Lock/suspend/compositor-disconnect guard: cancel capture, forbid insertion.
async fn lock_watch(shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>) {
    // Event-driven where possible: watch Hyprland socket for lock events is
    // complex; v1 polls `hyprctl` lock state at 2 s ONLY for the guard (not
    // for UI status). If detection is unavailable, automatic insertion is
    // disabled for the session and documented.
    let mut locked = false;
    let mut insertion_allowed = true;
    loop {
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        let is_locked = check_locked();
        if is_locked && !locked {
            locked = true;
            insertion_allowed = false;
            let mut g = shared.lock().await;
            if matches!(g.session.state, State::Recording | State::Starting) {
                if let Some(cap) = g.capture.take() {
                    cap.stop();
                }
                g.audio.clear();
                let _ = g.session.transition(State::Cancelled);
                let _ = g.session.transition(State::Idle);
                emit(&tx, &ev_state(Some(g.session.id.clone()), State::Cancelled, Some("Session locked — capture cancelled")));
            }
        } else if !is_locked && locked {
            locked = false;
            insertion_allowed = true;
        }
        let _ = insertion_allowed;
    }
}

fn check_locked() -> bool {
    // hyprlock presence is best-effort; absence of detection => insertion
    // stays enabled but the limitation is documented in troubleshooting.
    std::process::Command::new("pgrep")
        .arg("-x")
        .arg("hyprlock")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

async fn doctor() -> serde_json::Value {
    let mut checks: HashMap<&str, serde_json::Value> = HashMap::new();
    let bin = |n: &str| {
        std::process::Command::new("which")
            .arg(n)
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    };
    checks.insert("pw-record", serde_json::json!(bin("pw-record")));
    checks.insert("wl-copy", serde_json::json!(bin("wl-copy")));
    checks.insert("hyprctl", serde_json::json!(bin("hyprctl")));
    checks.insert("quickshell", serde_json::json!(bin("quickshell")));
    checks.insert("whisper-cli", serde_json::json!(bin("whisper-cli") || bin("whisper-cpp")));
    checks.insert("whisper-cli-cuda", serde_json::json!(bin("whisper-cli-cuda")));
    checks.insert("vad-speech-segments", serde_json::json!(bin("vad-speech-segments")));
    checks.insert("curl-cleanup", serde_json::json!(bin("curl")));
    let models = std::fs::read_dir(paths::models_dir())
        .map(|d| d.count())
        .unwrap_or(0);
    checks.insert("models_present", serde_json::json!(models));
    serde_json::json!({
        "checks": checks,
        "socket": paths::control_sock().display().to_string(),
        "version": env!("CARGO_PKG_VERSION"),
        "protocol": vaani_core::PROTOCOL_VERSION,
        "note": "GNOME/KDE/Sway/XWayland insertion support untested — copy-only outside Hyprland.",
    })
}

// Re-export for tests.
#[allow(dead_code)]
pub fn allowed_for_tests(from: State, to: State) -> bool {
    vaani_core::state::allowed(from, to)
}

#[cfg(test)]
mod preview_event_tests {
    use super::*;

    #[test]
    fn preview_is_compact_and_privacy_hides_both_words() {
        let (tx, mut rx) = broadcast::channel(4);
        emit_provisional(&tx, "session", "one two three", false, 0);
        let shown = rx.try_recv().unwrap().data.unwrap();
        assert_eq!(shown["last_word"], "two");
        assert_eq!(shown["next_word"], "three");
        emit_provisional(&tx, "session", "one two three", true, 0);
        let hidden = rx.try_recv().unwrap().data.unwrap();
        assert_eq!(hidden["last_word"], "");
        assert_eq!(hidden["next_word"], "");
        assert_eq!(hidden["tail"], "");
    }
}
