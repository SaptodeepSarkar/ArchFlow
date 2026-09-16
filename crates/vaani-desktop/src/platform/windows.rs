//! Native Windows global-hotkey adapter.
//!
//! Registration is explicit and uses the supported User32 message mechanism;
//! text insertion is intentionally supplied by a separate adapter so a
//! future UI Automation/clipboard implementation cannot silently become raw
//! keystroke injection.

use std::ffi::c_int;

const WM_HOTKEY: u32 = 0x0312;

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
