pub mod capture;
pub mod diff;
pub mod overlay;

use std::sync::Mutex;
use tauri::{Emitter, Manager};

use capture::{CaptureEngine, CaptureRoi, CaptureTargets};
use diff::{DiffResult, FrameDiffDetector};
use overlay::{OverlayState, OverlayStyle, SubtitlePayload};
use serde::Serialize;

const OVERLAY_WIDTH: f64 = 800.0;
const OVERLAY_HEIGHT: f64 = 160.0;
const OVERLAY_BOTTOM_MARGIN: f64 = 60.0;

fn calculate_default_overlay_position(
    overlay: &tauri::WebviewWindow,
) -> Result<tauri::Position, String> {
    let monitor = overlay
        .primary_monitor()
        .map_err(|e| e.to_string())?
        .ok_or_else(|| "Failed to query primary monitor".to_string())?;
    let size = monitor.size();
    let scale = monitor.scale_factor();
    let screen_w = (size.width as f64) / scale;
    let screen_h = (size.height as f64) / scale;
    let x = (screen_w - OVERLAY_WIDTH) / 2.0;
    let y = screen_h - OVERLAY_HEIGHT - OVERLAY_BOTTOM_MARGIN;
    Ok(tauri::Position::Logical(tauri::LogicalPosition::new(x, y)))
}

pub struct AppState {
    pub overlay_state: Mutex<OverlayState>,
    pub diff_detector: Mutex<FrameDiffDetector>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            overlay_state: Mutex::new(OverlayState::default()),
            diff_detector: Mutex::new(FrameDiffDetector::default()),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct SystemInfo {
    pub app_name: String,
    pub version: String,
    pub architecture: String,
    pub status: String,
}

#[tauri::command]
fn get_system_info() -> SystemInfo {
    SystemInfo {
        app_name: "Subterranean Staircase".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        architecture: std::env::consts::ARCH.to_string(),
        status: "Core Online".to_string(),
    }
}

#[tauri::command]
fn ping(message: String) -> String {
    format!(
        "Pong from Rust core! Received: '{}' on architecture: {}",
        message,
        std::env::consts::ARCH
    )
}

#[tauri::command]
fn get_capture_targets() -> Result<CaptureTargets, String> {
    CaptureEngine::list_targets()
}

#[tauri::command]
fn capture_preview_frame(
    window_id: Option<u32>,
    monitor_id: Option<u32>,
    roi: Option<CaptureRoi>,
) -> Result<String, String> {
    let img = match window_id {
        Some(win_id) => CaptureEngine::capture_window(win_id, roi.as_ref())?,
        None => CaptureEngine::capture_screen(monitor_id, roi.as_ref())?,
    };

    let preview_img = if img.width() > 640 {
        let aspect = img.height() as f32 / img.width() as f32;
        let new_w = 640;
        let new_h = ((640.0 * aspect) as u32).max(1);
        image::imageops::resize(&img, new_w, new_h, image::imageops::FilterType::Nearest)
    } else {
        img
    };

    CaptureEngine::to_base64_jpeg(&preview_img, 65)
}

#[tauri::command]
fn evaluate_frame_diff(
    state: tauri::State<'_, AppState>,
    window_id: Option<u32>,
    monitor_id: Option<u32>,
    roi: Option<CaptureRoi>,
    threshold: Option<f32>,
) -> Result<DiffResult, String> {
    let img = match window_id {
        Some(win_id) => CaptureEngine::capture_window(win_id, roi.as_ref())?,
        None => CaptureEngine::capture_screen(monitor_id, roi.as_ref())?,
    };
    let mut detector = state.diff_detector.lock().map_err(|e| e.to_string())?;
    Ok(detector.compare(&img, threshold))
}

#[derive(Debug, Clone, Serialize, serde::Deserialize)]
pub struct PreviewTickResult {
    pub preview_data_url: String,
    pub diff: DiffResult,
}

#[tauri::command]
fn capture_preview_and_diff(
    state: tauri::State<'_, AppState>,
    window_id: Option<u32>,
    monitor_id: Option<u32>,
    roi: Option<CaptureRoi>,
    threshold: Option<f32>,
) -> Result<PreviewTickResult, String> {
    let img = match window_id {
        Some(win_id) => CaptureEngine::capture_window(win_id, roi.as_ref())?,
        None => CaptureEngine::capture_screen(monitor_id, roi.as_ref())?,
    };

    let diff = {
        let mut detector = state.diff_detector.lock().map_err(|e| e.to_string())?;
        detector.compare(&img, threshold)
    };

    let preview_img = if img.width() > 640 {
        let aspect = img.height() as f32 / img.width() as f32;
        let new_w = 640;
        let new_h = ((640.0 * aspect) as u32).max(1);
        image::imageops::resize(&img, new_w, new_h, image::imageops::FilterType::Nearest)
    } else {
        img
    };

    let preview_data_url = CaptureEngine::to_base64_jpeg(&preview_img, 65)?;

    Ok(PreviewTickResult {
        preview_data_url,
        diff,
    })
}

#[tauri::command]
fn emit_subtitle(
    app: tauri::AppHandle,
    text: String,
    duration_ms: Option<u64>,
) -> Result<(), String> {
    let payload = SubtitlePayload {
        text,
        duration_ms,
    };
    if let Some(overlay) = app.get_webview_window("overlay") {
        overlay
            .emit("subtitle_update", &payload)
            .map_err(|e| e.to_string())
    } else {
        Err("Overlay window not found".to_string())
    }
}

#[tauri::command]
fn clear_subtitle(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        overlay
            .emit("subtitle_clear", ())
            .map_err(|e| e.to_string())
    } else {
        Err("Overlay window not found".to_string())
    }
}

