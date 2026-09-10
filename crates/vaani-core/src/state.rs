//! Dictation lifecycle state machine. Only the controller may transition.

use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "UPPERCASE")]
pub enum State {
    Idle,
    Starting,
    Recording,
    Transcribing,
    Cleaning,
    Ready,
    Inserting,
    Cancelled,
    Error,
}

#[derive(Debug, Error, PartialEq)]
pub enum TransitionError {
    #[error("invalid transition {from:?} -> {to:?}")]
    Invalid { from: State, to: State },
}

pub fn allowed(from: State, to: State) -> bool {
    use State::*;
    matches!(
        (from, to),
        (Idle, Starting)
            | (Starting, Recording)
            | (Starting, Cancelled)
            | (Starting, Error)
            | (Recording, Transcribing)
            | (Recording, Cancelled)
            | (Recording, Error)
            | (Transcribing, Cleaning)
            | (Transcribing, Ready)
            | (Transcribing, Idle) // silence short-circuit: nothing to insert
            | (Transcribing, Cancelled)
            | (Transcribing, Error)
            | (Cleaning, Ready)
            | (Cleaning, Cancelled)
            | (Cleaning, Error)
            | (Ready, Inserting)
            | (Ready, Idle)
            | (Ready, Cancelled)
            | (Inserting, Idle)
            | (Inserting, Ready)
            | (Inserting, Error)
            | (Cancelled, Idle)
            | (Error, Idle)
            // stop is idempotent: recording->transcribing etc. covered; allow
            // repeated stop signals to stay:
            | (Transcribing, Transcribing)
    )
}

#[derive(Debug, Clone)]
pub struct Session {
    pub id: String,
    pub state: State,
    /// increments on each new session; stale worker results carry old id
    pub seq: u64,
}

impl Session {
    pub fn new(seq: u64) -> Self {
        Self {
            id: uuid::Uuid::new_v4().to_string(),
            state: State::Idle,
            seq,
        }
    }

    pub fn transition(&mut self, to: State) -> Result<(), TransitionError> {
        // Idle->Idle is a no-op (duplicate commands must not duplicate insertion).
        if self.state == State::Idle && to == State::Idle {
            return Ok(());
        }
        if allowed(self.state, to) {
            self.state = to;
            Ok(())
        } else {
            Err(TransitionError::Invalid {
                from: self.state,
                to,
            })
        }
    }

    /// Late worker results for cancelled/previous sessions are discarded.
    pub fn accepts_result(&self, result_session: &str) -> bool {
        self.id == result_session
            && matches!(
                self.state,
                State::Transcribing | State::Cleaning | State::Recording
            )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn happy_path() {
        let mut s = Session::new(1);
        for next in [
            State::Starting,
            State::Recording,
            State::Transcribing,
            State::Ready,
            State::Inserting,
            State::Idle,
        ] {
            s.transition(next).unwrap();
        }
    }

    #[test]
    fn rejects_queue_while_busy() {
        // While transcribing, a new recording must be rejected, not queued.
        let mut s = Session::new(1);
        s.transition(State::Starting).unwrap();
        s.transition(State::Recording).unwrap();
        s.transition(State::Transcribing).unwrap();
        assert!(s.transition(State::Recording).is_err());
    }

    #[test]
    fn stale_results_discarded() {
        let s = Session::new(1);
        assert!(!s.accepts_result("other-id"));
        let mut s2 = Session::new(2);
        s2.transition(State::Starting).unwrap();
        s2.transition(State::Cancelled).unwrap();
        s2.transition(State::Idle).unwrap();
        assert!(!s2.accepts_result(&s2.id.clone()));
    }

    #[test]
    fn cancel_paths() {
        for from in [State::Starting, State::Recording, State::Transcribing] {
            let mut s = Session::new(1);
            // drive to `from`
            let path: Vec<State> = match from {
                State::Starting => vec![State::Starting],
                State::Recording => vec![State::Starting, State::Recording],
                _ => vec![State::Starting, State::Recording, State::Transcribing],
            };
            for st in path {
                s.transition(st).unwrap();
            }
            s.transition(State::Cancelled).unwrap();
            s.transition(State::Idle).unwrap();
        }
    }
}
