//! Background Pipeline Orchestrator (Safe Rust)
//!
//! Coordinates the end-to-end real-time translation loop:
//! `CaptureEngine` -> `FrameDiffDetector (SIMD)` -> `OcrEngine` -> `LlmTranslator (with Offline Fallback)` -> `Subtitle Overlay Event`.
//!
//! Provides thread-safe lifecycle state management (start, pause, resume, stop)
//! and real-time telemetry metrics without memory leaks.

use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};

use crate::capture::{CaptureEngine, CaptureRoi};
use crate::diff::FrameDiffDetector;
use crate::ocr::spatial::DebounceStatus;
use crate::ocr::OcrEngine;
use crate::overlay::SubtitlePayload;
use crate::translate::{LlmConfig, LlmTranslator, TranslationRequest};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PipelineStatus {
    Stopped,
    Running,
    Paused,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineConfig {
    pub target_type: String, // "screen" or "window"
    pub target_id: u32,
    pub roi: Option<CaptureRoi>,
    pub fps_limit: u32,
    pub frame_diff_threshold: f32,
    pub source_lang: String,
    pub target_lang: String,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            target_type: "screen".to_string(),
            target_id: 0,
            roi: None,
            fps_limit: 10,
            frame_diff_threshold: 0.015,
            source_lang: "auto".to_string(),
            target_lang: "en".to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PipelineMetrics {
    pub status: PipelineStatus,
    pub fps: f32,
    pub total_frames: u64,
    pub skipped_frames: u64,
    pub ocr_invocations: u64,
    pub translations_count: u64,
    pub last_diff_delta: f32,
    pub last_ocr_latency_ms: f32,
    pub last_trans_latency_ms: f32,
    pub last_detected_text: String,
    pub last_translated_text: String,
    pub is_fallback: bool,
}

impl Default for PipelineMetrics {
    fn default() -> Self {
        Self {
            status: PipelineStatus::Stopped,
            fps: 0.0,
            total_frames: 0,
            skipped_frames: 0,
            ocr_invocations: 0,
            translations_count: 0,
            last_diff_delta: 0.0,
            last_ocr_latency_ms: 0.0,
            last_trans_latency_ms: 0.0,
            last_detected_text: String::new(),
            last_translated_text: String::new(),
            is_fallback: false,
        }
    }
}

pub struct PipelineController {
    config: Arc<Mutex<PipelineConfig>>,
    metrics: Arc<Mutex<PipelineMetrics>>,
    is_running: Arc<AtomicBool>,
    is_paused: Arc<AtomicBool>,
    stop_signal: Arc<AtomicBool>,
    worker_handle: Mutex<Option<std::thread::JoinHandle<()>>>,
    lifecycle_mutex: Mutex<()>,
}

impl Default for PipelineController {
    fn default() -> Self {
        Self::new()
    }
}

impl PipelineController {
    pub fn new() -> Self {
        Self {
            config: Arc::new(Mutex::new(PipelineConfig::default())),
            metrics: Arc::new(Mutex::new(PipelineMetrics::default())),
            is_running: Arc::new(AtomicBool::new(false)),
            is_paused: Arc::new(AtomicBool::new(false)),
            stop_signal: Arc::new(AtomicBool::new(false)),
            worker_handle: Mutex::new(None),
            lifecycle_mutex: Mutex::new(()),
        }
    }

    pub fn get_status(&self) -> PipelineStatus {
        if !self.is_running.load(Ordering::Relaxed) {
            PipelineStatus::Stopped
        } else if self.is_paused.load(Ordering::Relaxed) {
            PipelineStatus::Paused
        } else {
            PipelineStatus::Running
        }
    }

    pub fn get_metrics(&self) -> PipelineMetrics {
        let mut m = self.metrics.lock().map(|g| g.clone()).unwrap_or_default();
        m.status = self.get_status();
        m
    }

    pub fn update_config(&self, mut new_config: PipelineConfig) -> Result<(), String> {
        let clean_target = new_config.target_type.trim().to_lowercase();
        if clean_target != "window" && clean_target != "screen" {
            return Err("target_type must be 'screen' or 'window'".to_string());
        }
        new_config.target_type = clean_target;
        new_config.fps_limit = new_config.fps_limit.clamp(1, 30);
        new_config.frame_diff_threshold = new_config.frame_diff_threshold.clamp(0.001, 0.5);
        if let Ok(mut g) = self.config.lock() {
            *g = new_config;
        }
        Ok(())
    }

    pub fn pause(&self) -> Result<(), String> {
        let _guard = self.lifecycle_mutex.lock().map_err(|e| e.to_string())?;
        if !self.is_running.load(Ordering::Relaxed) {
            return Err("Pipeline is not running".to_string());
        }
        self.is_paused.store(true, Ordering::SeqCst);
        if let Ok(mut m) = self.metrics.lock() {
            m.status = PipelineStatus::Paused;
        }
        Ok(())
    }

    pub fn resume(&self) -> Result<(), String> {
        let _guard = self.lifecycle_mutex.lock().map_err(|e| e.to_string())?;
        if !self.is_running.load(Ordering::Relaxed) {
            return Err("Pipeline is not running".to_string());
        }
        self.is_paused.store(false, Ordering::SeqCst);
        if let Ok(mut m) = self.metrics.lock() {
            m.status = PipelineStatus::Running;
        }
        Ok(())
    }

    pub fn stop(&self) -> Result<(), String> {
        let _guard = self.lifecycle_mutex.lock().map_err(|e| e.to_string())?;
        if !self.is_running.load(Ordering::Relaxed) {
            return Ok(());
        }

        self.stop_signal.store(true, Ordering::SeqCst);

        let mut handle_guard = self.worker_handle.lock().map_err(|e| e.to_string())?;
        if let Some(handle) = handle_guard.take() {
            let _ = handle.join();
        }

        self.is_running.store(false, Ordering::SeqCst);
        self.is_paused.store(false, Ordering::SeqCst);

        if let Ok(mut m) = self.metrics.lock() {
            m.status = PipelineStatus::Stopped;
        }

        Ok(())
    }

    pub fn start(
        &self,
        app: tauri::AppHandle,
        ocr_engine: Arc<OcrEngine>,
        llm_translator: Arc<LlmTranslator>,
        llm_config: Arc<Mutex<LlmConfig>>,
        initial_config: Option<PipelineConfig>,
    ) -> Result<(), String> {
        let _guard = self.lifecycle_mutex.lock().map_err(|e| e.to_string())?;
        if self.is_running.load(Ordering::Relaxed) {
            return Err("Pipeline is already running".to_string());
        }

        if let Some(cfg) = initial_config {
            self.update_config(cfg)?;
        }

        // Reap any existing completed handle before spawning replacement
        {
            let mut handle_guard = self.worker_handle.lock().map_err(|e| e.to_string())?;
            if let Some(old_handle) = handle_guard.take() {
                let _ = old_handle.join();
            }
        }

        self.stop_signal.store(false, Ordering::SeqCst);
        self.is_running.store(true, Ordering::SeqCst);
        self.is_paused.store(false, Ordering::SeqCst);

        // Reset metrics
        if let Ok(mut m) = self.metrics.lock() {
            *m = PipelineMetrics {
                status: PipelineStatus::Running,
                ..Default::default()
            };
        }

        let config_arc = Arc::clone(&self.config);
        let metrics_arc = Arc::clone(&self.metrics);
        let is_running_arc = Arc::clone(&self.is_running);
        let is_paused_arc = Arc::clone(&self.is_paused);
        let stop_signal_arc = Arc::clone(&self.stop_signal);

        let spawn_res = std::thread::Builder::new()
            .name("pipeline-orchestrator".to_string())
            .spawn(move || {
                let mut diff_detector = FrameDiffDetector::default();
                let mut had_active_subtitle = false;
                let mut last_metrics_emit = Instant::now();
                let mut frames_in_second = 0u32;
                let mut fps_timer = Instant::now();

                while !stop_signal_arc.load(Ordering::Relaxed) {
                    let loop_start = Instant::now();

                    // 1. Paused check
                    if is_paused_arc.load(Ordering::Relaxed) {
                        std::thread::sleep(Duration::from_millis(50));
                        continue;
                    }

                    // 2. Read current configuration snapshot
                    let cfg = config_arc.lock().map(|c| c.clone()).unwrap_or_default();
                    let target_fps = cfg.fps_limit.clamp(1, 30);
                    let target_interval = Duration::from_millis(1000 / target_fps as u64);

                    // 3. Screen or Window Capture
                    let capture_res = if cfg.target_type == "window" {
                        CaptureEngine::capture_window(cfg.target_id, cfg.roi.as_ref())
                    } else {
                        CaptureEngine::capture_screen(Some(cfg.target_id), cfg.roi.as_ref())
                    };

                    let frame = match capture_res {
                        Ok(img) => img,
                        Err(_) => {
                            std::thread::sleep(Duration::from_millis(100));
                            continue;
                        }
                    };

                    frames_in_second += 1;
                    if fps_timer.elapsed() >= Duration::from_secs(1) {
                        let actual_fps = frames_in_second as f32 / fps_timer.elapsed().as_secs_f32();
                        if let Ok(mut m) = metrics_arc.lock() {
                            m.fps = actual_fps;
                        }
                        frames_in_second = 0;
                        fps_timer = Instant::now();
                    }

                    if let Ok(mut m) = metrics_arc.lock() {
                        m.total_frames += 1;
                    }

                    // 4. Perceptual SIMD Frame-Diff Check
                    let diff_res = diff_detector.compare(&frame, Some(cfg.frame_diff_threshold));
                    if let Ok(mut m) = metrics_arc.lock() {
                        m.last_diff_delta = diff_res.delta;
                    }

                    // Static frame gating: bypass 100% of OCR if frame has not changed
                    if !diff_res.has_changed {
                        if let Ok(mut m) = metrics_arc.lock() {
                            m.skipped_frames += 1;
                        }

                        // Broadcast telemetry even on static frames
                        if last_metrics_emit.elapsed() >= Duration::from_millis(500) {
                            let metrics_snapshot = metrics_arc.lock().map(|m| m.clone()).unwrap_or_default();
                            let _ = app.emit("pipeline_metrics", &metrics_snapshot);
                            last_metrics_emit = Instant::now();
                        }

                        // Maintain target FPS
                        let elapsed = loop_start.elapsed();
                        if elapsed < target_interval {
                            std::thread::sleep(target_interval - elapsed);
                        }
                        continue;
                    }

                    // 5. Neural OCR Inference
                    let ocr_start = Instant::now();
                    let ocr_res = ocr_engine.process_image(&frame);
                    let ocr_lat = ocr_start.elapsed().as_secs_f32() * 1000.0;

                    if let Ok(mut m) = metrics_arc.lock() {
                        m.ocr_invocations += 1;
                        m.last_ocr_latency_ms = ocr_lat;
                    }

                    let detections = match ocr_res {
                        Ok(d) => d,
                        Err(e) => {
                            eprintln!("[PIPELINE-OCR-ERR] OCR inference error: {e}");
                            let elapsed = loop_start.elapsed();
                            if elapsed < target_interval {
                                std::thread::sleep(target_interval - elapsed);
                            }
                            continue;
                        }
                    };

                    if detections.is_empty() {
                        // Subtitle cleared from screen
                        if had_active_subtitle {
                            if let Some(overlay) = app.get_webview_window("overlay") {
                                let _ = overlay.emit("subtitle_clear", ());
                            }
                            had_active_subtitle = false;
                            ocr_engine.reset_debouncer();
                            if let Ok(mut m) = metrics_arc.lock() {
                                m.last_detected_text.clear();
                                m.last_translated_text.clear();
                            }
                        }
                    } else {
                        let raw_sentence = OcrEngine::consolidate_detections(&detections);
                        let debounce = ocr_engine.debounce_sentence(&raw_sentence);

                        match debounce {
                            DebounceStatus::Ready(ready_text) => {
                                let active_cfg = llm_config.lock().map(|c| c.clone()).unwrap_or_default();
                                let req = TranslationRequest {
                                    source_text: ready_text.clone(),
                                    source_lang: cfg.source_lang.clone(),
                                    target_lang: cfg.target_lang.clone(),
                                };

                                let trans_res = llm_translator.translate_blocking(&active_cfg, &req);
                                if let Ok(res) = trans_res {
                                    had_active_subtitle = true;
                                    if let Ok(mut m) = metrics_arc.lock() {
                                        m.translations_count += 1;
                                        m.last_trans_latency_ms = res.latency_ms;
                                        m.last_detected_text = ready_text.clone();
                                        m.last_translated_text = res.translated_text.clone();
                                        m.is_fallback = res.is_fallback;
                                    }

                                    // Emit directly to floating overlay window
                                    if let Some(overlay) = app.get_webview_window("overlay") {
                                        let _ = overlay.emit(
                                            "subtitle_update",
                                            &SubtitlePayload {
                                                text: res.translated_text,
                                                duration_ms: Some(5000),
                                            },
                                        );
                                    }
                                }
                            }
                            DebounceStatus::Unchanged(_) => {
                                had_active_subtitle = true;
                            }
                            DebounceStatus::Debouncing | DebounceStatus::Empty => {}
                        }
                    }

                    // 6. Periodic telemetry broadcast to Control Center dashboard (every 500 ms)
                    if last_metrics_emit.elapsed() >= Duration::from_millis(500) {
                        let metrics_snapshot = metrics_arc.lock().map(|m| m.clone()).unwrap_or_default();
                        let _ = app.emit("pipeline_metrics", &metrics_snapshot);
                        last_metrics_emit = Instant::now();
                    }

                    // 7. Loop rate limiter
                    let elapsed = loop_start.elapsed();
                    if elapsed < target_interval {
                        std::thread::sleep(target_interval - elapsed);
                    }
                }

                is_running_arc.store(false, Ordering::SeqCst);
                if let Ok(mut m) = metrics_arc.lock() {
                    m.status = PipelineStatus::Stopped;
                    let _ = app.emit("pipeline_metrics", &*m);
                }
            });

        match spawn_res {
            Ok(handle) => {
                let mut handle_guard = self.worker_handle.lock().map_err(|e| e.to_string())?;
                *handle_guard = Some(handle);
                Ok(())
            }
            Err(e) => {
                self.is_running.store(false, Ordering::SeqCst);
                self.is_paused.store(false, Ordering::SeqCst);
                if let Ok(mut m) = self.metrics.lock() {
                    m.status = PipelineStatus::Stopped;
                }
                Err(format!("Failed to spawn pipeline worker thread: {e}"))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pipeline_controller_initial_state() {
        let controller = PipelineController::new();
        assert_eq!(controller.get_status(), PipelineStatus::Stopped);
        let m = controller.get_metrics();
        assert_eq!(m.total_frames, 0);
        assert_eq!(m.skipped_frames, 0);
    }

    #[test]
    fn test_pipeline_config_update() {
        let controller = PipelineController::new();
        let new_cfg = PipelineConfig {
            target_type: "window".to_string(),
            target_id: 42,
            roi: None,
            fps_limit: 15,
            frame_diff_threshold: 0.02,
            source_lang: "ja".to_string(),
            target_lang: "id".to_string(),
        };
        let mut bad_cfg = new_cfg.clone();
        bad_cfg.target_type = "invalid".to_string();
        assert!(controller.update_config(bad_cfg).is_err());

        assert!(controller.update_config(new_cfg).is_ok());
        let read_cfg = controller.config.lock().unwrap().clone();
        assert_eq!(read_cfg.target_id, 42);
        assert_eq!(read_cfg.fps_limit, 15);
        assert_eq!(read_cfg.source_lang, "ja");
    }

    #[test]
    fn test_pipeline_pause_resume_validation() {
        let controller = PipelineController::new();
        // Pausing when stopped should return an error
        assert!(controller.pause().is_err());
        assert!(controller.resume().is_err());
    }
}
