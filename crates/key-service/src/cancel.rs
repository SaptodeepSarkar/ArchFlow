// vaani-key-service — Phase 11 (cancel-error) decision logic.
//
// Pure, std-only, no I/O: maps (phase, signal) -> an ordered action list.
// Every path ends in Idle with zero residents; busy helpers are never
// killed mid-work, they are asked to stop then offloaded once killable
// (the kill-state model from PRD/key-service.md still owns the timing).
//
// Wiring into the daemon is one paste in main.rs (see the Phase 11 report
// hook snippet: `mod cancel;` + cancel-signal branch + error branch).
// This file stays pure so `rustc --test` alone proves the decision table;
// once `mod cancel;` lands, `cargo test -p vaani-key-service` covers it too.

/// Where a run is when the signal arrives.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Phase {
    Idle,
    Listening,    // mic open, audio helper busy
    Transcribing, // STT loaded / working
}

/// What happened. `Trigger` while already running = double-trigger.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Signal {
    Trigger,
    Cancel,
    SttLoadFail,
    LlmLoadFail,
    MicFail,
}

/// What the pill must show as a result of this decision.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pill {
    Hidden, // back to idle, pill off-screen
    Error,  // error state, auto-dismisses back to idle
    Unchanged, // double-trigger: pill keeps showing the live run
}

/// Helper residency after the decision. The table guarantees all-clear.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Residents {
    pub pill: bool,
    pub audio: bool,
    pub stt: bool,
    pub llm: bool,
    pub typing: bool,
}

impl Residents {
    pub const CLEAR: Residents = Residents {
        pill: false,
        audio: false,
        stt: false,
        llm: false,
        typing: false,
    };
    pub fn is_clear(self) -> bool {
        self == Residents::CLEAR
    }
}

/// The ordered offload plan. Action vocabulary (stable; the main.rs hook
/// and gate-11.sh both match on these strings):
/// `kill_audio`, `kill_stt`, `skip_formatting`, `abort_before_stt`,
/// `pill_hide`, `pill_error`, `offload_all`, `idle`, `ignore_trigger`.
#[derive(Debug, PartialEq, Eq)]
pub struct Plan {
    pub actions: Vec<&'static str>,
    pub phase: Phase,
    pub pill: Pill,
    pub residents: Residents,
    pub pipelines: u8, // live pipelines after this decision; never > 1
}

fn idle_clean(pill: Pill, actions: Vec<&'static str>) -> Plan {
    Plan { actions, phase: Phase::Idle, pill, residents: Residents::CLEAR, pipelines: 0 }
}

