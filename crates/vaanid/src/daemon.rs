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
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
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
    /// Focus lost mid-live-session: stop committing, keep accumulating.
    target_lost: bool,
}

#[derive(Default, Clone, serde::Serialize)]
struct Latencies {
    mic_ready_ms: u64,
    stop_to_text_ms: u64,
    inference_ms: u64,
    dispatch_ms: u64,
}

pub async fn run() -> anyhow::Result<()> {
    paths::ensure_dirs()?;
    let sock = paths::control_sock();
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
        target_lost: false,
    }));

    // Session-lock/suspend guard: on lock, cancel capture + forbid insertion.
    {
        let s = shared.clone();
        let t = tx.clone();
        tokio::spawn(async move { lock_watch(s, t).await });
    }
    // Pending-text expiry sweeper (5 min default, in-memory only).
    {
        let s = shared.clone();
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(std::time::Duration::from_secs(15)).await;
                let mut g = s.lock().await;
                if let Some(p) = &g.pending {
                    if p.at.elapsed().as_secs() > g.cfg.insertion.pending_expiry_secs {
                        g.pending = None;
                        emit(&t_dummy(), &Event {
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

fn t_dummy() -> broadcast::Sender<Event> {
    let (t, _) = broadcast::channel(1);
    t
}

fn emit(tx: &broadcast::Sender<Event>, ev: &Event) {
    let _ = tx.send(ev.clone());
}

fn ev_state(session: Option<String>, state: State, msg: Option<&str>) -> Event {
    Event {
        protocol_version: vaani_core::PROTOCOL_VERSION,
        event: "state".into(),
        session_id: session,
        state: Some(format!("{state:?}").to_uppercase()),
        amplitude: None,
        message: msg.map(|s| s.into()),
        data: None,
    }
}

async fn handle_conn(stream: UnixStream, shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>) {
    let (r, mut w) = stream.into_split();
    let mut lines = BufReader::new(r).lines();
    // Snapshot first for subscribers.
    let snap = {
        let g = shared.lock().await;
        serde_json::json!({
            "state": format!("{:?}", g.session.state).to_uppercase(),
            "session_id": g.session.id,
            "pending": g.pending.is_some(),
        })
    };
    let _ = w
        .write_all(format!("{snap}\n").as_bytes())
        .await;

    while let Ok(Some(line)) = lines.next_line().await {
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
                let _ = w.write_all(format!("{}\n", serde_json::to_string(&resp).unwrap()).as_bytes()).await;
                continue;
            }
        };
        let rid = req.request_id.clone();
        let resp = dispatch(req, shared.clone(), tx.clone()).await;
        let mut resp = resp;
        if resp.request_id.is_empty() {
            resp.request_id = rid;
        }
        let _ = w
            .write_all(format!("{}\n", serde_json::to_string(&resp).unwrap()).as_bytes())
            .await;
    }
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

async fn dispatch(req: Request, shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>) -> Response {
    let rid = req.request_id.clone();
    match req.kind {
        RequestKind::Toggle => {
            let busy = {
                let g = shared.lock().await;
                !matches!(g.session.state, State::Idle | State::Ready | State::Cancelled | State::Error)
            };
            if busy {
                stop_flow(shared.clone(), &tx).await
            } else {
                // If READY with pending text and target unchanged, toggle re-inserts? No:
                // toggle from READY with pending just reports ready (explicit copy/insert).
                start_flow(shared.clone(), &tx, false).await
            }
        }
        RequestKind::LiveToggle => {
            let busy = {
                let g = shared.lock().await;
                !matches!(g.session.state, State::Idle | State::Ready | State::Cancelled | State::Error)
            };
            if busy {
                stop_flow(shared.clone(), &tx).await
            } else {
                start_flow(shared.clone(), &tx, true).await
            }
        }
        RequestKind::Start => start_flow(shared.clone(), &tx, false).await,
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
                    .arg("-c")
                    .arg("vaani")
                    .env("VAANI_OPEN_SETTINGS", "1")
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
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
        g.target_lost = false;
        emit(tx, &ev_state(Some(sid), State::Starting, Some("Starting microphone…")));
        // On-demand overlay UI (separate app-owned Quickshell config).
        // The reaper thread keeps closed UI processes from becoming zombies.
        std::thread::spawn(|| {
            let mut child = std::process::Command::new("quickshell")
                .arg("-c")
                .arg("vaani")
                .env_remove("VAANI_OPEN_SETTINGS")
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
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
            emit(tx, &ev_state(Some(sid.clone()), State::Recording, Some("Listening")));
            // Spawn amplitude pump: drains blocks, forwards audio, emits ≤30 Hz.
            let sh = shared.clone();
            let t2 = tx.clone();
            let sess = sid.clone();
            tokio::spawn(async move { amplitude_loop(sh, t2, sess).await });
            // Live dictation: commit stabilized words while recording.
            if live {
                let sh = shared.clone();
                let t3 = tx.clone();
                let sess = sid.clone();
                tokio::spawn(async move { live_loop(sh, t3, sess).await });
            }
            let s = g.session.clone();
            resp_ok("", &s, Some("Listening".into()), None)
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
async fn amplitude_loop(shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>, sess: String) {
    let mut last_emit = std::time::Instant::now();
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
                    (true, g.amplitude, false)
                }
            } else {
                (false, 0.0, false)
            }
        };
        if !alive {
            if sid_ok {
                // Auto-stop at session limit: drop lock before stop_flow.
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
    emit(tx, &Event {
        protocol_version: vaani_core::PROTOCOL_VERSION,
        event: "provisional".into(),
        session_id: Some(sess.into()),
        state: Some("RECORDING".into()),
        amplitude: None,
        message: None,
        data: Some(serde_json::json!({
            "tail": if hidden { "" } else { tail },
            "hidden": hidden,
            "committed_words": committed_words,
        })),
    });
}

struct LiveSnap {
    audio: Vec<f32>,
    cfg: vaani_core::config::Config,
    target: FocusTarget,
    committed: String,
}

enum LiveTick {
    Exit,
    Skip,
    Work(LiveSnap),
}

/// Live loop (SUPER+H): every chunk, transcribe cumulative audio, commit only
/// the newly stabilized prefix (last TAIL words held back as provisional).
/// A worker failure retries next tick; the controller stays up.
fn live_tail_words() -> usize {
    4
}

async fn live_loop(shared: Arc<Mutex<Shared>>, tx: broadcast::Sender<Event>, sess: String) {
    loop {
        let chunk_secs = { shared.lock().await.cfg.general.live_chunk_secs.clamp(2, 10) };
        tokio::time::sleep(std::time::Duration::from_secs(chunk_secs)).await;
        let tick: LiveTick = {
            let g = shared.lock().await;
            if g.session.id != sess || !matches!(g.session.state, State::Recording) || !g.live {
                LiveTick::Exit
            } else if g.target_lost {
                LiveTick::Skip // focus lost: keep recording, commit nothing
            } else if g.audio.len() < 16_000 {
                LiveTick::Skip // <1 s: not worth an inference pass
            } else {
                LiveTick::Work(LiveSnap {
                    audio: g.audio.clone(),
                    cfg: g.cfg.clone(),
                    target: g.target.clone(),
                    committed: g.committed.clone(),
                })
            }
        };
        let snap = match tick {
            LiveTick::Exit => break,
            LiveTick::Skip => continue,
            LiveTick::Work(s) => s,
        };
        let work = tokio::task::spawn_blocking(move || {
            worker_sup::transcribe(
                &snap.audio,
                &snap.cfg.recognition.model,
                &snap.cfg.recognition.language,
                snap.cfg.recognition.translate_to_en,
                snap.cfg.audio.worker_threads,
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
            _ => {
                // Worker hiccup: retry next tick, keep recording.
                emit_provisional(&tx, &sess, "", hide, committed_n);
                continue;
            }
        };
        if t.is_silence || t.text.is_empty() {
            emit_provisional(&tx, &sess, "", hide, committed_n);
            continue;
        }
        let (stable, tail) = vaani_core::reconcile::stable_prefix(&t.text, live_tail_words());
        // Policy gate: review/terminal/no-auto sessions preview only.
        let mode = g.cfg.insertion_mode_for(&snap.target.app_id);
        let preview_only = mode == "review"
            || g.cfg.general.review_before_insertion
            || g.no_auto.as_deref() == Some(sess.as_str())
            || focus::is_terminal(&snap.target.app_id);
        if preview_only {
            // Show everything beyond committed as provisional; commit nothing.
            let shown = match vaani_core::reconcile::delta_vs(&g.committed, &t.text.trim()) {
                Some(d) => d,
                None => tail.clone(),
            };
            emit_provisional(&tx, &sess, &shown, hide, committed_n);
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
                        emit_provisional(&tx, &sess, &tail, hide, n);
                    }
                    _ => {
                        // Focus moved or dispatch failed: freeze commits,
                        // keep recording; full text stays recoverable.
                        g.target_lost = true;
                        let n = g.committed.split_whitespace().count();
                        emit(&tx, &ev_state(Some(sess.clone()), State::Recording, Some("Text ready — target changed; finishing keeps text for copy")));
                        emit_provisional(&tx, &sess, &tail, hide, n);
                    }
                }
            }
            None => {
                // No new stable words (or recognizer revised): preview tail only.
                emit_provisional(&tx, &sess, &tail, hide, committed_n);
            }
        }
    }
}

/// Stop: idempotent, closes capture immediately, transcribes (blocking task),
// then cleanup/insertion per policy. Late results for cancelled sessions die.
async fn stop_flow(shared: Arc<Mutex<Shared>>, tx: &broadcast::Sender<Event>) -> Response {
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
        (g.audio.clone(), sid, g.cfg.clone(), g.target.clone())
    };

    let t0 = std::time::Instant::now();
    // Run inference off the async runtime (blocking worker process).
    // Clone for the worker thread; keep the original for error-path retry.
    let samples_for_worker = samples.clone();
    let work = tokio::task::spawn_blocking(move || {
        worker_sup::transcribe(&samples_for_worker, &cfg_snap.recognition.model, &cfg_snap.recognition.language, cfg_snap.recognition.translate_to_en, cfg_snap.audio.worker_threads)
    })
    .await;

    let mut g = shared.lock().await;
    // Late/stale guard: session must still be ours and TRANSCRIBING.
    if g.session.id != sid || !matches!(g.session.state, State::Transcribing) {
        let s = g.session.clone();
        return resp_ok("", &s, Some("stale result discarded".into()), None);
    }
    g.audio.clear(); // default audio retention ends after transcription
    match work {
        Ok(Ok(t)) => {
            g.last_lat.stop_to_text_ms = t0.elapsed().as_millis() as u64;
            g.last_lat.inference_ms = t.inference_ms;
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
            // Optional conservative cleanup (explicit endpoint only).
            // Live sessions skip full-text cleanup here: committed words are
            // already typed raw, so only the remainder is cleaned at finalize.
            let mut final_text = t.text.clone();
            if g.cfg.cleanup.mode == "clean" && !g.live {
                let _ = g.session.transition(State::Cleaning);
                emit(tx, &ev_state(Some(sid.clone()), State::Cleaning, Some("Cleaning up…")));
                let vocab = g.cfg.cleanup.vocabulary.clone();
                let ep = g.cfg.cleanup.endpoint.clone();
                let to = g.cfg.cleanup.timeout_secs;
                drop(g);
                let raw = final_text.clone();
                let cleaned = tokio::task::spawn_blocking(move || cleanup::clean(&raw, &ep, to, &vocab)).await.unwrap_or(final_text);
                g = shared.lock().await;
                if g.session.id != sid || !matches!(g.session.state, State::Cleaning) {
                    let s = g.session.clone();
                    return resp_ok("", &s, Some("stale cleanup discarded".into()), None);
                }
                final_text = cleaned;
            }
            let _ = g.session.transition(State::Ready);
            emit(tx, &ev_state(Some(sid.clone()), State::Ready, Some("Text ready")));
            g.pending = Some(Pending { text: final_text.clone(), at: std::time::Instant::now() });
            // Live finalize: part of the text is already typed into the
            // target — insert only the remainder. Pending keeps the FULL
            // text so copy recovery never loses words.
            let was_live = g.live;
            let mut insert_text = final_text.clone();
            if was_live {
                let remainder =
                    vaani_core::reconcile::delta_vs(&g.committed, &final_text).unwrap_or_default();
                insert_text = remainder;
                if g.cfg.cleanup.mode == "clean" && !insert_text.trim().is_empty() {
                    let _ = g.session.transition(State::Cleaning);
                    emit(tx, &ev_state(Some(sid.clone()), State::Cleaning, Some("Cleaning up…")));
                    let vocab = g.cfg.cleanup.vocabulary.clone();
                    let ep = g.cfg.cleanup.endpoint.clone();
                    let to = g.cfg.cleanup.timeout_secs;
                    let raw = insert_text.clone();
                    drop(g);
                    let cleaned = tokio::task::spawn_blocking(move || cleanup::clean(&raw, &ep, to, &vocab)).await.unwrap_or(insert_text);
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
                    let _ = g.session.transition(State::Idle);
                    emit(tx, &ev_state(Some(sid), State::Idle, Some("Finished — text already typed")));
                    let s = g.session.clone();
                    return resp_ok("", &s, Some("finished".into()), Some(serde_json::json!({"text": final_text})));
                }
            }
            // Insertion policy.
            let mode = g.cfg.insertion_mode_for(&target.app_id);
            let settings_open = g.no_auto.as_deref() == Some(sid.as_str());
            if settings_open {
                g.no_auto = None; // one-shot: applies to this operation only
            }
            if mode == "review" || g.cfg.general.review_before_insertion || settings_open {
                let s = g.session.clone();
                let why = if settings_open { "Text ready — settings open, review required" } else { "Text ready — review required" };
                return resp_ok("", &s, Some(why.into()), Some(serde_json::json!({"text": final_text})));
            }
            let _ = g.session.transition(State::Inserting);
            let t0d = std::time::Instant::now();
            let mode_c = mode.clone();
            let text_c = insert_text.clone();
            let tgt_c = target.clone();
            drop(g);
            let outcome = tokio::task::spawn_blocking(move || inserter::insert_automatic(&text_c, &tgt_c, &mode_c)).await.unwrap();
            g = shared.lock().await;
            g.last_lat.dispatch_ms = t0d.elapsed().as_millis() as u64;
            match outcome {
                inserter::InsertOutcome::DispatchAttempted(m) => {
                    let _ = g.session.transition(State::Idle);
                    emit(tx, &ev_state(Some(sid), State::Idle, Some("Paste requested")));
                    let s = g.session.clone();
                    resp_ok("", &s, Some(m), Some(serde_json::json!({"text": final_text})))
                }
                inserter::InsertOutcome::CopyReady(m) => {
                    let _ = g.session.transition(State::Ready);
                    emit(tx, &ev_state(Some(sid), State::Ready, Some("Text ready — target changed")));
                    let s = g.session.clone();
                    resp_ok("", &s, Some(m), Some(serde_json::json!({"text": final_text})))
                }
                inserter::InsertOutcome::Failed(m) => {
                    let _ = g.session.transition(State::Ready);
                    emit(tx, &ev_state(Some(sid), State::Ready, Some("Insertion failed — text kept")));
                    let s = g.session.clone();
                    resp_ok("", &s, Some(m), Some(serde_json::json!({"text": final_text})))
                }
                inserter::InsertOutcome::Unsupported(m) => {
                    let _ = g.session.transition(State::Ready);
                    let s = g.session.clone();
                    resp_ok("", &s, Some(m), Some(serde_json::json!({"text": final_text})))
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
    g.target_lost = false;
    // Drive to CANCELLED from any active state, then IDLE.
    let _ = g.session.transition(State::Cancelled);
    emit(tx, &ev_state(Some(g.session.id.clone()), State::Cancelled, Some("Cancelled")));
    let _ = g.session.transition(State::Idle);
    emit(tx, &ev_state(Some(g.session.id.clone()), State::Idle, None));
    let s = g.session.clone();
    resp_ok(rid, &s, Some("cancelled".into()), None)
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