#[tauri::command]
fn toggle_overlay_interactive(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    interactive: bool,
) -> Result<bool, String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        overlay
            .set_ignore_cursor_events(!interactive)
            .map_err(|e| e.to_string())?;

        {
            let mut st = state.overlay_state.lock().map_err(|e| e.to_string())?;
            st.is_interactive = interactive;
        }

        overlay
            .emit("overlay_interactive_changed", interactive)
            .map_err(|e| e.to_string())?;

        Ok(interactive)
    } else {
        Err("Overlay window not found".to_string())
    }
}

#[tauri::command]
fn toggle_overlay_visibility(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    visible: bool,
) -> Result<bool, String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        if visible {
            overlay.show().map_err(|e| e.to_string())?;
        } else {
            overlay.hide().map_err(|e| e.to_string())?;
        }

        let mut st = state.overlay_state.lock().map_err(|e| e.to_string())?;
        st.is_visible = visible;

        Ok(visible)
    } else {
        Err("Overlay window not found".to_string())
    }
}

#[tauri::command]
fn reset_overlay_position(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        let pos = calculate_default_overlay_position(&overlay)?;
        overlay.set_position(pos).map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("Overlay window not found".to_string())
    }
}

#[tauri::command]
fn update_overlay_style(
    app: tauri::AppHandle,
    state: tauri::State<'_, AppState>,
    style: OverlayStyle,
) -> Result<(), String> {
    if let Some(overlay) = app.get_webview_window("overlay") {
        overlay
            .emit("overlay_style_changed", &style)
            .map_err(|e| e.to_string())?;

        let mut st = state.overlay_state.lock().map_err(|e| e.to_string())?;
        st.style = style;
        Ok(())
    } else {
        Err("Overlay window not found".to_string())
    }
}

#[tauri::command]
fn get_overlay_state(state: tauri::State<'_, AppState>) -> Result<OverlayState, String> {
    let st = state.overlay_state.lock().map_err(|e| e.to_string())?;
    Ok(st.clone())
}

pub fn run() -> tauri::Result<()> {
    tauri::Builder::default()
        .manage(AppState::default())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            if let Some(overlay_win) = app.get_webview_window("overlay") {
                let _ = overlay_win.set_ignore_cursor_events(true);

                if let Ok(pos) = calculate_default_overlay_position(&overlay_win) {
                    let _ = overlay_win.set_position(pos);
                }

                #[cfg(target_os = "macos")]
                {
                    if let Ok(ns_win) = overlay_win.ns_window() {
                        unsafe {
                            overlay::configure_macos_fullscreen_overlay(ns_win);
                        }
                    }
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_system_info,
            ping,
            get_capture_targets,
            capture_preview_frame,
            evaluate_frame_diff,
            capture_preview_and_diff,
            emit_subtitle,
            clear_subtitle,
            toggle_overlay_interactive,
            toggle_overlay_visibility,
            reset_overlay_position,
            update_overlay_style,
            get_overlay_state
        ])
        .run(tauri::generate_context!())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_system_info_metadata() {
        let info = get_system_info();
        assert_eq!(info.app_name, "Subterranean Staircase");
        assert_eq!(info.version, env!("CARGO_PKG_VERSION"));
        assert_eq!(info.status, "Core Online");
        assert!(!info.architecture.is_empty());
    }

    #[test]
    fn test_ping_response() {
        let reply = ping("Hello Tauri".to_string());
        assert!(reply.contains("Pong from Rust core!"));
        assert!(reply.contains("Hello Tauri"));
    }

    #[test]
    fn test_app_state_initialization() {
        let state = AppState::default();
        let overlay = state.overlay_state.lock().unwrap();
        assert!(overlay.is_visible);
        assert!(!overlay.is_interactive);
        assert_eq!(overlay.style.font_size, 24);
    }
}
