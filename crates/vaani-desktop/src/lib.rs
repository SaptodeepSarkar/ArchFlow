//! Portable desktop orchestration.
//!
//! Linux Wayland/X11 and Windows provide different shortcut, focus, overlay,
//! clipboard, and insertion adapters. This crate owns the lifecycle and the
//! safety rule shared by all of them: direct insertion is best effort, then
//! the complete text is copied, and only a confirmed copy failure is reported
//! as unavailable.

use vaani_core::engine::{EngineError, InsertOutcome};

pub mod firebase;
pub mod personalization;
#[cfg(any(unix, windows))]
pub mod platform;
pub use firebase::{
    FirebaseEmailAuth, FirebaseRestProvider, FirebaseSession, FirebaseTokenProvider,
};
pub use personalization::PersonalizationRepository;

/// Local-first desktop account bridge. The repository remains usable before
/// sign-in and the session is held only for the lifetime of this object.
pub struct DesktopSyncClient {
    project_id: String,
    repository: PersonalizationRepository,
    session: Option<FirebaseSession>,
    cursor: Option<String>,
}

impl DesktopSyncClient {
    pub fn new(project_id: impl Into<String>, repository: PersonalizationRepository) -> Self {
        Self {
            project_id: project_id.into(),
            repository,
            session: None,
            cursor: None,
        }
    }

    pub fn repository(&self) -> &PersonalizationRepository {
        &self.repository
    }

    pub fn sign_in(
        &mut self,
        auth: &FirebaseEmailAuth,
        email: &str,
        password: &str,
    ) -> Result<String, EngineError> {
        let session = auth.sign_in(email, password)?;
        let email = session.email().to_owned();
        self.session = Some(session);
        self.cursor = None;
        Ok(email)
    }

    pub fn create_account(
        &mut self,
        auth: &FirebaseEmailAuth,
        email: &str,
        password: &str,
    ) -> Result<String, EngineError> {
        let session = auth.create_account(email, password)?;
        let email = session.email().to_owned();
        self.session = Some(session);
        self.cursor = None;
        Ok(email)
    }

    pub fn sign_out(&mut self) {
        self.session = None;
        self.cursor = None;
    }

    pub fn email(&self) -> Option<&str> {
        self.session.as_ref().map(FirebaseSession::email)
    }