/// Pure decision table. Every failure/cancel path ends idle with zero
/// residents; a double-trigger is ignored and keeps the single pipeline.
pub fn decide(phase: Phase, signal: Signal) -> Plan {
    match (phase, signal) {
        // Cancel mid-listen: kill audio + STT now, no formatting pass.
        (Phase::Listening, Signal::Cancel) => idle_clean(
            Pill::Hidden,
            vec!["kill_audio", "kill_stt", "skip_formatting", "pill_hide", "offload_all", "idle"],
        ),
        // Cancel mid-transcribe: same, STT first (it holds VRAM), then audio.
        (Phase::Transcribing, Signal::Cancel) => idle_clean(
            Pill::Hidden,
            vec!["kill_stt", "kill_audio", "skip_formatting", "pill_hide", "offload_all", "idle"],
        ),
        // Cancel with nothing running: already idle, nothing to kill.
        (Phase::Idle, Signal::Cancel) => idle_clean(Pill::Hidden, vec!["idle"]),
        // STT fails to load: error state, offload everything, idle.
        (_, Signal::SttLoadFail) => idle_clean(
            Pill::Error,
            vec!["pill_error", "offload_all", "idle"],
        ),
        // LLM fails to load: error state, offload everything, idle.
        (_, Signal::LlmLoadFail) => idle_clean(
            Pill::Error,
            vec!["pill_error", "offload_all", "idle"],
        ),
        // Mic fails: abort before STT loads, error state, idle.
        (_, Signal::MicFail) => idle_clean(
            Pill::Error,
            vec!["abort_before_stt", "pill_error", "offload_all", "idle"],
        ),
        // Double-trigger during a run: ignore, never two pipelines.
        (Phase::Listening, Signal::Trigger) | (Phase::Transcribing, Signal::Trigger) => Plan {
            actions: vec!["ignore_trigger"],
            phase,
            pill: Pill::Unchanged,
            residents: Residents::CLEAR, // nothing newly resident; run owns its helpers
            pipelines: 1,
        },
        // Fresh trigger while idle: a new run may start (not this module's job).
        (Phase::Idle, Signal::Trigger) => Plan {
            actions: vec!["ignore_trigger"],
            phase: Phase::Idle,
            pill: Pill::Unchanged,
            residents: Residents::CLEAR,
            pipelines: 0,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_idle_clean(plan: &Plan) {
        assert_eq!(plan.phase, Phase::Idle, "must end idle: {plan:?}");
        assert!(plan.residents.is_clear(), "zero residents: {plan:?}");
        assert_eq!(plan.pipelines, 0, "no live pipeline: {plan:?}");
        assert_eq!(plan.actions.last(), Some(&"idle"), "last action is idle: {plan:?}");
    }

    #[test]
    fn cancel_mid_listen() {
        let plan = decide(Phase::Listening, Signal::Cancel);
        assert!(plan.actions.contains(&"kill_audio") && plan.actions.contains(&"kill_stt"));
        assert!(plan.actions.contains(&"skip_formatting"), "no formatting pass: {plan:?}");
        assert_eq!(plan.pill, Pill::Hidden);
        assert_idle_clean(&plan);
    }

    #[test]
    fn cancel_mid_transcribe() {
        let plan = decide(Phase::Transcribing, Signal::Cancel);
        // Immediate offload order: STT (holds VRAM) before audio, format skipped.
        let stt = plan.actions.iter().position(|a| *a == "kill_stt").unwrap();
        let audio = plan.actions.iter().position(|a| *a == "kill_audio").unwrap();
        assert!(stt < audio, "stt offloads first: {plan:?}");
        assert!(plan.actions.contains(&"skip_formatting"), "no formatting pass: {plan:?}");
        assert_eq!(plan.pill, Pill::Hidden);
        assert_idle_clean(&plan);
    }

    #[test]
    fn stt_load_fail() {
        for phase in [Phase::Idle, Phase::Listening, Phase::Transcribing] {
            let plan = decide(phase, Signal::SttLoadFail);
            assert_eq!(plan.pill, Pill::Error, "error state shown: {plan:?}");
            assert!(plan.actions.contains(&"offload_all"), "everything offloaded: {plan:?}");
            assert_idle_clean(&plan);
        }
    }

    #[test]
    fn llm_load_fail() {
        for phase in [Phase::Idle, Phase::Listening, Phase::Transcribing] {
            let plan = decide(phase, Signal::LlmLoadFail);
            assert_eq!(plan.pill, Pill::Error, "error state shown: {plan:?}");
            assert!(plan.actions.contains(&"offload_all"), "everything offloaded: {plan:?}");
            assert_idle_clean(&plan);
        }
    }

    #[test]
    fn mic_fail() {
        for phase in [Phase::Idle, Phase::Listening] {
            let plan = decide(phase, Signal::MicFail);
            assert_eq!(plan.pill, Pill::Error, "error state shown: {plan:?}");
            assert!(plan.actions.contains(&"abort_before_stt"), "abort before STT: {plan:?}");
            assert!(plan.actions.contains(&"offload_all"), "everything offloaded: {plan:?}");
            assert_idle_clean(&plan);
        }
    }

    #[test]
    fn double_trigger_ignored_then_idle_clean() {
        // Second trigger mid-run is ignored: same phase, still one pipeline.
        for phase in [Phase::Listening, Phase::Transcribing] {
            let plan = decide(phase, Signal::Trigger);
            assert_eq!(plan.actions, vec!["ignore_trigger"], "ignored: {plan:?}");
            assert_eq!(plan.phase, phase, "run continues: {plan:?}");
            assert!(plan.pipelines <= 1, "never two pipelines: {plan:?}");
        }
        // ...and the surviving run still terminates idle-clean on cancel.
        assert_idle_clean(&decide(Phase::Listening, Signal::Cancel));
        assert_idle_clean(&decide(Phase::Transcribing, Signal::Cancel));
    }
}
