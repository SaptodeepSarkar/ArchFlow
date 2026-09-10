//! Bounded speech segmentation with overlap + reconciliation.
//! Long dictation: fixed segments with overlap, never re-infer full buffer per frame.

/// 30 s segments with 2 s overlap at 16 kHz.
pub const SEGMENT_SAMPLES: usize = 16_000 * 30;
pub const OVERLAP_SAMPLES: usize = 16_000 * 2;
pub const MAX_SEGMENTS: usize = 4; // 4 * 30 s = 120 s cap

/// Split samples into overlapping segments.
pub fn segment(samples: &[f32]) -> Vec<(usize, usize)> {
    let mut out = Vec::new();
    if samples.is_empty() {
        return out;
    }
    let mut start = 0usize;
    let mut n = 0;
    while start < samples.len() && n < MAX_SEGMENTS {
        let mut end = (start + SEGMENT_SAMPLES).min(samples.len());
        // Don't emit a tiny trailing shard; merge it into the previous segment.
        if end < samples.len() && samples.len() - end < OVERLAP_SAMPLES {
            end = samples.len();
        }
        out.push((start, end));
        if end == samples.len() {
            break;
        }
        start = end - OVERLAP_SAMPLES;
        n += 1;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn short_is_single() {
        let s = vec![0.0; 16_000 * 5];
        assert_eq!(segment(&s), vec![(0, 16_000 * 5)]);
    }

    #[test]
    fn long_splits_with_overlap() {
        let s = vec![0.0; 16_000 * 65];
        let segs = segment(&s);
        assert!(segs.len() >= 3);
        for w in segs.windows(2) {
            assert_eq!(w[0].1 - w[1].0, OVERLAP_SAMPLES);
        }
    }

    #[test]
    fn cap_at_120s() {
        let s = vec![0.0; 16_000 * 200];
        let segs = segment(&s);
        assert!(segs.len() <= MAX_SEGMENTS);
    }
}
