//! Portable desktop orchestration.
//!
//! Linux Wayland/X11 and Windows provide different shortcut, focus, overlay,
//! clipboard, and insertion adapters. This crate owns the lifecycle and the
//! safety rule shared by all of them: direct insertion is best effort, then
//! the complete text is copied, and only a confirmed copy failure is reported
//! as unavailable.

use vaani_core::engine::{
    DenoiserEngine, EngineError, FormatContext, FormatRequest, FormatterEngine, InsertOutcome,
    PersonalizationProvider, SessionId, SttEngine, TextPipeline, VadEngine,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShortcutModifier {
    Ctrl,
    Alt,
    Shift,
    Super,
}

/// Validated cross-platform global invocation description. Platform adapters
/// translate this representation to native registration APIs; shells never
/// need to parse user-entered modifier strings themselves.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ShortcutSpec {
    modifiers: Vec<ShortcutModifier>,
    key: String,
}

impl ShortcutSpec {
    pub fn parse(value: &str) -> Result<Self, EngineError> {
        let mut modifiers = Vec::new();
        let mut key = None;
        for token in value
            .split('+')
            .map(str::trim)
            .filter(|token| !token.is_empty())
        {
            let token_upper = token.to_ascii_uppercase();
            let modifier = match token_upper.as_str() {
                "CTRL" | "CONTROL" => Some(ShortcutModifier::Ctrl),
                "ALT" => Some(ShortcutModifier::Alt),
                "SHIFT" => Some(ShortcutModifier::Shift),
                "SUPER" | "META" | "WIN" | "WINDOWS" => Some(ShortcutModifier::Super),
                _ => None,
            };
            if let Some(modifier) = modifier {
                if modifiers.contains(&modifier) {
                    return Err(EngineError::new(
                        vaani_core::engine::EngineErrorKind::InvalidInput,
                        "shortcut contains a duplicate modifier",
                    ));
                }
                modifiers.push(modifier);
            } else if key.replace(token_upper.clone()).is_some() {
                return Err(EngineError::new(
                    vaani_core::engine::EngineErrorKind::InvalidInput,
                    "shortcut contains multiple keys",
                ));
            }
        }
        let key = key.ok_or_else(|| {
            EngineError::new(
                vaani_core::engine::EngineErrorKind::InvalidInput,
                "shortcut must contain one key",
            )
        })?;
        if !valid_shortcut_key(&key) {
            return Err(EngineError::new(
                vaani_core::engine::EngineErrorKind::InvalidInput,
                "shortcut key is unsupported",
            ));
        }
        Ok(Self { modifiers, key })
    }

    pub fn default() -> Self {
        Self::parse("SUPER+ALT+SPACE").expect("default shortcut is valid")
    }

    pub fn modifiers(&self) -> &[ShortcutModifier] {
        &self.modifiers
    }

    pub fn key(&self) -> &str {
        &self.key
    }

    pub fn canonical(&self) -> String {
        let mut tokens = Vec::new();
        for (modifier, label) in [
            (ShortcutModifier::Ctrl, "CTRL"),
            (ShortcutModifier::Alt, "ALT"),
            (ShortcutModifier::Shift, "SHIFT"),
            (ShortcutModifier::Super, "SUPER"),
        ] {
            if self.modifiers.contains(&modifier) {
                tokens.push(label);
            }
        }
        tokens.push(self.key.as_str());
        tokens.join("+")
    }
}

fn valid_shortcut_key(key: &str) -> bool {
    (key.len() == 1 && key.as_bytes()[0].is_ascii_alphanumeric())
        || matches!(key, "SPACE" | "ESC" | "TAB" | "ENTER")
        || (key.strip_prefix('F').is_some_and(|number| {
            number
                .parse::<u8>()
                .is_ok_and(|number| (1..=12).contains(&number))
        }))
}

/// One bounded, denoised audio block ready for the STT adapter.
///
/// The front-end keeps audio in memory and never serializes it into control
/// messages, logs, or process arguments. `speech` is a gate hint only; STT
/// still receives the complete block so quiet consonants are not discarded.
#[derive(Debug, Clone, PartialEq)]
pub struct AudioChunk {
    pub samples: Vec<f32>,
    pub speech: bool,
    pub level: u8,
}

