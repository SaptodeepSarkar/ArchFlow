//! Energy-based VAD for 16 kHz float32 mono, 20 ms blocks.
//! Heuristic activity score only — never presented as calibrated confidence.

/// 20 ms at 16 kHz = 320 samples.
pub const BLOCK_SAMPLES: usize = 320;

/// Simple VAD: RMS + zero-crossing gate with hangover.
pub struct Vad {
    /// RMS threshold for speech.
    pub rms_thresh: f32,
    /// hangover blocks to keep speech active after energy drops.
    pub hangover: u32,
    hang: u32,
    pub speech_blocks: u64,
    pub total_blocks: u64,
}

impl Default for Vad {
    fn default() -> Self {
        Self {
            // Quiet laptop microphones need a sensitive gate; Whisper's own
            // VAD remains the second-stage false-positive gate, and auto-stop
            // requires speech_seen so a low threshold can't end sessions early.
            rms_thresh: 0.003,
            hangover: 15, // 300 ms
            hang: 0,
            speech_blocks: 0,
            total_blocks: 0,
        }
    }
}

impl Vad {
    /// Returns true if this block counts as speech (including hangover).
    pub fn push_block(&mut self, block: &[f32]) -> bool {
        assert_eq!(block.len(), BLOCK_SAMPLES);
        self.total_blocks += 1;
        let mut sum = 0.0f32;
        let mut zc = 0u32;
        let mut prev = block[0];
        for &x in block.iter() {
            sum += x * x;
            if (prev >= 0.0) != (x >= 0.0) {
                zc += 1;
            }
            prev = x;
        }
        let rms = (sum / block.len() as f32).sqrt();
        // Very high zero-crossing with low RMS is likely noise; require energy.
        let active = rms >= self.rms_thresh && zc < 200;
        if active {
            self.hang = self.hangover;
            self.speech_blocks += 1;
            true
        } else if self.hang > 0 {
            self.hang -= 1;
            self.speech_blocks += 1;
            true
        } else {
            false
        }
    }

    /// After the utterance: true if essentially silence (no inserted text).
    pub fn is_silence(&self) -> bool {
        if self.total_blocks == 0 {
            return true;
        }
        // Fewer than 5% speech blocks -> silence.
        self.speech_blocks * 20 < self.total_blocks
    }
}

impl crate::engine::VadEngine for Vad {
    fn engine_id(&self) -> &str {
        "energy-zcr"
    }

    fn push_block(&mut self, block: &[f32]) -> Result<bool, crate::engine::EngineError> {
        if block.len() != BLOCK_SAMPLES {
            return Err(crate::engine::EngineError::new(
                crate::engine::EngineErrorKind::InvalidInput,
                format!("VAD block must contain {BLOCK_SAMPLES} samples"),
            ));
        }
        Ok(Vad::push_block(self, block))
    }

    fn is_silence(&self) -> bool {
        Vad::is_silence(self)
    }

    fn reset(&mut self) {
        self.hang = 0;
        self.speech_blocks = 0;
        self.total_blocks = 0;
    }
}

/// Peak-normalised amplitude 0..1 for the overlay waveform (per block).
pub fn block_amplitude(block: &[f32]) -> f32 {
    let mut peak: f32 = 0.0;
    for &x in block {
        peak = peak.max(x.abs());
    }
    peak.clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn silence_is_silence() {
        let mut v = Vad::default();
        let z = vec![0.0f32; BLOCK_SAMPLES];
        for _ in 0..50 {
            v.push_block(&z);
        }
        assert!(v.is_silence());
    }

    #[test]
    fn tone_is_speech() {
        let mut v = Vad::default();
        for i in 0..50 {
            let b: Vec<f32> = (0..BLOCK_SAMPLES)
                .map(|n| 0.2 * ((i * BLOCK_SAMPLES + n) as f32 * 0.1).sin())
                .collect();
            v.push_block(&b);
        }
        assert!(!v.is_silence());
    }

    #[test]
    fn quiet_voice_level_is_not_discarded() {
        let mut v = Vad::default();
        for i in 0..50 {
            let b: Vec<f32> = (0..BLOCK_SAMPLES)
                .map(|n| 0.008 * ((i * BLOCK_SAMPLES + n) as f32 * 0.08).sin())
                .collect();
            v.push_block(&b);
        }
        assert!(!v.is_silence());
    }

    #[test]
    fn very_quiet_voice_level_is_not_discarded() {
        // 0.005 amplitude sine: RMS ~0.0035, just above the 0.003 gate.
        let mut v = Vad::default();
        for i in 0..50 {
            let b: Vec<f32> = (0..BLOCK_SAMPLES)
                .map(|n| 0.005 * ((i * BLOCK_SAMPLES + n) as f32 * 0.08).sin())
                .collect();
            v.push_block(&b);
        }
        assert!(!v.is_silence());
    }

    #[test]
    fn adapter_rejects_unbounded_block_shape() {
        use crate::engine::VadEngine;
        let mut v = Vad::default();
        let error = VadEngine::push_block(&mut v, &[0.0; BLOCK_SAMPLES - 1]).unwrap_err();
        assert_eq!(error.kind, crate::engine::EngineErrorKind::InvalidInput);
        assert_eq!(v.engine_id(), "energy-zcr");
    }
}
