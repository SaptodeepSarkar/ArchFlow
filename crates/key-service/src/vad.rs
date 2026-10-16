//! End-of-speech detection, so the user never presses the hotkey twice.
//!
//! The microphone here sits behind a PipeWire noise-suppression chain with a
//! hot floor (ambient RMS ≈ 0.18 of full scale), which makes level-based
//! detection either fire on room tone or never clear the bar. The recognizer
//! is the better signal: across every silent run its output stayed empty,
//! while speech produces words. So "speech" means *the decoder produced
//! something*, and the run ends when that output stops changing.
//!
//! Rules:
//!   * any decoder output (a final word or a changed partial) = activity
//!   * once activity has been seen, end after [`SILENCE_MS`] without any
//!   * end after [`NO_SPEECH_MS`] with no activity at all (nothing was said,
//!     so nothing is typed)
//!
//! Pure logic: the timing rules are unit-testable without a microphone.

/// Quiet time after speech that ends the run.
const SILENCE_MS: u32 = 900;
/// Give up if the decoder never produces anything.
const NO_SPEECH_MS: u32 = 5000;

#[derive(Debug, PartialEq, Eq, Clone, Copy)]
pub enum Decision {
    /// Keep recording.
    Listening,
    /// Stop now. `heard` false means nothing was ever said.
    End { heard: bool },
}

pub struct Vad {
    total_ms: u32,
    idle_ms: u32,
    heard: bool,
}

impl Default for Vad {
    fn default() -> Self {
        Self::new()
    }
}

impl Vad {
    pub fn new() -> Self {
        Self {
            total_ms: 0,
            idle_ms: 0,
            heard: false,
        }
    }

    /// Feed one chunk: `activity` is true when the decoder produced a new
    /// word or changed the partial it is showing.
    pub fn tick(&mut self, chunk_ms: u32, activity: bool) -> Decision {
        self.total_ms = self.total_ms.saturating_add(chunk_ms);
        if activity {
            self.heard = true;
            self.idle_ms = 0;
        } else {
            self.idle_ms = self.idle_ms.saturating_add(chunk_ms);
        }
        if self.heard && self.idle_ms >= SILENCE_MS {
            return Decision::End { heard: true };
        }
        if !self.heard && self.total_ms >= NO_SPEECH_MS {
            return Decision::End { heard: false };
        }
        Decision::Listening
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Feed (chunk_ms, activity) pairs; return the first End decision.
    fn run(chunks: &[(u32, bool)]) -> Option<Decision> {
        let mut v = Vad::new();
        for (ms, activity) in chunks {
            let d = v.tick(*ms, *activity);
            if matches!(d, Decision::End { .. }) {
                return Some(d);
            }
        }
        None
    }

    #[test]
    fn speech_then_quiet_ends_the_run() {
        let mut chunks: Vec<(u32, bool)> = vec![(100, true); 10]; // ~1s of words
        chunks.extend(vec![(100, false); 12]); // then quiet
        assert_eq!(run(&chunks), Some(Decision::End { heard: true }));
    }

    #[test]
    fn silent_room_ends_without_typing() {
        let chunks: Vec<(u32, bool)> = vec![(100, false); 60]; // 6s of nothing
        assert_eq!(run(&chunks), Some(Decision::End { heard: false }));
    }

    #[test]
    fn ongoing_speech_is_not_cut_short() {
        // Activity every chunk: a pause shorter than SILENCE_MS must not end
        // the run mid-sentence.
        let mut chunks: Vec<(u32, bool)> = vec![(100, true); 5];
        chunks.extend(vec![(100, false); 5]); // a 500 ms pause
        chunks.extend(vec![(100, true); 5]);
        chunks.extend(vec![(100, false); 3]);
        assert_eq!(run(&chunks), None, "a half-second pause is not the end");
    }

    #[test]
    fn one_word_then_quiet_still_ends_as_heard() {
        let mut chunks: Vec<(u32, bool)> = vec![(100, true)];
        chunks.extend(vec![(100, false); 10]);
        assert_eq!(run(&chunks), Some(Decision::End { heard: true }));
    }
}