/// Platform-neutral audio capture adapter. Capture implementations may emit
/// any chunk size; this type normalizes them into the VAD's bounded blocks.
pub struct AudioFrontEnd<V, D> {
    vad: V,
    denoiser: D,
    pending: Vec<f32>,
}

impl<V, D> AudioFrontEnd<V, D>
where
    V: VadEngine,
    D: DenoiserEngine,
{
    pub fn new(vad: V, denoiser: D) -> Self {
        Self {
            vad,
            denoiser,
            pending: Vec::new(),
        }
    }

    /// Push an arbitrary-size mono PCM chunk and return all complete blocks.
    pub fn push(&mut self, samples: &[f32]) -> Result<Vec<AudioChunk>, EngineError> {
        self.pending.extend(self.denoiser.process(samples)?);
        self.drain_blocks(false)
    }

    /// Flush the final short capture chunk without dropping its samples.
    pub fn finish(&mut self) -> Result<Vec<AudioChunk>, EngineError> {
        let chunks = self.drain_blocks(true)?;
        self.vad.reset();
        Ok(chunks)
    }

    pub fn vad(&self) -> &V {
        &self.vad
    }

    /// Discard a partial capture and start a fresh VAD session.
    pub fn reset(&mut self) {
        self.pending.clear();
        self.vad.reset();
    }

    fn drain_blocks(&mut self, flush_partial: bool) -> Result<Vec<AudioChunk>, EngineError> {
        let block_size = vaani_core::vad::BLOCK_SAMPLES;
        let mut chunks = Vec::new();
        while self.pending.len() >= block_size || (flush_partial && !self.pending.is_empty()) {
            let take = self.pending.len().min(block_size);
            let mut block: Vec<f32> = self.pending.drain(..take).collect();
            let mut vad_block = block.clone();
            vad_block.resize(block_size, 0.0);
            let speech = self.vad.push_block(&vad_block)?;
            let level = (vaani_core::vad::block_amplitude(&block) * 100.0).round() as u8;
            chunks.push(AudioChunk {
                samples: std::mem::take(&mut block),
                speech,
                level,
            });
        }
        Ok(chunks)
    }
}

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

    pub fn state(&self) -> DesktopState {
        self.model.state
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
    audio_samples: usize,
}

/// Complete capture-to-delivery composition for a desktop shell. The shell
/// supplies platform capture and invokes only this session boundary; audio
/// normalization, VAD lifetime, STT, formatting, and safe delivery stay
/// consistent across Linux and Windows.
pub struct DesktopSession<S, F, P, O, I, C, V, D> {
    runtime: DesktopRuntime<S, F, P, O, I, C>,
    audio: AudioFrontEnd<V, D>,
    speech_seen: bool,
}

