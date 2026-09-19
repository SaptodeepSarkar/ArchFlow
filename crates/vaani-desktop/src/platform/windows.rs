//! Native Windows global-hotkey adapter.
//!
//! Registration is explicit and uses the supported User32 message mechanism;
//! text insertion is intentionally supplied by a separate adapter so a
//! future UI Automation/clipboard implementation cannot silently become raw
//! keystroke injection.

use crate::{
    DeliveryReport, DesktopSession, DesktopState, FormatContext, OverlayModel, OverlayPort,
    ShortcutModifier, ShortcutSpec,
};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, Stream, StreamConfig};
use std::ffi::c_int;
use std::mem::size_of;
use std::ptr::null_mut;
use std::sync::mpsc::{self, Receiver, TryRecvError};
use vaani_core::engine::{EngineError, EngineErrorKind, InsertOutcome};

const WM_HOTKEY: u32 = 0x0312;
const WM_VAANI_AUDIO: u32 = 0x8001;
const WM_VAANI_TRAY: u32 = 0x8002;
const WM_CLOSE: u32 = 0x0010;
const WM_DESTROY: u32 = 0x0002;
const WM_LBUTTONUP: u32 = 0x0202;
const WM_LBUTTONDBLCLK: u32 = 0x0203;
const WM_RBUTTONUP: u32 = 0x0205;
const WS_EX_TOOLWINDOW: u32 = 0x00000080;
const WS_EX_TOPMOST: u32 = 0x00000008;
const WS_POPUP: u32 = 0x80000000;
const SW_SHOW: i32 = 5;
const SW_HIDE: i32 = 0;
const SWP_NOSIZE: u32 = 0x0001;
const SWP_NOACTIVATE: u32 = 0x0010;
const HWND_TOPMOST: isize = -1;
const NIM_ADD: u32 = 0;
const NIM_DELETE: u32 = 2;
const NIF_MESSAGE: u32 = 1;
const NIF_ICON: u32 = 2;
const NIF_TIP: u32 = 4;
const IDI_APPLICATION: usize = 32512;
const CF_UNICODETEXT: u32 = 13;
const GMEM_MOVEABLE: u32 = 0x0002;
const KEYEVENTF_KEYUP: u32 = 0x0002;
const INPUT_KEYBOARD: u32 = 1;

#[repr(C)]
struct Message {
    hwnd: *mut std::ffi::c_void,
    message: u32,
    w_param: usize,
    l_param: isize,
    time: u32,
    point_x: i32,
    point_y: i32,
    private: u32,
}

