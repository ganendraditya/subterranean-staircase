pub mod cache;
pub mod capture;
pub mod diff;
pub mod ocr;
pub mod overlay;
pub mod translate;

use std::sync::{Arc, Mutex};
use tauri::{Emitter, Manager};

use cache::TranslationCache;
use capture::{CaptureEngine, CaptureRoi, CaptureTargets};
use diff::{DiffResult, FrameDiffDetector};
use ocr::{OcrDetection, OcrEngine};
use overlay::{OverlayState, OverlayStyle, SubtitlePayload};
use serde::{Deserialize, Serialize};
use std::time::Instant;
use translate::{LlmConfig, LlmTranslator, TranslationRequest, TranslationResponse};

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
    pub cache: Arc<TranslationCache>,
    pub llm_translator: LlmTranslator,
    pub llm_config: Mutex<LlmConfig>,
    pub ocr_engine: Arc<OcrEngine>,
}

impl Default for AppState {
    fn default() -> Self {
        let cache = Arc::new(TranslationCache::open_default().unwrap_or_else(|_| {
            TranslationCache::open_in_memory().expect("open fallback memory cache")
        }));
        let llm_translator = LlmTranslator::new(cache.clone());
        let llm_config = Mutex::new(LlmConfig::load());
        let ocr_engine = Arc::new(OcrEngine::new_default());
        Self {
            overlay_state: Mutex::new(OverlayState::default()),
            diff_detector: Mutex::new(FrameDiffDetector::default()),
            cache,
            llm_translator,
            llm_config,
            ocr_engine,
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

fn inherit_saved_api_key(target: &mut LlmConfig, source: &LlmConfig) {
    if target
        .api_key
        .as_ref()
        .map(|k| k.trim() == "••••••••" || k.trim().is_empty())
        .unwrap_or(true)
    {
        target.api_key = source.api_key.clone();
    }
}

#[tauri::command]
async fn translate_subtitle(
    state: tauri::State<'_, AppState>,
    request: TranslationRequest,
    config: Option<LlmConfig>,
) -> Result<TranslationResponse, String> {
    let active_config = match config {
        Some(mut cfg) => {
            let guard = state.llm_config.lock().map_err(|e| e.to_string())?;
            inherit_saved_api_key(&mut cfg, &guard);
            cfg
        }
        None => {
            let guard = state.llm_config.lock().map_err(|e| e.to_string())?;
            guard.clone()
        }
    };
    state.llm_translator.translate(&active_config, &request).await
}

#[tauri::command]
async fn test_llm_connection(
    state: tauri::State<'_, AppState>,
    config: Option<LlmConfig>,
) -> Result<String, String> {
    let active_config = match config {
        Some(mut cfg) => {
            let guard = state.llm_config.lock().map_err(|e| e.to_string())?;
            inherit_saved_api_key(&mut cfg, &guard);
            cfg
        }
        None => {
            let guard = state.llm_config.lock().map_err(|e| e.to_string())?;
            guard.clone()
        }
    };
    state.llm_translator.test_connection(&active_config).await
}

#[tauri::command]
fn get_llm_config(state: tauri::State<'_, AppState>) -> Result<LlmConfig, String> {
    let guard = state.llm_config.lock().map_err(|e| e.to_string())?;
    let mut safe_cfg = guard.clone();
    // Never expose raw plaintext secret to webview DOM
    if safe_cfg
        .api_key
        .as_ref()
        .map(|k| !k.trim().is_empty())
        .unwrap_or(false)
    {
        safe_cfg.api_key = Some("••••••••".to_string());
    } else {
        safe_cfg.api_key = None;
    }
    Ok(safe_cfg)
}

#[tauri::command]
fn save_llm_config(
    state: tauri::State<'_, AppState>,
    mut config: LlmConfig,
) -> Result<(), String> {
    {
        let guard = state.llm_config.lock().map_err(|e| e.to_string())?;
        inherit_saved_api_key(&mut config, &guard);
    }
    // File I/O outside lock to avoid contention on Tokio threads
    config.save()?;
    let mut guard = state.llm_config.lock().map_err(|e| e.to_string())?;
    *guard = config;
    Ok(())
}

#[tauri::command]
fn get_cache_stats(state: tauri::State<'_, AppState>) -> usize {
    state.cache.count()
}

#[tauri::command]
fn clear_translation_cache(state: tauri::State<'_, AppState>) -> Result<(), String> {
    state.cache.clear().map_err(|e| e.to_string())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrStatusPayload {
    pub is_ready: bool,
    pub det_model_present: bool,
    pub rec_model_present: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrResultPayload {
    pub detections: Vec<OcrDetection>,
    pub consolidated_text: String,
    pub latency_ms: f32,
    pub debounce_status: String,
}

#[tauri::command]
fn get_ocr_status(state: tauri::State<'_, AppState>) -> OcrStatusPayload {
    let is_ready = state.ocr_engine.is_ready();
    let (det, rec) = OcrEngine::find_default_models();
    OcrStatusPayload {
        is_ready,
        det_model_present: det.is_some(),
        rec_model_present: rec.is_some(),
    }
}

const MAX_BASE64_IMAGE_BYTES: usize = 15 * 1024 * 1024; // 15 MB base64 payload limit
const MAX_DECODED_IMAGE_PIXELS: u64 = 4096 * 4096; // 16 MegaPixels boundary limit

#[tauri::command]
async fn run_ocr_on_frame(
    state: tauri::State<'_, AppState>,
    image_base64: Option<String>,
    window_id: Option<u32>,
    monitor_id: Option<u32>,
    roi: Option<CaptureRoi>,
) -> Result<OcrResultPayload, String> {
    let t0 = Instant::now();
    let ocr_engine = state.ocr_engine.clone();

    // Move heavy capture, decoding, and neural inference onto Tokio blocking pool
    tauri::async_runtime::spawn_blocking(move || {
        let rgba_img = if let Some(b64) = image_base64 {
            let clean_b64 = if let Some(idx) = b64.find(',') {
                &b64[idx + 1..]
            } else {
                &b64
            };
            let trimmed = clean_b64.trim();
            if trimmed.len() > MAX_BASE64_IMAGE_BYTES {
                return Err("Base64 image payload exceeds maximum allowed size (15 MB)".to_string());
            }

            use base64::Engine;
            let decoded = base64::prelude::BASE64_STANDARD
                .decode(trimmed)
                .map_err(|e| format!("Base64 decode error: {e}"))?;
            let dyn_img = image::load_from_memory(&decoded)
                .map_err(|e| format!("Image decode error: {e}"))?;

            let (w, h) = (dyn_img.width() as u64, dyn_img.height() as u64);
            if w * h > MAX_DECODED_IMAGE_PIXELS {
                return Err(format!(
                    "Image resolution ({}x{}) exceeds maximum allowed pixels limit",
                    w, h
                ));
            }
            dyn_img.to_rgba8()
        } else if let Some(wid) = window_id {
            CaptureEngine::capture_window(wid, roi.as_ref())?
        } else {
            CaptureEngine::capture_screen(monitor_id, roi.as_ref())?
        };

        let detections = ocr_engine.process_image(&rgba_img)?;
        let latency_ms = t0.elapsed().as_secs_f32() * 1000.0;
        let consolidated = OcrEngine::consolidate_detections(&detections);
        let debounce_status_enum = ocr_engine.debounce_sentence(&consolidated);
        let debounce_status = match debounce_status_enum {
            ocr::spatial::DebounceStatus::Debouncing => "Debouncing (streaming)".to_string(),
            ocr::spatial::DebounceStatus::Ready(_) => "Ready (stabilized)".to_string(),
            ocr::spatial::DebounceStatus::Unchanged(_) => "Unchanged".to_string(),
            ocr::spatial::DebounceStatus::Empty => "Empty".to_string(),
        };

        Ok(OcrResultPayload {
            detections,
            consolidated_text: consolidated,
            latency_ms,
            debounce_status,
        })
    })
    .await
    .map_err(|e| format!("OCR execution task joined with error: {e}"))?
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
            get_overlay_state,
            translate_subtitle,
            test_llm_connection,
            get_llm_config,
            save_llm_config,
            get_cache_stats,
            clear_translation_cache,
            get_ocr_status,
            run_ocr_on_frame
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
        assert_eq!(state.cache.count(), 0);
        let _ = state.ocr_engine.is_ready();
    }
}