impl<S, F, P, O, I, C, V, D> DesktopSession<S, F, P, O, I, C, V, D>
where
    S: SttEngine,
    F: FormatterEngine,
    P: PersonalizationProvider,
    O: OverlayPort,
    I: DirectInserter,
    C: ClipboardPort,
    V: VadEngine,
    D: DenoiserEngine,
{
    pub fn new(runtime: DesktopRuntime<S, F, P, O, I, C>, audio: AudioFrontEnd<V, D>) -> Self {
        Self {
            runtime,
            audio,
            speech_seen: false,
        }
    }

    pub fn start(&mut self) -> Result<SessionId, EngineError> {
        self.audio.reset();
        self.speech_seen = false;
        self.runtime.start()
    }

    pub fn active_session(&self) -> Option<SessionId> {
        self.runtime.active_session()
    }

    pub fn state(&self) -> DesktopState {
        self.runtime.state()
    }

    /// Whether any normalized block in the active utterance passed the VAD
    /// activity gate. A shell can use this to short-circuit silence-only
    /// finalization and avoid phantom STT output.
    pub fn speech_seen(&self) -> bool {
        self.speech_seen
    }

    pub fn push_audio(&mut self, samples: &[f32]) -> Result<(), EngineError> {
        let session_id = self.active_session().ok_or_else(|| {
            EngineError::new(
                vaani_core::engine::EngineErrorKind::Cancelled,
                "no active desktop session",
            )
        })?;
        for chunk in self.audio.push(samples)? {
            self.speech_seen |= chunk.speech;
            self.runtime.feed_audio_chunk(session_id, chunk)?;
        }
        Ok(())
    }

    pub fn finish(&mut self, context: FormatContext) -> Result<DeliveryReport, EngineError> {
        let session_id = self.active_session().ok_or_else(|| {
            EngineError::new(
                vaani_core::engine::EngineErrorKind::Cancelled,
                "no active desktop session",
            )
        })?;
        for chunk in self.audio.finish()? {
            self.speech_seen |= chunk.speech;
            self.runtime.feed_audio_chunk(session_id, chunk)?;
        }
        self.runtime.finish(session_id, context)
    }

    pub fn cancel(&mut self) -> Result<(), EngineError> {
        let Some(session_id) = self.active_session() else {
            self.audio.reset();
            self.speech_seen = false;
            return Ok(());
        };
        self.runtime.cancel(session_id)?;
        self.audio.reset();
        self.speech_seen = false;
        Ok(())
    }
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
            audio_samples: 0,
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
        self.audio_samples = 0;
        Ok(session_id)
    }

    pub fn state(&self) -> DesktopState {
        self.controller.state()
    }

    pub fn active_session(&self) -> Option<SessionId> {
        self.session_id
    }

    /// Feed an in-memory audio chunk and publish only the newest partial.
    pub fn feed_audio(
        &mut self,
        session_id: SessionId,
        samples: &[f32],
        level: u8,
    ) -> Result<(), EngineError> {
        self.require_session(session_id)?;
        let max_samples = vaani_core::MAX_AUDIO_SECS as usize * vaani_core::SAMPLE_RATE as usize;
        let next_samples = self
            .audio_samples
            .checked_add(samples.len())
            .ok_or_else(|| {
                EngineError::new(
                    vaani_core::engine::EngineErrorKind::InvalidInput,
                    "desktop session audio exceeds the maximum duration",
                )
            })?;
        if next_samples > max_samples {
            return Err(EngineError::new(
                vaani_core::engine::EngineErrorKind::InvalidInput,
                "desktop session audio exceeds the maximum duration",
            ));
        }
        if let Some(partial) = self.stt.feed_audio(session_id, samples)?.into_iter().last() {
            self.controller.preview(partial.text, level);
        }
        self.audio_samples = next_samples;
        Ok(())
    }

    /// Feed one normalized front-end block into the STT lifecycle.
    pub fn feed_audio_chunk(
        &mut self,
        session_id: SessionId,
        chunk: AudioChunk,
    ) -> Result<(), EngineError> {
        self.feed_audio(session_id, &chunk.samples, chunk.level)
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
                self.audio_samples = 0;
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
        self.audio_samples = 0;
        Ok(report)
    }

    pub fn cancel(&mut self, session_id: SessionId) -> Result<(), EngineError> {
        self.require_session(session_id)?;
        self.stt.cancel(session_id)?;
        self.controller.invoke(Invocation::Cancel);
        self.session_id = None;
        self.audio_samples = 0;
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
    fn shortcut_specs_are_canonical_and_case_insensitive() {
        let spec = ShortcutSpec::parse("meta + alt + space").unwrap();
        assert_eq!(spec.canonical(), "ALT+SUPER+SPACE");
        assert_eq!(spec.key(), "SPACE");
        assert_eq!(ShortcutSpec::default().canonical(), "ALT+SUPER+SPACE");
    }

    #[test]
    fn shortcut_specs_reject_ambiguous_or_unsafe_values() {
        for value in ["CTRL+ALT", "CTRL+ALT+A+B", "CTRL+CTRL+A", "CTRL+F13"] {
            assert!(ShortcutSpec::parse(value).is_err(), "accepted {value}");
        }
    }

    #[test]
    fn audio_front_end_rechunks_without_dropping_samples() {
        let mut front_end = AudioFrontEnd::new(
            vaani_core::vad::Vad::default(),
            vaani_core::engine::NoopDenoiser,
        );
        let first = vec![0.1_f32; 100];
        let second = vec![0.2_f32; 300];
        assert!(front_end.push(&first).unwrap().is_empty());
        let chunks = front_end.push(&second).unwrap();
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].samples.len(), vaani_core::vad::BLOCK_SAMPLES);
        assert!(chunks[0].speech);
        assert_eq!(chunks[0].level, 20);

        let tail = front_end.finish().unwrap();
        assert_eq!(tail.len(), 1);
        assert_eq!(tail[0].samples, vec![0.2_f32; 80]);

        let next = front_end
            .push(&vec![0.0_f32; vaani_core::vad::BLOCK_SAMPLES])
            .unwrap();
        assert_eq!(next.len(), 1);
        assert!(!next[0].speech);
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
    fn runtime_rejects_stale_session_and_can_restart_after_failure() {
        let events = Arc::new(Mutex::new(Vec::new()));
        let mut runtime = DesktopRuntime::new(
            RuntimeStt::new(),
            RuntimeFormatter,
            RuntimePersonalization,
            Overlay(events),
            Inserter(Err(EngineError::new(
                vaani_core::engine::EngineErrorKind::Runtime,
                "insertion unavailable",
            ))),
            Clipboard(false),
        );
        let first = runtime.start().unwrap();
        assert_eq!(runtime.state(), DesktopState::Listening);
        assert!(runtime.feed_audio(SessionId::new_v4(), &[], 0).is_err());
        let oversized = vec![
            0.0_f32;
            vaani_core::MAX_AUDIO_SECS as usize * vaani_core::SAMPLE_RATE as usize
                + 1
        ];
        let error = runtime.feed_audio(first, &oversized, 0).unwrap_err();
        assert_eq!(
            error.kind,
            vaani_core::engine::EngineErrorKind::InvalidInput
        );
        let report = runtime
            .finish(
                first,
                FormatContext {
                    application: None,
                    language: "en".into(),
                    personalization: PersonalizationSnapshot::default(),
                },
            )
            .unwrap();
        assert!(!report.text_preserved);
        assert_eq!(runtime.state(), DesktopState::Failure);
        let second = runtime.start().unwrap();
        assert_ne!(first, second);
        assert_eq!(runtime.active_session(), Some(second));
        runtime.cancel(second).unwrap();
        assert_eq!(runtime.state(), DesktopState::Hidden);
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
        runtime
            .feed_audio_chunk(
                session_id,
                AudioChunk {
                    samples: vec![0.0, 0.1],
                    speech: true,
                    level: 72,
                },
            )
            .unwrap();
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
    fn desktop_session_owns_front_end_lifecycle_and_flushes_tail() {
        let inserted = Arc::new(Mutex::new(Vec::new()));
        let runtime = DesktopRuntime::new(
            RuntimeStt::new(),
            RuntimeFormatter,
            RuntimePersonalization,
            Overlay(Arc::new(Mutex::new(Vec::new()))),
            CapturingInserter(inserted.clone()),
            Clipboard(true),
        );
        let mut session = DesktopSession::new(
            runtime,
            AudioFrontEnd::new(
                vaani_core::vad::Vad::default(),
                vaani_core::engine::NoopDenoiser,
            ),
        );
        session.start().unwrap();
        assert!(!session.speech_seen());
        session.push_audio(&[0.2_f32; 100]).unwrap();
        // A sub-block tail is classified when finish flushes it.
        assert!(!session.speech_seen());
        let report = session
            .finish(FormatContext {
                application: None,
                language: "en".into(),
                personalization: PersonalizationSnapshot::default(),
            })
            .unwrap();
        assert!(session.speech_seen());
        assert!(report.text_preserved);
        assert_eq!(session.active_session(), None);
        assert_eq!(
            inserted.lock().unwrap().as_slice(),
            &["send https://github.com/example/repo".to_string()]
        );

        session.start().unwrap();
        session
            .push_audio(&[0.0_f32; vaani_core::vad::BLOCK_SAMPLES])
            .unwrap();
        assert!(!session.speech_seen());
        session.cancel().unwrap();
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