#[link(name = "user32")]
extern "system" {
    fn RegisterHotKey(hwnd: *mut std::ffi::c_void, id: c_int, modifiers: u32, key: u32) -> i32;
    fn UnregisterHotKey(hwnd: *mut std::ffi::c_void, id: c_int) -> i32;
    fn GetMessageW(message: *mut Message, hwnd: *mut std::ffi::c_void, min: u32, max: u32) -> i32;
    fn TranslateMessage(message: *const Message) -> i32;
    fn DispatchMessageW(message: *const Message) -> isize;
    fn DefWindowProcW(
        hwnd: *mut std::ffi::c_void,
        message: u32,
        w_param: usize,
        l_param: isize,
    ) -> isize;
    fn RegisterClassW(class: *const WindowClass) -> u16;
    fn CreateWindowExW(
        ex_style: u32,
        class_name: *const u16,
        window_name: *const u16,
        style: u32,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
        parent: *mut std::ffi::c_void,
        menu: *mut std::ffi::c_void,
        instance: *mut std::ffi::c_void,
        param: *mut std::ffi::c_void,
    ) -> *mut std::ffi::c_void;
    fn DestroyWindow(hwnd: *mut std::ffi::c_void) -> i32;
    fn ShowWindow(hwnd: *mut std::ffi::c_void, command: i32) -> i32;
    fn SetWindowPos(
        hwnd: *mut std::ffi::c_void,
        insert_after: *mut std::ffi::c_void,
        x: i32,
        y: i32,
        width: i32,
        height: i32,
        flags: u32,
    ) -> i32;
    fn SetWindowTextW(hwnd: *mut std::ffi::c_void, text: *const u16) -> i32;
    fn LoadIconW(instance: *mut std::ffi::c_void, name: *const u16) -> *mut std::ffi::c_void;
    fn GetModuleHandleW(name: *const u16) -> *mut std::ffi::c_void;
    fn GetCurrentThreadId() -> u32;
    fn PostThreadMessageW(thread_id: u32, message: u32, w_param: usize, l_param: isize) -> i32;
    fn GetForegroundWindow() -> *mut std::ffi::c_void;
    fn GetClassNameW(hwnd: *mut std::ffi::c_void, class_name: *mut u16, max_count: i32) -> i32;
    fn OpenClipboard(owner: *mut std::ffi::c_void) -> i32;
    fn CloseClipboard() -> i32;
    fn EmptyClipboard() -> i32;
    fn SetClipboardData(format: u32, data: *mut std::ffi::c_void) -> *mut std::ffi::c_void;
    fn GlobalAlloc(flags: u32, bytes: usize) -> *mut std::ffi::c_void;
    fn GlobalLock(memory: *mut std::ffi::c_void) -> *mut u16;
    fn GlobalUnlock(memory: *mut std::ffi::c_void) -> i32;
    fn GlobalFree(memory: *mut std::ffi::c_void) -> *mut std::ffi::c_void;
    fn SendInput(count: u32, inputs: *mut Input, size: c_int) -> u32;
}

#[link(name = "shell32")]
extern "system" {
    fn Shell_NotifyIconW(message: u32, data: *mut NotifyIconData) -> i32;
}

#[repr(C)]
struct WindowClass {
    style: u32,
    window_proc:
        Option<unsafe extern "system" fn(*mut std::ffi::c_void, u32, usize, isize) -> isize>,
    class_extra: i32,
    window_extra: i32,
    instance: *mut std::ffi::c_void,
    icon: *mut std::ffi::c_void,
    cursor: *mut std::ffi::c_void,
    background: *mut std::ffi::c_void,
    menu_name: *const u16,
    class_name: *const u16,
}

unsafe extern "system" fn overlay_window_proc(
    hwnd: *mut std::ffi::c_void,
    message: u32,
    w_param: usize,
    l_param: isize,
) -> isize {
    if message == WM_CLOSE {
        let _ = DestroyWindow(hwnd);
        return 0;
    }
    if message == WM_DESTROY {
        return 0;
    }
    DefWindowProcW(hwnd, message, w_param, l_param)
}

fn wide(value: &str) -> Vec<u16> {
    value.encode_utf16().chain(std::iter::once(0)).collect()
}

#[repr(C)]
#[derive(Clone, Copy)]
struct KeyboardInput {
    virtual_key: u16,
    scan_code: u16,
    flags: u32,
    time: u32,
    extra_info: usize,
}

#[repr(C)]
union InputUnion {
    keyboard: KeyboardInput,
}

#[repr(C)]
struct Input {
    input_type: u32,
    input: InputUnion,
}

