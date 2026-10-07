use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverlayStyle {
    pub font_size: u32,
    pub text_color: String,
    pub stroke_color: String,
    pub stroke_width: u32,
}

impl Default for OverlayStyle {
    fn default() -> Self {
        Self {
            font_size: 24,
            text_color: "#ffffff".to_string(),
            stroke_color: "#000000".to_string(),
            stroke_width: 2,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OverlayState {
    pub is_visible: bool,
    pub is_interactive: bool,
    pub style: OverlayStyle,
}

impl Default for OverlayState {
    fn default() -> Self {
        Self {
            is_visible: true,
            is_interactive: false,
            style: OverlayStyle::default(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubtitlePayload {
    pub text: String,
    pub duration_ms: Option<u64>,
}

/// # Safety
/// `ns_window_ptr` must be a valid, non-null pointer to a live `NSWindow`
/// obtained from Tauri's `ns_window()` API within the setup lifecycle.
#[cfg(target_os = "macos")]
pub(crate) fn configure_macos_fullscreen_overlay(ns_window_ptr: *mut std::ffi::c_void) {
    if ns_window_ptr.is_null() {
        return;
    }
    use std::ffi::c_void;
    extern "C" {
        fn sel_registerName(name: *const std::ffi::c_char) -> *mut c_void;
        fn objc_msgSend();
    }

    let nswindow = ns_window_ptr as *mut c_void;

    // SAFETY: Registered selectors are checked for non-null before invocation.
    // 1. NSWindowCollectionBehaviorCanJoinAllSpaces (1) | NSWindowCollectionBehaviorFullScreenAuxiliary (256) | NSWindowCollectionBehaviorStationary (16) = 273
    let sel_collection =
        unsafe { sel_registerName(b"setCollectionBehavior:\0".as_ptr() as *const _) };
    if !sel_collection.is_null() {
        let send_usize: unsafe extern "C" fn(*mut c_void, *mut c_void, usize) =
            unsafe { std::mem::transmute(objc_msgSend as *const ()) };
        unsafe { send_usize(nswindow, sel_collection, 1 | 256 | 16) };
    }

    // 2. NSScreenSaverWindowLevel = 1000
    let sel_level = unsafe { sel_registerName(b"setLevel:\0".as_ptr() as *const _) };
    if !sel_level.is_null() {
        let send_isize: unsafe extern "C" fn(*mut c_void, *mut c_void, isize) =
            unsafe { std::mem::transmute(objc_msgSend as *const ()) };
        unsafe { send_isize(nswindow, sel_level, 1000) };
    }

    // 3. setHidesOnDeactivate: NO (0u8 across C ABI)
    let sel_hides =
        unsafe { sel_registerName(b"setHidesOnDeactivate:\0".as_ptr() as *const _) };
    if !sel_hides.is_null() {
        let send_u8: unsafe extern "C" fn(*mut c_void, *mut c_void, u8) =
            unsafe { std::mem::transmute(objc_msgSend as *const ()) };
        unsafe { send_u8(nswindow, sel_hides, 0u8) };
    }

    // 4. orderFrontRegardless
    let sel_order = unsafe { sel_registerName(b"orderFrontRegardless\0".as_ptr() as *const _) };
    if !sel_order.is_null() {
        let send_void: unsafe extern "C" fn(*mut c_void, *mut c_void) =
            unsafe { std::mem::transmute(objc_msgSend as *const ()) };
        unsafe { send_void(nswindow, sel_order) };
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_overlay_defaults() {
        let state = OverlayState::default();
        assert!(state.is_visible);
        assert!(!state.is_interactive);
        assert_eq!(state.style.font_size, 24);
        assert_eq!(state.style.text_color, "#ffffff");
        assert_eq!(state.style.stroke_color, "#000000");
        assert_eq!(state.style.stroke_width, 2);
    }

    #[test]
    fn test_subtitle_payload_serialization() {
        let payload = SubtitlePayload {
            text: "Hello, World!".to_string(),
            duration_ms: Some(4000),
        };
        let json = serde_json::to_string(&payload).expect("serialize payload");
        assert!(json.contains("Hello, World!"));
        assert!(json.contains("4000"));
    }

    #[test]
    #[cfg(target_os = "macos")]
    fn test_macos_fullscreen_null_safety() {
        // Must safely return on null pointer without panicking
        configure_macos_fullscreen_overlay(std::ptr::null_mut());
    }
}
