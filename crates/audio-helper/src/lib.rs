//! On-demand default-mic capture over PipeWire.
//!
//! Spawns `pw-record` with stdout piped and drains it into a RAM [`Vec`] only.
//! No file is ever opened for writing in this crate. The stream runs only
//! between [`Recorder::start`] and [`Recorder::stop`]; [`Recorder::is_busy`]
//! is true while recording and [`Recorder::is_killable`] is its inverse
//! (idle and stopped helpers are safe to offload; the idle timeout itself
//! is owned by the key service, Phase 10).

use std::io::Read;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, Receiver};

/// Mono capture rate. STT-grade, keeps RAM use small (~160KB per 5s).
pub const SAMPLE_RATE: u32 = 16_000;
pub const CHANNELS: u32 = 1;
/// Bytes per second of raw s16le mono at [`SAMPLE_RATE`].
pub const BYTES_PER_SEC: usize = (SAMPLE_RATE as usize) * 2;

/// Raw PCM capture held in RAM only.
pub struct AudioCapture {
    /// Little-endian s16 mono samples.
    pub samples: Vec<i16>,
    pub sample_rate: u32,
}

impl AudioCapture {
    /// Recorded duration in seconds.
    pub fn secs(&self) -> f64 {
        self.samples.len() as f64 / self.sample_rate as f64
    }
}

pub struct Recorder {
    child: Option<Child>,
    // Draining thread: without it the 64KB stdout pipe fills after ~2s and
    // stalls pw-record, so the stream is drained continuously into RAM.
    drain: Option<Receiver<Vec<u8>>>,
    stopped_once: bool,
    streaming: bool,
}

impl Recorder {
    pub fn new() -> Self {
        Self {
            child: None,
            drain: None,
            stopped_once: false,
            streaming: false,
        }
    }

    /// Open the default-mic stream. Errors if already recording.
    pub fn start(&mut self) -> std::io::Result<()> {
        self.start_with(false)
    }

    /// Open the mic as a chunk stream for live transcription: PCM arrives as
    /// it is captured instead of one buffer at the end. Read it with
    /// [`Recorder::chunks`]; close with [`Recorder::stop_stream`].
    pub fn start_stream(&mut self) -> std::io::Result<()> {
        self.start_with(true)
    }

    /// Chunk receiver for a stream opened with [`Recorder::start_stream`].
    pub fn chunks(&self) -> Option<&Receiver<Vec<u8>>> {
        self.drain.as_ref()
    }

    fn start_with(&mut self, streaming: bool) -> std::io::Result<()> {
        if self.is_busy() {
            return Err(std::io::Error::new(
                std::io::ErrorKind::AlreadyExists,
                "already recording",
            ));
        }
        let mut child = Command::new("pw-record")
            .args(["--rate", "16000", "--channels", "1", "-"])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .stdin(Stdio::null())
            .spawn()?;
        let mut out = child.stdout.take();
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let Some(o) = out.as_mut() else {
                eprintln!("audio-helper: pw-record gave no stdout pipe");
                return;
            };
            if streaming {
                // ~100ms of 16kHz mono s16 arrives per read: small enough
                // for a live word stream, large enough not to spin.
                let mut buf = [0u8; 3200];
                let mut total = 0usize;
                loop {
                    match o.read(&mut buf) {
                        Ok(0) => break, // normal end: stop_stream killed pw-record
                        Err(e) => {
                            eprintln!("audio-helper: mic stream error after {total} bytes: {e}");
                            break;
                        }
                        Ok(n) => {
                            total += n;
                            if tx.send(buf[..n].to_vec()).is_err() {
                                break;
                            }
                        }
                    }
                }
            } else {
                let mut raw = Vec::new();
                let _ = o.read_to_end(&mut raw);
                let _ = tx.send(raw);
            }
        });
        self.child = Some(child);
        self.drain = Some(rx);
        self.streaming = streaming;
        Ok(())
    }

    /// Close a stream opened with [`Recorder::start_stream`]. Discards the
    /// chunk receiver; callers keep the words they already received.
    pub fn stop_stream(&mut self) {
        self.drain = None;
        if let Some(mut c) = self.child.take() {
            let _ = c.kill();
            let _ = c.wait();
        }
    }

    /// True while the mic stream is open. Helpers reporting busy must not be killed.
    pub fn is_busy(&mut self) -> bool {
        let running = match self.child.as_mut() {
            None => false,
            Some(c) => c.try_wait().map(|s| s.is_none()).unwrap_or(false),
        };
        if !running {
            // Reaped or never started: drop the handle so a stale zombie
            // is never reported busy. Only a live stream counts.
            if self.child.is_some() {
                let _ = self.child.take();
            }
        }
        running
    }

    /// True when safe to offload: never busy. Covers idle and stopped.
    pub fn is_killable(&mut self) -> bool {
        !self.is_busy()
    }

    /// Close the stream and drain stdout into RAM. Errors if not recording.
    pub fn stop(&mut self) -> std::io::Result<AudioCapture> {
        let mut child = match self.child.take() {
            Some(c) => c,
            None => {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::NotConnected,
                    "not recording",
                ))
            }
        };
        // Signal end of stream; the drain thread sees EOF and hands over
        // the RAM buffer (pipe only, never a file).
        let _ = child.kill();
        let _ = child.wait();
        let raw = self
            .drain
            .take()
            .map(|rx| rx.recv().unwrap_or_default())
            .unwrap_or_default();
        self.stopped_once = true;
        // pw-record writes raw s16le to stdout; drop a trailing odd byte.
        let n = raw.len() & !1;
        let samples = raw[..n]
            .chunks_exact(2)
            .map(|b| i16::from_le_bytes([b[0], b[1]]))
            .collect();
        Ok(AudioCapture {
            samples,
            sample_rate: SAMPLE_RATE,
        })
    }
}