pub struct GlobalHotkey {
    id: c_int,
    modifiers: u32,
    key: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TrayEvent {
    PrimaryClick,
    DoubleClick,
    SecondaryClick,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WindowsMessage {
    Hotkey,
    Audio,
    Tray(TrayEvent),
}

impl GlobalHotkey {
    pub fn register(id: c_int, modifiers: u32, key: u32) -> Result<Self, String> {
        let registered = unsafe { RegisterHotKey(std::ptr::null_mut(), id, modifiers, key) };
        if registered == 0 {
            return Err("RegisterHotKey failed; the binding may already be claimed".into());
        }
        Ok(Self { id, modifiers, key })
    }

    pub fn register_spec(id: c_int, spec: &ShortcutSpec) -> Result<Self, String> {
        let modifiers = spec.modifiers().iter().fold(0, |flags, modifier| {
            flags
                | match modifier {
                    ShortcutModifier::Ctrl => 0x0002,
                    ShortcutModifier::Alt => 0x0001,
                    ShortcutModifier::Shift => 0x0004,
                    ShortcutModifier::Super => 0x0008,
                }
        });
        let key = virtual_key(spec.key())
            .ok_or_else(|| "shortcut key has no Windows virtual-key mapping".to_string())?;
        Self::register(id, modifiers, key)
    }

    pub fn run<F: FnMut()>(&self, mut on_hotkey: F) -> Result<(), String> {
        self.run_messages(|message| {
            if message == WM_HOTKEY {
                on_hotkey();
            }
        })
    }

    /// Run the User32 message loop and expose both hotkey and application
    /// messages to an event-driven shell.
    pub fn run_messages<F: FnMut(u32)>(&self, mut on_message: F) -> Result<(), String> {
        self.run_events(|event| match event {
            WindowsMessage::Hotkey => on_message(WM_HOTKEY),
            WindowsMessage::Audio => on_message(WM_VAANI_AUDIO),
            WindowsMessage::Tray(_) => on_message(WM_VAANI_TRAY),
        })
    }

    pub fn run_events<F: FnMut(WindowsMessage)>(&self, mut on_event: F) -> Result<(), String> {
        let _ = (self.modifiers, self.key);
        loop {
            let mut message = Message {
                hwnd: std::ptr::null_mut(),
                message: 0,
                w_param: 0,
                l_param: 0,
                time: 0,
                point_x: 0,
                point_y: 0,
                private: 0,
            };
            let result = unsafe { GetMessageW(&mut message, std::ptr::null_mut(), 0, 0) };
            if result == -1 {
                return Err("GetMessageW failed".into());
            }
            if result == 0 {
                return Ok(());
            }
            if message.message == WM_HOTKEY && message.w_param == self.id as usize {
                on_event(WindowsMessage::Hotkey);
            } else if message.message == WM_VAANI_AUDIO {
                on_event(WindowsMessage::Audio);
            } else if message.message == WM_VAANI_TRAY {
                let event = match message.l_param as u32 {
                    WM_LBUTTONUP => Some(TrayEvent::PrimaryClick),
                    WM_LBUTTONDBLCLK => Some(TrayEvent::DoubleClick),
                    WM_RBUTTONUP => Some(TrayEvent::SecondaryClick),
                    _ => None,
                };
                if let Some(event) = event {
                    on_event(WindowsMessage::Tray(event));
                }
            }
            unsafe {
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
        }
    }
}

impl Drop for GlobalHotkey {
    fn drop(&mut self) {
        unsafe {
            let _ = UnregisterHotKey(std::ptr::null_mut(), self.id);
        }
    }
}

/// Minimal topmost Win32 overlay implementing the portable overlay contract.
/// The shell remains responsible for creating it on the message-loop thread.
pub struct WindowsOverlay {
    hwnd: usize,
}

impl WindowsOverlay {
    pub fn new() -> Result<Self, EngineError> {
        let class_name = wide("VaaniOverlayWindow");
        let instance = unsafe { GetModuleHandleW(null_mut()) };
        let class = WindowClass {
            style: 0,
            window_proc: Some(overlay_window_proc),
            class_extra: 0,
            window_extra: 0,
            instance,
            icon: null_mut(),
            cursor: null_mut(),
            background: null_mut(),
            menu_name: null_mut(),
            class_name: class_name.as_ptr(),
        };
        unsafe {
            let _ = RegisterClassW(&class);
        }
        let title = wide("Vaani");
        let window = unsafe {
            CreateWindowExW(
                WS_EX_TOOLWINDOW | WS_EX_TOPMOST,
                class_name.as_ptr(),
                title.as_ptr(),
                WS_POPUP,
                40,
                40,
                620,
                96,
                null_mut(),
                null_mut(),
                instance,
                null_mut(),
            )
        };
        if window.is_null() {
            return Err(EngineError::new(
                EngineErrorKind::Unavailable,
                "could not create Windows Vaani overlay",
            ));
        }
        Ok(Self {
            hwnd: window as usize,
        })
    }

    fn hwnd(&self) -> *mut std::ffi::c_void {
        self.hwnd as *mut std::ffi::c_void
    }
}

unsafe impl Send for WindowsOverlay {}
unsafe impl Sync for WindowsOverlay {}

impl OverlayPort for WindowsOverlay {
    fn render(&self, model: &OverlayModel) {
        let state = match model.state {
            DesktopState::Hidden => "Hidden",
            DesktopState::Listening => "Listening",
            DesktopState::Finishing => "Finishing",
            DesktopState::Delivering => "Delivering",
            DesktopState::Failure => "Failure",
        };
        let mut text = format!("Vaani · {state}");
        if !model.preview.is_empty() {
            text.push_str("\n");
            text.push_str(&model.preview);
        } else if !model.message.is_empty() {
            text.push_str("\n");
            text.push_str(&model.message);
        }
        let title = wide(&text);
        unsafe {
            let _ = SetWindowTextW(self.hwnd(), title.as_ptr());
            let _ = SetWindowPos(
                self.hwnd(),
                HWND_TOPMOST as *mut std::ffi::c_void,
                40,
                40,
                620,
                96,
                SWP_NOSIZE | SWP_NOACTIVATE,
            );
            let _ = ShowWindow(self.hwnd(), SW_SHOW);
        }
    }

    fn hide(&self) {
        unsafe {
            let _ = ShowWindow(self.hwnd(), SW_HIDE);
        }
    }
}

impl Drop for WindowsOverlay {
    fn drop(&mut self) {
        unsafe {
            let _ = DestroyWindow(self.hwnd());
        }
    }
}

#[repr(C)]
struct NotifyIconData {
    cb_size: u32,
    hwnd: *mut std::ffi::c_void,
    id: u32,
    flags: u32,
    callback_message: u32,
    icon: *mut std::ffi::c_void,
    tip: [u16; 128],
    state: u32,
    state_mask: u32,
    info: [u16; 256],
    version: u32,
    info_title: [u16; 64],
    info_flags: u32,
    guid: [u8; 16],
    balloon_icon: *mut std::ffi::c_void,
}

/// Tray registration for a Windows shell. Tray callbacks arrive as
/// `WM_VAANI_TRAY` messages in `GlobalHotkey::run_messages`.
pub struct WindowsTray {
    hwnd: usize,
    id: u32,
}

impl WindowsTray {
    pub fn attach(overlay: &WindowsOverlay, id: u32) -> Result<Self, EngineError> {
        let mut tip = [0u16; 128];
        let label = wide("Vaani");
        let tip_len = label.len().min(tip.len());
        tip[..tip_len].copy_from_slice(&label[..tip_len]);
        let mut data = NotifyIconData {
            cb_size: size_of::<NotifyIconData>() as u32,
            hwnd: overlay.hwnd(),
            id,
            flags: NIF_MESSAGE | NIF_ICON | NIF_TIP,
            callback_message: WM_VAANI_TRAY,
            icon: unsafe { LoadIconW(null_mut(), IDI_APPLICATION as *const u16) },
            tip,
            state: 0,
            state_mask: 0,
            info: [0; 256],
            version: 0,
            info_title: [0; 64],
            info_flags: 0,
            guid: [0; 16],
            balloon_icon: null_mut(),
        };
        if unsafe { Shell_NotifyIconW(NIM_ADD, &mut data) } == 0 {
            return Err(EngineError::new(
                EngineErrorKind::Unavailable,
                "could not attach Vaani Windows tray icon",
            ));
        }
        Ok(Self {
            hwnd: overlay.hwnd as usize,
            id,
        })
    }
}

impl Drop for WindowsTray {
    fn drop(&mut self) {
        let mut data = NotifyIconData {
            cb_size: size_of::<NotifyIconData>() as u32,
            hwnd: self.hwnd as *mut std::ffi::c_void,
            id: self.id,
            flags: 0,
            callback_message: 0,
            icon: null_mut(),
            tip: [0; 128],
            state: 0,
            state_mask: 0,
            info: [0; 256],
            version: 0,
            info_title: [0; 64],
            info_flags: 0,
            guid: [0; 16],
            balloon_icon: null_mut(),
        };
        unsafe {
            let _ = Shell_NotifyIconW(NIM_DELETE, &mut data);
        }
    }
}

/// Windows clipboard adapter. Text is copied through the Win32 clipboard API
/// from memory; it is never placed in a command line or shell invocation.
pub struct WindowsClipboard;

/// WASAPI microphone capture for a Windows shell.
///
/// The callback only forwards bounded in-memory PCM blocks. A shell drains
/// them and passes the samples to `AudioFrontEnd`; no audio is serialized,
/// logged, or passed through a process argument.
pub struct WindowsAudioCapture {
    stream: Stream,
    samples: Receiver<Vec<f32>>,
    message_thread: u32,
    pub sample_rate: u32,
    pub source_sample_rate: u32,
    pub channels: u16,
}

impl WindowsAudioCapture {
    pub fn start() -> Result<Self, EngineError> {
        let host = cpal::default_host();
        let device = host.default_input_device().ok_or_else(|| {
            EngineError::new(
                EngineErrorKind::Unavailable,
                "Windows has no default microphone",
            )
        })?;
        let supported = device.default_input_config().map_err(|error| {
            EngineError::new(
                EngineErrorKind::Unavailable,
                format!("Windows microphone format unavailable: {error}"),
            )
        })?;
        let sample_rate = supported.sample_rate().0;
        let channels = supported.channels();
        let config: StreamConfig = supported.clone().into();
        let (sender, samples) = mpsc::sync_channel(8);
        let message_thread = unsafe { GetCurrentThreadId() };
        let notify_thread = message_thread;
        let error_callback = |error| {
            let _ = error;
        };
        let stream = match supported.sample_format() {
            SampleFormat::F32 => {
                build_input_stream::<f32>(&device, &config, sender, notify_thread, error_callback)
            }
            SampleFormat::I16 => {
                build_input_stream::<i16>(&device, &config, sender, notify_thread, error_callback)
            }
            SampleFormat::U16 => {
                build_input_stream::<u16>(&device, &config, sender, notify_thread, error_callback)
            }
            _format => Err(cpal::BuildStreamError::StreamConfigNotSupported),
        }
        .map_err(|error| {
            EngineError::new(
                EngineErrorKind::Unavailable,
                format!("Windows microphone stream unavailable: {error}"),
            )
        })?;
        stream.play().map_err(|error| {
            EngineError::new(
                EngineErrorKind::Runtime,
                format!("Windows microphone could not start: {error}"),
            )
        })?;
        Ok(Self {
            stream,
            samples,
            message_thread,
            sample_rate: 16_000,
            source_sample_rate: sample_rate,
            channels,
        })
    }

    /// Drain at most one callback block. The caller owns session timing and
    /// forwards each returned block to the shared audio front-end.
    pub fn try_next_block(&self) -> Result<Option<Vec<f32>>, EngineError> {
        match self.samples.try_recv() {
            Ok(samples) => Ok(Some(samples)),
            Err(TryRecvError::Empty) => Ok(None),
            Err(TryRecvError::Disconnected) => Err(EngineError::new(
                EngineErrorKind::Runtime,
                "Windows microphone stream ended",
            )),
        }
    }

    fn drain_blocks(&self) -> Result<Vec<Vec<f32>>, EngineError> {
        let mut blocks = Vec::new();
        while let Some(block) = self.try_next_block()? {
            blocks.push(block);
        }
        Ok(blocks)
    }

    pub fn is_running(&self) -> bool {
        let _ = (&self.stream, self.message_thread);
        true
    }
}

fn build_input_stream<T>(
    device: &cpal::Device,
    config: &StreamConfig,
    sender: mpsc::SyncSender<Vec<f32>>,
    message_thread: u32,
    error_callback: impl FnMut(cpal::StreamError) + Send + 'static,
) -> Result<Stream, cpal::BuildStreamError>
where
    T: cpal::SizedSample + cpal::Sample,
    f32: cpal::FromSample<T>,
{
    let channels = config.channels as usize;
    let source_sample_rate = config.sample_rate.0;
    device.build_input_stream(
        config,
        move |data: &[T], _| {
            let mut mono = Vec::with_capacity(data.len() / channels.max(1));
            for frame in data.chunks(channels.max(1)) {
                let sum = frame
                    .iter()
                    .map(|sample| (*sample).to_sample::<f32>())
                    .sum::<f32>();
                mono.push(sum / frame.len() as f32);
            }
            let mono = resample_to_16khz(&mono, source_sample_rate);
            let _ = sender.try_send(mono);
            unsafe {
                let _ = PostThreadMessageW(message_thread, WM_VAANI_AUDIO, 0, 0);
            }
        },
        error_callback,
        None,
    )
}

fn resample_to_16khz(samples: &[f32], source_rate: u32) -> Vec<f32> {
    if samples.is_empty() || source_rate == 16_000 {
        return samples.to_vec();
    }
    let output_len = ((samples.len() as u64 * 16_000) / source_rate as u64) as usize;
    let mut output = Vec::with_capacity(output_len);
    for index in 0..output_len {
        let source_position = index as f64 * source_rate as f64 / 16_000.0;
        let left = source_position.floor() as usize;
        let right = (left + 1).min(samples.len() - 1);
        let fraction = (source_position - left as f64) as f32;
        output.push(samples[left] + (samples[right] - samples[left]) * fraction);
    }
    output
}

/// Event-driven Windows shell bridge. The caller supplies the already-wired
/// portable session; this bridge owns only the User32 hotkey loop and the
/// WASAPI capture lifetime.
pub struct WindowsSessionLoop<S, F, P, O, I, C, V, D> {
    hotkey: GlobalHotkey,
    session: DesktopSession<S, F, P, O, I, C, V, D>,
    context: FormatContext,
    capture: Option<WindowsAudioCapture>,
}

impl<S, F, P, O, I, C, V, D> WindowsSessionLoop<S, F, P, O, I, C, V, D>
where
    S: vaani_core::engine::SttEngine,
    F: vaani_core::engine::FormatterEngine,
    P: vaani_core::engine::PersonalizationProvider,
    O: crate::OverlayPort,
    I: crate::DirectInserter,
    C: crate::ClipboardPort,
    V: vaani_core::engine::VadEngine,
    D: vaani_core::engine::DenoiserEngine,
{
    pub fn new(
        hotkey: GlobalHotkey,
        session: DesktopSession<S, F, P, O, I, C, V, D>,
        context: FormatContext,
    ) -> Self {
        Self {
            hotkey,
            session,
            context,
            capture: None,
        }
    }

    pub fn run(
        self,
        mut on_result: impl FnMut(Result<Option<DeliveryReport>, EngineError>),
    ) -> Result<(), String> {
        let Self {
            hotkey,
            mut session,
            context,
            mut capture,
        } = self;
        hotkey.run_events(move |event| match event {
            WindowsMessage::Hotkey | WindowsMessage::Tray(TrayEvent::PrimaryClick) => {
                Self::toggle_parts(&mut session, &context, &mut capture, &mut on_result)
            }
            WindowsMessage::Audio => {
                if let Err(error) = Self::drain_parts(&mut session, &mut capture) {
                    let _ = session.cancel();
                    capture = None;
                    on_result(Err(error));
                }
            }
            WindowsMessage::Tray(TrayEvent::DoubleClick | TrayEvent::SecondaryClick) => {}
        })
    }

    fn toggle_parts(
        session: &mut DesktopSession<S, F, P, O, I, C, V, D>,
        context: &FormatContext,
        capture: &mut Option<WindowsAudioCapture>,
        on_result: &mut impl FnMut(Result<Option<DeliveryReport>, EngineError>),
    ) {
        if capture.is_some() {
            let result = Self::drain_parts(session, capture).and_then(|()| {
                *capture = None;
                session.finish_if_speech(context.clone())
            });
            on_result(result);
            return;
        }
        let next_capture = match WindowsAudioCapture::start() {
            Ok(capture) => capture,
            Err(error) => {
                on_result(Err(error));
                return;
            }
        };
        if let Err(error) = session.start() {
            on_result(Err(error));
            return;
        }
        *capture = Some(next_capture);
    }

    fn drain_parts(
        session: &mut DesktopSession<S, F, P, O, I, C, V, D>,
        capture: &mut Option<WindowsAudioCapture>,
    ) -> Result<(), EngineError> {
        let Some(capture) = capture.as_ref() else {
            return Ok(());
        };
        for block in capture.drain_blocks()? {
            session.push_audio(&block)?;
        }
        Ok(())
    }
}

impl crate::ClipboardPort for WindowsClipboard {
    fn copy(&self, text: &str) -> Result<(), EngineError> {
        copy_windows(text)
    }
}

/// Safe best-effort insertion: clipboard ownership plus a Ctrl+V dispatch.
/// Terminal and multiline shell-like targets deliberately remain copy-only.
pub struct WindowsInserter;

impl crate::DirectInserter for WindowsInserter {
    fn insert(&self, text: &str) -> Result<InsertOutcome, EngineError> {
        if text.is_empty() {
            return Err(EngineError::new(
                EngineErrorKind::InvalidInput,
                "empty text",
            ));
        }
        let window = foreground_window()?;
        if is_terminal(&window) || (text.contains('\n') && looks_shell_like(text)) {
            copy_windows(text)?;
            return Ok(InsertOutcome::Copied {
                reason: "terminal or shell-like target is copy-only".into(),
            });
        }
        copy_windows(text)?;
        send_paste()?;
        Ok(InsertOutcome::Copied {
            reason: "paste requested through focused Windows editor".into(),
        })
    }
}

fn copy_windows(text: &str) -> Result<(), EngineError> {
    let mut wide: Vec<u16> = text.encode_utf16().collect();
    wide.push(0);
    unsafe {
        if OpenClipboard(null_mut()) == 0 {
            return Err(EngineError::new(
                EngineErrorKind::Unavailable,
                "Windows clipboard is busy",
            ));
        }
        let result = (|| {
            if EmptyClipboard() == 0 {
                return Err(EngineError::new(
                    EngineErrorKind::Runtime,
                    "could not clear Windows clipboard",
                ));
            }
            let memory = GlobalAlloc(GMEM_MOVEABLE, wide.len() * size_of::<u16>());
            if memory.is_null() {
                return Err(EngineError::new(
                    EngineErrorKind::Runtime,
                    "could not allocate clipboard memory",
                ));
            }
            let destination = GlobalLock(memory);
            if destination.is_null() {
                let _ = GlobalFree(memory);
                return Err(EngineError::new(
                    EngineErrorKind::Runtime,
                    "could not lock clipboard memory",
                ));
            }
            std::ptr::copy_nonoverlapping(wide.as_ptr(), destination, wide.len());
            let _ = GlobalUnlock(memory);
            if SetClipboardData(CF_UNICODETEXT, memory).is_null() {
                let _ = GlobalFree(memory);
                return Err(EngineError::new(
                    EngineErrorKind::Runtime,
                    "could not publish Windows clipboard text",
                ));
            }
            Ok(())
        })();
        let _ = CloseClipboard();
        result
    }
}

fn foreground_window() -> Result<*mut std::ffi::c_void, EngineError> {
    let window = unsafe { GetForegroundWindow() };
    if window.is_null() {
        Err(EngineError::new(
            EngineErrorKind::Unavailable,
            "focused window unavailable",
        ))
    } else {
        Ok(window)
    }
}

fn foreground_class(window: *mut std::ffi::c_void) -> String {
    let mut buffer = [0u16; 128];
    let length = unsafe { GetClassNameW(window, buffer.as_mut_ptr(), buffer.len() as i32) };
    String::from_utf16_lossy(&buffer[..length.max(0) as usize])
}

fn is_terminal(window: &*mut std::ffi::c_void) -> bool {
    let class = foreground_class(*window).to_ascii_lowercase();
    [
        "cascadia_window_class",
        "consolewindowclass",
        "mintty",
        "windowsterminal",
    ]
    .iter()
    .any(|name| class.contains(name))
}

fn send_paste() -> Result<(), EngineError> {
    let mut inputs = [
        Input {
            input_type: INPUT_KEYBOARD,
            input: InputUnion {
                keyboard: KeyboardInput {
                    virtual_key: 0x11,
                    scan_code: 0,
                    flags: 0,
                    time: 0,
                    extra_info: 0,
                },
            },
        },
        Input {
            input_type: INPUT_KEYBOARD,
            input: InputUnion {
                keyboard: KeyboardInput {
                    virtual_key: 0x56,
                    scan_code: 0,
                    flags: 0,
                    time: 0,
                    extra_info: 0,
                },
            },
        },
        Input {
            input_type: INPUT_KEYBOARD,
            input: InputUnion {
                keyboard: KeyboardInput {
                    virtual_key: 0x56,
                    scan_code: 0,
                    flags: KEYEVENTF_KEYUP,
                    time: 0,
                    extra_info: 0,
                },
            },
        },
        Input {
            input_type: INPUT_KEYBOARD,
            input: InputUnion {
                keyboard: KeyboardInput {
                    virtual_key: 0x11,
                    scan_code: 0,
                    flags: KEYEVENTF_KEYUP,
                    time: 0,
                    extra_info: 0,
                },
            },
        },
    ];
    let sent = unsafe {
        SendInput(
            inputs.len() as u32,
            inputs.as_mut_ptr(),
            size_of::<Input>() as c_int,
        )
    };
    if sent == inputs.len() as u32 {
        Ok(())
    } else {
        Err(EngineError::new(
            EngineErrorKind::Runtime,
            "Windows paste dispatch failed",
        ))
    }
}

fn looks_shell_like(text: &str) -> bool {
    text.lines().any(|line| {
        let line = line.trim_start().to_ascii_lowercase();
        ["del ", "format ", "git ", "cargo ", "powershell ", "rm "]
            .iter()
            .any(|prefix| line.starts_with(prefix))
    })
}

fn virtual_key(key: &str) -> Option<u32> {
    if key.len() == 1 && key.as_bytes()[0].is_ascii_alphanumeric() {
        return Some(key.as_bytes()[0].to_ascii_uppercase() as u32);
    }
    match key {
        "SPACE" => Some(0x20),
        "ESC" => Some(0x1b),
        "TAB" => Some(0x09),
        "ENTER" => Some(0x0d),
        _ => key
            .strip_prefix('F')
            .and_then(|number| number.parse::<u32>().ok())
            .filter(|number| (1..=12).contains(number))
            .map(|number| 0x70 + number - 1),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shortcut_spec_maps_supported_windows_keys() {
        assert_eq!(virtual_key("A"), Some(0x41));
        assert_eq!(virtual_key("SPACE"), Some(0x20));
        assert_eq!(virtual_key("F12"), Some(0x7b));
        assert_eq!(virtual_key("F13"), None);
    }

    #[test]
    fn shell_like_text_is_not_pasteable() {
        assert!(looks_shell_like("powershell Get-Process"));
        assert!(!looks_shell_like("write a meeting note"));
    }

    #[test]
    fn capture_resampling_normalizes_source_rate_to_worker_rate() {
        let downsampled = resample_to_16khz(&[0.0, 1.0, 0.0, -1.0], 32_000);
        assert_eq!(downsampled.len(), 2);
        assert_eq!(downsampled[0], 0.0);
        assert_eq!(downsampled[1], 0.0);

        let upsampled = resample_to_16khz(&[0.25, -0.25], 8_000);
        assert_eq!(upsampled.len(), 4);
        assert_eq!(upsampled.first(), Some(&0.25));
        assert_eq!(upsampled.last(), Some(&-0.25));
    }
}
