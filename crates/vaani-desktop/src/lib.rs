//! Portable desktop orchestration.
//!
//! Linux Wayland/X11 and Windows provide different shortcut, focus, overlay,
//! clipboard, and insertion adapters. This crate owns the lifecycle and the
//! safety rule shared by all of them: direct insertion is best effort, then
//! the complete text is copied, and only a confirmed copy failure is reported
//! as unavailable.

use vaani_core::engine::{
    EngineError, FormatContext, FormatRequest, FormatterEngine, InsertOutcome,
    PersonalizationProvider, SessionId, SttEngine, TextPipeline,
};

pub mod credentials;
pub mod firebase;
pub mod personalization;
#[cfg(any(unix, windows))]
pub mod platform;
pub use credentials::SecureSessionStore;
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

    pub fn persist_session(&self, store: &SecureSessionStore) -> Result<(), EngineError> {
        self.session
            .as_ref()
            .ok_or_else(|| {
                EngineError::new(
                    vaani_core::engine::EngineErrorKind::Unavailable,
                    "not signed in",
                )
            })
            .and_then(|session| store.save(session))
    }

    pub fn restore_session(&mut self, store: &SecureSessionStore) -> Result<bool, EngineError> {
        let Some(session) = store.load()? else {
            return Ok(false);
        };
        self.session = Some(session);
        self.cursor = None;
        Ok(true)
    }

    pub fn clear_persisted_session(&self, store: &SecureSessionStore) -> Result<(), EngineError> {
        store.clear()
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
            (DesktopState::Failure, Invocation::Toggle | Invocation::Start) => {
                DesktopState::Listening
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

    pub fn fail(&mut self, message: impl Into<String>) {
        self.model.state = DesktopState::Failure;
        self.model.message = message.into();
        self.overlay.render(&self.model);
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

/// Event-driven desktop runtime composition. Platform capture and shortcut
/// adapters feed this type in memory; the runtime owns the stable STT →
/// formatter → personalization → delivery sequence.
pub struct DesktopRuntime<S, F, P, O, I, C> {
    stt: S,
    pipeline: TextPipeline<F, P>,
    controller: DesktopController<O>,
    inserter: I,
    clipboard: C,
    session_id: Option<SessionId>,
}

impl<S, F, P, O, I, C> DesktopRuntime<S, F, P, O, I, C>
where
    S: SttEngine,
    F: FormatterEngine,
    P: PersonalizationProvider,
    O: OverlayPort,
    I: DirectInserter,
    C: ClipboardPort,
{
    pub fn new(
        stt: S,
        formatter: F,
        personalization: P,
        overlay: O,
        inserter: I,
        clipboard: C,
    ) -> Self {
        Self {
            stt,
            pipeline: TextPipeline::new(formatter, personalization),
            controller: DesktopController::new(overlay),
            inserter,
            clipboard,
            session_id: None,
        }
    }

    pub fn start(&mut self) -> Result<SessionId, EngineError> {
        if self.session_id.is_some()
            || self.controller.invoke(Invocation::Start) != DesktopState::Listening
        {
            return Err(EngineError::new(
                vaani_core::engine::EngineErrorKind::Runtime,
                "desktop session already active",
            ));
        }
        let session_id = SessionId::new_v4();
        if let Err(error) = self.stt.start(session_id) {
            self.controller.invoke(Invocation::Cancel);
            return Err(error);
        }
        self.session_id = Some(session_id);
        Ok(session_id)
    }

    /// Feed an in-memory audio chunk and publish only the newest partial.
    pub fn feed_audio(
        &mut self,
        session_id: SessionId,
        samples: &[f32],
        level: u8,
    ) -> Result<(), EngineError> {
        self.require_session(session_id)?;
        if let Some(partial) = self.stt.feed_audio(session_id, samples)?.into_iter().last() {
            self.controller.preview(partial.text, level);
        }
        Ok(())
    }

    pub fn finish(
        &mut self,
        session_id: SessionId,
        context: FormatContext,
    ) -> Result<DeliveryReport, EngineError> {
        self.require_session(session_id)?;
        self.controller.invoke(Invocation::Stop);
        let final_partial = match self.stt.finalize(session_id) {
            Ok(partial) => partial,
            Err(error) => {
                self.controller.fail(error.message.clone());
                self.session_id = None;
                return Err(error);
            }
        };
        let request = FormatRequest {
            session_id,
            transcript: final_partial.text,
            context,
        };
        let text = match self.pipeline.process(&request) {
            Ok(result) => result.text,
            Err(_) => request.transcript,
        };
        let report = self
            .controller
            .deliver(&self.inserter, &self.clipboard, &text);
        self.session_id = None;
        Ok(report)
    }

    pub fn cancel(&mut self, session_id: SessionId) -> Result<(), EngineError> {
        self.require_session(session_id)?;
        self.stt.cancel(session_id)?;
        self.controller.invoke(Invocation::Cancel);
        self.session_id = None;
        Ok(())
    }

    fn require_session(&self, session_id: SessionId) -> Result<(), EngineError> {
        if self.session_id == Some(session_id) {
            Ok(())
        } else {
            Err(EngineError::new(
                vaani_core::engine::EngineErrorKind::Cancelled,
                "stale desktop session",
            ))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};
    use vaani_core::engine::{FormatResult, SttCapabilities, SttPartial};
    use vaani_core::personalization::PersonalizationSnapshot;

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

    struct RuntimeStt {
        capabilities: SttCapabilities,
        active: Option<SessionId>,
    }

    impl RuntimeStt {
        fn new() -> Self {
            Self {
                capabilities: SttCapabilities {
                    engine_id: "test-stt".into(),
                    languages: vec!["en".into()],
                    streaming: true,
                    n_best: false,
                },
                active: None,
            }
        }

        fn check(&self, session_id: SessionId) -> Result<(), EngineError> {
            if self.active == Some(session_id) {
                Ok(())
            } else {
                Err(EngineError::new(
                    vaani_core::engine::EngineErrorKind::Cancelled,
                    "stale test session",
                ))
            }
        }
    }

    impl SttEngine for RuntimeStt {
        fn capabilities(&self) -> &SttCapabilities {
            &self.capabilities
        }

        fn start(&mut self, session_id: SessionId) -> Result<(), EngineError> {
            self.active = Some(session_id);
            Ok(())
        }

        fn feed_audio(
            &mut self,
            session_id: SessionId,
            _samples: &[f32],
        ) -> Result<Vec<SttPartial>, EngineError> {
            self.check(session_id)?;
            Ok(vec![SttPartial {
                session_id,
                text: "send my github".into(),
                revision: 1,
                is_final: false,
            }])
        }

        fn finalize(&mut self, session_id: SessionId) -> Result<SttPartial, EngineError> {
            self.check(session_id)?;
            Ok(SttPartial {
                session_id,
                text: "send my github".into(),
                revision: 2,
                is_final: true,
            })
        }

        fn cancel(&mut self, session_id: SessionId) -> Result<(), EngineError> {
            self.check(session_id)?;
            self.active = None;
            Ok(())
        }
    }

    struct RuntimeFormatter;
    impl FormatterEngine for RuntimeFormatter {
        fn engine_id(&self) -> &str {
            "test-formatter"
        }

        fn format(&self, request: &FormatRequest) -> Result<FormatResult, EngineError> {
            Ok(FormatResult {
                engine_id: self.engine_id().into(),
                text: request.transcript.clone(),
                changed: false,
            })
        }
    }

    struct RuntimePersonalization;
    impl PersonalizationProvider for RuntimePersonalization {
        fn snapshot(&self) -> Result<PersonalizationSnapshot, EngineError> {
            Ok(PersonalizationSnapshot {
                vocabulary: Vec::new(),
                snippets: vec![vaani_core::personalization::Snippet {
                    id: "github".into(),
                    trigger: "my GitHub".into(),
                    value: "https://github.com/example/repo".into(),
                    created_at_ms: 0,
                    updated_at_ms: 0,
                }],
                replacements: Vec::new(),
            })
        }
    }

    struct CapturingInserter(Arc<Mutex<Vec<String>>>);
    impl DirectInserter for CapturingInserter {
        fn insert(&self, text: &str) -> Result<InsertOutcome, EngineError> {
            self.0.lock().unwrap().push(text.to_owned());
            Ok(InsertOutcome::Inserted)
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
    fn runtime_wires_partial_final_personalization_and_delivery() {
        let events = Arc::new(Mutex::new(Vec::new()));
        let inserted = Arc::new(Mutex::new(Vec::new()));
        let mut runtime = DesktopRuntime::new(
            RuntimeStt::new(),
            RuntimeFormatter,
            RuntimePersonalization,
            Overlay(events.clone()),
            CapturingInserter(inserted.clone()),
            Clipboard(true),
        );
        let session_id = runtime.start().unwrap();
        runtime.feed_audio(session_id, &[0.0, 0.1], 72).unwrap();
        let report = runtime
            .finish(
                session_id,
                FormatContext {
                    application: Some("test-editor".into()),
                    language: "en".into(),
                    personalization: PersonalizationSnapshot::default(),
                },
            )
            .unwrap();
        assert!(report.text_preserved);
        assert_eq!(
            inserted.lock().unwrap().as_slice(),
            &["send https://github.com/example/repo".to_string()]
        );
        assert!(events.lock().unwrap().contains(&DesktopState::Listening));
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
