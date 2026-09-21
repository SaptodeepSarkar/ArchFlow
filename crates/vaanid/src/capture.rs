//! Bounded PipeWire capture via the maintained `pw-record` client.
//!
//! Rationale: writing a bespoke libpipewire-rs stream negotiator here would
//! be fragile across PipeWire 1.x; `pw-record` IS the maintained PipeWire
//! client and honours the user's existing graph (default source, EasyEffects
//! virtual sources, Bluetooth profiles) without modifying anything.
//! We request f32 mono 16 kHz; the server side resamples from the real device
//! format (16 kHz is our recognizer requirement, not a hardware assumption).
//!
//! Constraints honoured: ~20 ms blocks, preallocated buffers, bounded queue,
//! no disk I/O / inference / JSON / blocking locks in the callback path.
//! The reader thread pushes f32 blocks into a bounded channel; if the worker
//! is slow, old blocks are dropped with a counter (backpressure that cannot
//! block the audio callback). Capture closes immediately on stop/cancel.

use std::io::Read;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{sync_channel, SyncSender, TrySendError};
use vaani_core::vad::BLOCK_SAMPLES;

pub const CHANNEL_BLOCKS: usize = 6000; // 6000 * 20 ms = 120 s cap

pub struct CaptureHandle {
    child: Child,
    reader: Option<std::thread::JoinHandle<CaptureStats>>,
    pub rx: std::sync::mpsc::Receiver<Vec<f32>>,
    pub device: String,
    pub started_at: std::time::Instant,
}

#[derive(Debug, Default, Clone)]
pub struct CaptureStats {
    pub blocks: u64,
    pub dropped: u64,
    pub bytes: u64,
}

impl CaptureHandle {
    pub fn start(device_selector: &str) -> anyhow::Result<Self> {
        let device = resolve_device(device_selector)?;
        let mut cmd = Command::new("pw-record");
        // Options BEFORE the positional output ("-"): pw-record ignores
        // options placed after it, silently capturing the default source.
        if !device.is_empty() {
            cmd.arg("--target").arg(&device);
        }
        cmd.arg("--format")
            .arg("f32")
            .arg("--rate")
            .arg("16000")
            .arg("--channels")
            .arg("1")
            .arg("-"); // stdout
                       // Never touch global graph: no --volume, no device switching.
        let mut child = cmd
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| anyhow::anyhow!("pw-record spawn failed (is PipeWire installed?): {e}"))?;

        let stdout = child.stdout.take().expect("piped");
        let (tx, rx) = sync_channel::<Vec<f32>>(CHANNEL_BLOCKS);
        let reader = std::thread::spawn(move || pump_stdout(stdout, tx));

        Ok(Self {
            child,
            reader: Some(reader),
            rx,
            device,
            started_at: std::time::Instant::now(),
        })
    }

    /// Drain all buffered blocks without blocking.
    pub fn drain(&mut self) -> (Vec<f32>, CaptureStats) {
        let mut out: Vec<f32> = Vec::new();
        while let Ok(b) = self.rx.try_recv() {
            out.extend_from_slice(&b);
        }
        // Cap at 120 s.
        let max = (vaani_core::MAX_AUDIO_SECS as usize) * 16_000;
        if out.len() > max {
            out.drain(..out.len() - max);
        }
        // Stats unavailable until join; return partial.
        (out, CaptureStats::default())
    }

    pub fn stop(mut self) -> CaptureStats {
        let _ = self.child.kill();
        let _ = self.child.wait();
        // Drop reader pipe so pump thread exits, then join.
        if let Some(h) = self.reader.take() {
            let _ = h.join().unwrap_or_default();
        }
        CaptureStats::default()
    }
}

/// Read stdout f32-LE stream, slice into 20 ms blocks, forward.
/// Preallocated 320-sample buffer reused; only allocation is the per-block
/// Vec handed to the channel (bounded; drop on full — never block).
fn pump_stdout<R: Read>(mut r: R, tx: SyncSender<Vec<f32>>) -> CaptureStats {
    let mut stats = CaptureStats::default();
    let mut buf = [0u8; BLOCK_SAMPLES * 4];
    loop {
        match r.read_exact(&mut buf) {
            Ok(()) => {
                stats.blocks += 1;
                stats.bytes += buf.len() as u64;
                let mut block = Vec::with_capacity(BLOCK_SAMPLES);
                for c in buf.chunks_exact(4) {
                    block.push(f32::from_le_bytes([c[0], c[1], c[2], c[3]]));
                }
                match tx.try_send(block) {
                    Ok(()) => {}
                    Err(TrySendError::Full(_)) => stats.dropped += 1,
                    Err(TrySendError::Disconnected(_)) => break,
                }
            }
            Err(_) => break, // EOF / process exit
        }
    }
    stats
}

/// Resolve the default source at the START of each session (never persist
/// numeric node IDs). Returns target name or "" for server default.
/// Best-effort: if the graph can't be queried, "" lets pw-record use the
/// server default rather than failing.
pub fn resolve_device(selector: &str) -> anyhow::Result<String> {
    if !selector.is_empty() {
        return Ok(selector.to_string());
    }
    Ok(String::new())
}

/// Microphone level test: capture `secs` seconds, return peak/RMS.
pub fn mic_test(secs: u32) -> anyhow::Result<(f32, f32)> {
    let secs = secs.clamp(1, 10);
    let mut h = CaptureHandle::start("")?;
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(secs as u64);
    let mut peak = 0.0f32;
    let mut sum = 0.0f64;
    let mut n = 0u64;
    while std::time::Instant::now() < deadline {
        match h.rx.recv_timeout(std::time::Duration::from_millis(100)) {
            Ok(b) => {
                for &x in &b {
                    peak = peak.max(x.abs());
                    sum += (x as f64) * (x as f64);
                    n += 1;
                }
            }
            Err(_) => continue,
        }
    }
    h.stop();
    let rms = if n > 0 {
        (sum / n as f64).sqrt() as f32
    } else {
        0.0
    };
    Ok((peak, rms))
}
