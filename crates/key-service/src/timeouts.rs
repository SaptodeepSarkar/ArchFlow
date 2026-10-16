// vaani-key-service — Phase 10 (timeouts-offload).
//
// Pure idle-offload decisions under the PRD kill-state model. Given
// `idle_timeout_s` (from vaani.conf via vaani-config) plus per-helper
// busy/killable probes, decide offload vs keep-alive:
//
// - timeout not yet elapsed -> keep alive (nothing due).
// - timeout elapsed + killable + not busy -> offload.
// - timeout elapsed but busy (or not killable) -> keep alive and
//   re-check on the next poll; a busy helper is NEVER killed.
//
// Std-only, no daemon access, no wall clock inside (the caller passes
// `now_s` so tests drive a fake clock). Unit-testable without the daemon.
//
// Wiring: the coordinator declares `mod timeouts;` in main.rs and calls
// `decide`/`due_for_offload` from the idle loop (see hook snippet in the
// Phase 10 report). End-to-end daemon offload is Phase 13/14's job.

/// Decision for one helper at one poll point.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Decision {
    /// Safe to offload now.
    Offload,
    /// Keep alive; re-check on the next poll.
    KeepAlive,
}

/// One helper's observable state at a poll point. `last_activity_s` is the
/// daemon's monotonic clock reading (seconds) of when the helper last did
/// work; `busy`/`killable` are its live kill-state probes.
#[derive(Debug, Clone)]
pub struct Helper {
    pub name: String,
    pub last_activity_s: u64,
    pub busy: bool,
    pub killable: bool,
}

/// Decide for a single helper. `idle_s` = seconds since it last did work.
pub fn decide(idle_timeout_s: u64, idle_s: u64, busy: bool, killable: bool) -> Decision {
    if idle_s < idle_timeout_s {
        return Decision::KeepAlive; // timeout not reached: nothing due
    }
    if busy || !killable {
        return Decision::KeepAlive; // PRD: never kill mid-work; re-check later
    }
    Decision::Offload
}

/// Sweep: names of helpers due for offload at `now_s`, in slice order.
pub fn due_for_offload(idle_timeout_s: u64, now_s: u64, helpers: &[Helper]) -> Vec<String> {
    helpers
        .iter()
        .filter(|h| {
            decide(
                idle_timeout_s,
                now_s.saturating_sub(h.last_activity_s),
                h.busy,
                h.killable,
            ) == Decision::Offload
        })
        .map(|h| h.name.clone())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn helper(name: &str, last_activity_s: u64, busy: bool, killable: bool) -> Helper {
        Helper { name: name.into(), last_activity_s, busy, killable }
    }

    #[test]
    fn before_timeout_everything_stays_alive() {
        assert_eq!(decide(10, 0, false, true), Decision::KeepAlive);
        assert_eq!(decide(10, 9, false, true), Decision::KeepAlive);
    }

    #[test]
    fn killable_idle_past_timeout_offloads() {
        assert_eq!(decide(10, 10, false, true), Decision::Offload);
        assert_eq!(decide(10, 10_000, false, true), Decision::Offload);
    }

    #[test]
    fn busy_past_timeout_stays_alive_never_killed() {
        assert_eq!(decide(10, 10, true, false), Decision::KeepAlive);
        assert_eq!(decide(10, 10_000, true, true), Decision::KeepAlive);
    }

    #[test]
    fn non_killable_idle_past_timeout_stays_alive() {
        assert_eq!(decide(10, 60, false, false), Decision::KeepAlive);
    }

    #[test]
    fn busy_then_idle_transitions_to_offload() {
        // Same helper across two polls: busy at t=20, done and idle at t=21.
        assert_eq!(decide(10, 20, true, false), Decision::KeepAlive);
        assert_eq!(decide(10, 21, false, true), Decision::Offload);
    }

    #[test]
    fn zero_timeout_offloads_idle_immediately() {
        assert_eq!(decide(0, 0, false, true), Decision::Offload);
        assert_eq!(decide(0, 0, true, false), Decision::KeepAlive);
    }

    #[test]
    fn sweep_returns_only_due_helpers_in_order() {
        let hs = vec![
            helper("pill", 0, false, true),   // idle 12s: due
            helper("stt", 5, true, false),    // idle 7s but busy: kept
            helper("llm", 11, false, true),   // idle 1s: not yet due
            helper("audio", 0, false, true),  // idle 12s: due
        ];
        assert_eq!(due_for_offload(10, 12, &hs), vec!["pill".to_string(), "audio".to_string()]);
    }

    #[test]
    fn future_activity_clock_never_panics_nor_offloads() {
        let hs = vec![helper("stt", 999, false, true)];
        assert!(due_for_offload(10, 12, &hs).is_empty()); // saturating_sub -> idle 0
    }
}