    pub fn sync_once(&mut self) -> Result<vaani_core::sync::SyncCycle, EngineError> {
        let session = self.session.as_ref().ok_or_else(|| {
            EngineError::new(
                vaani_core::engine::EngineErrorKind::Unavailable,
                "sign in to sync personalization",
            )
        })?;
        let provider = FirebaseRestProvider::new(self.project_id.clone(), session);
        self.repository.sync_once(&provider, &mut self.cursor)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Invocation {
    Toggle,
    Start,
    Stop,
    Cancel,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DesktopState {
    Hidden,
    Listening,
    Finishing,
    Delivering,
    Failure,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OverlayModel {
    pub state: DesktopState,
    pub level: u8,
    pub preview: String,
    pub message: String,
}

pub trait OverlayPort: Send + Sync {
    fn render(&self, model: &OverlayModel);
    fn hide(&self);
}

pub trait DirectInserter: Send + Sync {
    fn insert(&self, text: &str) -> Result<InsertOutcome, EngineError>;
}

pub trait ClipboardPort: Send + Sync {
    fn copy(&self, text: &str) -> Result<(), EngineError>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeliveryReport {
    pub outcome: InsertOutcome,
    pub text_preserved: bool,
}

/// Deliver text without allowing platform limitations to discard it.
pub fn deliver<I: DirectInserter, C: ClipboardPort>(
    inserter: &I,
    clipboard: &C,
    text: &str,
) -> DeliveryReport {
    let direct = inserter.insert(text);
    match direct {
        Ok(InsertOutcome::Inserted) => DeliveryReport {
            outcome: InsertOutcome::Inserted,
            text_preserved: true,
        },
        Ok(InsertOutcome::Copied { reason }) => DeliveryReport {
            outcome: InsertOutcome::Copied { reason },
            text_preserved: true,
        },
        Ok(InsertOutcome::Unavailable { reason })
        | Err(EngineError {
            message: reason, ..
        }) => match clipboard.copy(text) {
            Ok(()) => DeliveryReport {
                outcome: InsertOutcome::Copied {
                    reason: format!("direct insertion unavailable: {reason}"),
                },
                text_preserved: true,
            },
            Err(copy_error) => DeliveryReport {
                outcome: InsertOutcome::Unavailable {
                    reason: format!(
                        "direct insertion unavailable: {reason}; clipboard failed: {}",
                        copy_error.message
                    ),
                },
                text_preserved: false,
            },
        },
    }
}

/// Small stateful shell coordinator. Platform adapters own threads/event
/// loops; this type only owns transitions and never polls the desktop.
pub struct DesktopController<O> {
    overlay: O,
    model: OverlayModel,
}

impl<O: OverlayPort> DesktopController<O> {
    pub fn new(overlay: O) -> Self {
        Self {
            overlay,
            model: OverlayModel {
                state: DesktopState::Hidden,
                level: 0,
                preview: String::new(),
                message: String::new(),
            },
        }
    }

    pub fn invoke(&mut self, invocation: Invocation) -> DesktopState {
        self.model.state = match (self.model.state, invocation) {
            (DesktopState::Hidden, Invocation::Toggle | Invocation::Start) => {
                DesktopState::Listening
            }
            (DesktopState::Listening, Invocation::Toggle | Invocation::Stop) => {
                DesktopState::Finishing
            }
            (_, Invocation::Cancel) => DesktopState::Hidden,
            (state, _) => state,
        };
        if self.model.state == DesktopState::Hidden {
            self.overlay.hide();
        } else {
            self.overlay.render(&self.model);
        }
        self.model.state
    }

    pub fn preview(&mut self, text: impl Into<String>, level: u8) {
        if self.model.state != DesktopState::Listening {
            return;
        }
        self.model.preview = text.into();
        self.model.level = level;
        self.overlay.render(&self.model);
    }

    pub fn finishing(&mut self) {
        if self.model.state == DesktopState::Listening {
            self.model.state = DesktopState::Finishing;
            self.overlay.render(&self.model);
        }
    }

    pub fn deliver<I: DirectInserter, C: ClipboardPort>(
        &mut self,
        inserter: &I,
        clipboard: &C,
        text: &str,
    ) -> DeliveryReport {
        self.model.state = DesktopState::Delivering;
        self.overlay.render(&self.model);
        let report = deliver(inserter, clipboard, text);
        self.model.state = if report.text_preserved {
            DesktopState::Hidden
        } else {
            DesktopState::Failure
        };
        if self.model.state == DesktopState::Hidden {
            self.overlay.hide();
        } else {
            self.model.message = "Text could not be preserved".into();
            self.overlay.render(&self.model);
        }
        report
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    struct Overlay(Arc<Mutex<Vec<DesktopState>>>);
    impl OverlayPort for Overlay {
        fn render(&self, model: &OverlayModel) {
            self.0.lock().unwrap().push(model.state);
        }
        fn hide(&self) {
            self.0.lock().unwrap().push(DesktopState::Hidden);
        }
    }

    struct Inserter(Result<InsertOutcome, EngineError>);
    impl DirectInserter for Inserter {
        fn insert(&self, _: &str) -> Result<InsertOutcome, EngineError> {
            self.0.clone()
        }
    }

    struct Clipboard(bool);
    impl ClipboardPort for Clipboard {
        fn copy(&self, _: &str) -> Result<(), EngineError> {
            if self.0 {
                Ok(())
            } else {
                Err(EngineError::new(
                    vaani_core::engine::EngineErrorKind::Runtime,
                    "copy denied",
                ))
            }
        }
    }

    #[test]
    fn unavailable_insertion_copies_complete_text() {
        let report = deliver(
            &Inserter(Ok(InsertOutcome::Unavailable {
                reason: "no focused editor".into(),
            })),
            &Clipboard(true),
            "keep this",
        );
        assert!(report.text_preserved);
        assert!(matches!(report.outcome, InsertOutcome::Copied { .. }));
    }

    #[test]
    fn failed_copy_is_the_only_losing_outcome() {
        let report = deliver(
            &Inserter(Err(EngineError::new(
                vaani_core::engine::EngineErrorKind::Permission,
                "blocked",
            ))),
            &Clipboard(false),
            "retain this",
        );
        assert!(!report.text_preserved);
        assert!(matches!(report.outcome, InsertOutcome::Unavailable { .. }));
    }

    #[test]
    fn controller_has_event_driven_lifecycle() {
        let events = Arc::new(Mutex::new(Vec::new()));
        let mut controller = DesktopController::new(Overlay(events.clone()));
        assert_eq!(
            controller.invoke(Invocation::Start),
            DesktopState::Listening
        );
        controller.preview("last words", 80);
        assert_eq!(controller.invoke(Invocation::Stop), DesktopState::Finishing);
        assert_eq!(
            controller
                .deliver(
                    &Inserter(Ok(InsertOutcome::Inserted)),
                    &Clipboard(true),
                    "text"
                )
                .outcome,
            InsertOutcome::Inserted
        );
        assert!(events.lock().unwrap().contains(&DesktopState::Delivering));
    }

    #[test]
    fn account_is_optional_for_local_personalization() {
        let path =
            std::env::temp_dir().join(format!("vaani-desktop-client-{}.jsonl", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_file(path.with_extension("outbox.jsonl"));
        let repository = PersonalizationRepository::open(&path, "client-test").unwrap();
        repository
            .add_snippet("my email", "person@example.test")
            .unwrap();
        let mut client = DesktopSyncClient::new("project-id", repository);
        assert_eq!(client.email(), None);
        assert_eq!(
            client.repository().render("my email").unwrap(),
            "person@example.test"
        );
        assert!(client.sync_once().is_err());
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_file(path.with_extension("outbox.jsonl"));
    }
}
