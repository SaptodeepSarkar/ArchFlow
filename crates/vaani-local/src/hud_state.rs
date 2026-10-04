//! HUD state contains no transcript text. Session checks reject stale audio/state events.
use vaani_core::protocol::Event;
#[derive(Default)]
pub struct HudState {
    pub session: Option<String>,
    pub state: String,
    pub copied: bool,
    pub levels: [f32; 5],
}
impl HudState {
    pub fn apply(&mut self, event: &Event) -> bool {
        if let (Some(current), Some(incoming)) = (&self.session, &event.session_id) {
            if current != incoming && event.state.as_deref() != Some("STARTING") {
                return false;
            }
        }
        if event.event == "state" {
            let Some(state) = event.state.as_deref() else {
                return false;
            };
            if !matches!(
                state,
                "IDLE"
                    | "STARTING"
                    | "RECORDING"
                    | "TRANSCRIBING"
                    | "CLEANING"
                    | "READY"
                    | "INSERTING"
                    | "CANCELLED"
                    | "ERROR"
            ) {
                return false;
            }
            if state == "STARTING" || (state == "RECORDING" && self.state != "RECORDING") {
                self.copied = false;
                self.levels = [0.0; 5];
            }
            if event.session_id.is_some() {
                self.session = event.session_id.clone();
            }
            self.state = state.into();
            self.copied |= event
                .data
                .as_ref()
                .is_some_and(|d| d["copied"].as_bool() == Some(true));
            if state != "RECORDING" {
                self.levels = [0.0; 5];
            }
            true
        } else if event.event == "amplitude" && self.state == "RECORDING" {
            let level = event
                .amplitude
                .filter(|v| v.is_finite())
                .unwrap_or(0.0)
                .clamp(0.0, 1.0);
            self.levels.rotate_left(1);
            self.levels[4] = level;
            true
        } else {
            false
        }
    }
    pub fn caption(&self) -> (&str, &str) {
        match self.state.as_str() {
            "STARTING" => ("STARTING MICROPHONE", "Getting ready…"),
            "RECORDING" => ("LISTENING", "Speak naturally…"),
            "TRANSCRIBING" => ("TRANSCRIBING", "Turning speech into words…"),
            "CLEANING" => ("FORMATTING", "Keeping your words intact…"),
            "INSERTING" => ("DELIVERING", "Placing your text…"),
            "READY" => ("TEXT READY", "Review or copy your text."),
            "CANCELLED" => ("CANCELLED", "Dictation cancelled."),
            "ERROR" => ("NEEDS ATTENTION", "Check Vaani’s setup and retry."),
            "IDLE" if self.copied => ("ON YOUR CLIPBOARD", "Copied. Paste when you’re ready."),
            "IDLE" => ("FINISHED", "Dictation finished."),
            _ => ("CONNECTING", "Connecting to Vaani…"),
        }
    }
    pub fn dismissal_ms(&self) -> Option<u64> {
        match self.state.as_str() {
            "IDLE" if self.copied => Some(2200),
            "IDLE" | "CANCELLED" => Some(360),
            "ERROR" => Some(1600),
            _ => None,
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn event(state: Option<&str>, session: &str, amplitude: Option<f32>) -> Event {
        Event {
            protocol_version: 1,
            event: if state.is_some() {
                "state"
            } else {
                "amplitude"
            }
            .into(),
            session_id: Some(session.into()),
            state: state.map(str::to_owned),
            amplitude,
            message: None,
            data: None,
        }
    }
    #[test]
    fn new_session_rejects_stale_completion_and_audio() {
        let mut hud = HudState::default();
        assert!(hud.apply(&event(Some("RECORDING"), "a", None)));
        assert!(hud.apply(&event(Some("STARTING"), "b", None)));
        assert!(!hud.apply(&event(Some("IDLE"), "a", None)));
        assert!(!hud.apply(&event(None, "a", Some(1.0))));
        assert_eq!(hud.state, "STARTING");
    }
    #[test]
    fn recording_bars_use_only_finite_current_audio() {
        let mut hud = HudState::default();
        hud.apply(&event(Some("RECORDING"), "a", None));
        hud.apply(&event(None, "a", Some(0.2)));
        assert_eq!(hud.levels[4], 0.2);
        hud.apply(&event(None, "a", Some(f32::NAN)));
        assert_eq!(hud.levels[4], 0.0);
        hud.apply(&event(Some("TRANSCRIBING"), "a", None));
        assert_eq!(hud.levels, [0.0; 5]);
        assert!(!hud.apply(&event(None, "a", Some(1.0))));
    }
    #[test]
    fn copied_notice_lingers_and_resets_for_next_session() {
        let mut hud = HudState::default();
        let mut finished = event(Some("IDLE"), "a", None);
        finished.data = Some(serde_json::json!({"copied":true}));
        hud.apply(&finished);
        assert_eq!(hud.dismissal_ms(), Some(2200));
        assert_eq!(hud.caption().0, "ON YOUR CLIPBOARD");
        hud.apply(&event(Some("STARTING"), "b", None));
        assert!(!hud.copied);
        assert_eq!(hud.dismissal_ms(), None);
    }
}
