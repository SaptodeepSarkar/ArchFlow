//! vaani-core: configuration, protocol, state machine, VAD, segmentation.
//! No audio I/O, no model loading, no QML here.

pub mod config;
pub mod engine;
pub mod model;
pub mod personalization;
pub mod protocol;
pub mod reconcile;
pub mod segment;
pub mod state;
pub mod sync;
pub mod sync_crypto;
pub mod transcript;
pub mod vad;

pub const PROTOCOL_VERSION: u32 = 1;
/// Max control message bytes (1 MiB). Audio never goes through control socket.
pub const MAX_CONTROL_BYTES: usize = 1024 * 1024;
/// Max transcript chars retained in memory.
pub const MAX_TRANSCRIPT_CHARS: usize = 32_000;
/// Max session audio: 120 s * 16 kHz float32 mono.
pub const MAX_AUDIO_SECS: u32 = 120;
pub const SAMPLE_RATE: u32 = 16_000;
