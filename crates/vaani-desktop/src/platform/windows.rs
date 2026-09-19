//! Native Windows global-hotkey adapter.
//!
//! Registration is explicit and uses the supported User32 message mechanism;
//! text insertion is intentionally supplied by a separate adapter so a
//! future UI Automation/clipboard implementation cannot silently become raw
//! keystroke injection.

use crate::{ShortcutModifier, ShortcutSpec};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{SampleFormat, Stream, StreamConfig};
use std::ffi::c_int;
use std::mem::size_of;
use std::ptr::null_mut;
use std::sync::mpsc::{self, Receiver, TryRecvError};
use vaani_core::engine::{EngineError, EngineErrorKind, InsertOutcome};

const WM_HOTKEY: u32 = 0x0312;
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
                on_hotkey();
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
    pub sample_rate: u32,
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
        let error_callback = |error| {
            let _ = error;
        };
        let stream = match supported.sample_format() {
            SampleFormat::F32 => {
                build_input_stream::<f32>(&device, &config, sender, error_callback)
            }
            SampleFormat::I16 => {
                build_input_stream::<i16>(&device, &config, sender, error_callback)
            }
            SampleFormat::U16 => {
                build_input_stream::<u16>(&device, &config, sender, error_callback)
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
            sample_rate,
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

    pub fn is_running(&self) -> bool {
        let _ = &self.stream;
        true
    }
}

fn build_input_stream<T>(
    device: &cpal::Device,
    config: &StreamConfig,
    sender: mpsc::SyncSender<Vec<f32>>,
    error_callback: impl FnMut(cpal::StreamError) + Send + 'static,
) -> Result<Stream, cpal::BuildStreamError>
where
    T: cpal::SizedSample + cpal::Sample,
    f32: cpal::FromSample<T>,
{
    let channels = config.channels as usize;
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
            let _ = sender.try_send(mono);
        },
        error_callback,
        None,
    )
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
}
