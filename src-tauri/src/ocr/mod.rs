//! Native Rust Optical Character Recognition (OCR) Engine
//!
//! Powered by:
//! - DBNet text detection with aspect-preserving resize & polygon unclip (ratio 2.0)
//! - SVTR / PP-OCR text recognition with native Rust CTC greedy decoding
//! - Dual-band screen spatial filtering & progressive sentence debouncing (0.12s)

pub mod ctc;
pub mod dbnet;
pub mod rec;
pub mod spatial;

use image::RgbaImage;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::Instant;

use ctc::CtcDecoder;
use dbnet::{DbNetConfig, DbNetDetector};
use rec::TextRecognizer;
use spatial::{DebounceStatus, DualBandSpatialFilter, SentenceDebouncer};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SubtitleBox {
    pub points: [[f32; 2]; 4],
}

impl SubtitleBox {
    pub fn new(points: [[f32; 2]; 4]) -> Self {
        Self { points }
    }

    pub fn center_y(&self) -> f32 {
        (self.points[0][1] + self.points[1][1] + self.points[2][1] + self.points[3][1]) / 4.0
    }

    pub fn center_x(&self) -> f32 {
        (self.points[0][0] + self.points[1][0] + self.points[2][0] + self.points[3][0]) / 4.0
    }

    pub fn min_x(&self) -> f32 {
        self.points.iter().map(|p| p[0]).fold(f32::INFINITY, f32::min)
    }

    pub fn max_x(&self) -> f32 {
        self.points.iter().map(|p| p[0]).fold(f32::NEG_INFINITY, f32::max)
    }

    pub fn min_y(&self) -> f32 {
        self.points.iter().map(|p| p[1]).fold(f32::INFINITY, f32::min)
    }

    pub fn max_y(&self) -> f32 {
        self.points.iter().map(|p| p[1]).fold(f32::NEG_INFINITY, f32::max)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OcrDetection {
    pub text: String,
    pub confidence: f32,
    pub box_points: SubtitleBox,
    pub timestamp: f64,
}

pub struct OcrEngine {
    detector: Option<DbNetDetector>,
    recognizer: Option<TextRecognizer>,
    spatial_filter: DualBandSpatialFilter,
    debouncer: Mutex<SentenceDebouncer>,
}

impl OcrEngine {
    /// Initialize OCR engine by discovering models from standard search paths.
    pub fn new_default() -> Self {
        let (det_path, rec_path) = Self::find_default_models();
        Self::new(det_path, rec_path)
    }

    /// Initialize OCR engine with specific detection and recognition model paths.
    pub fn new(det_path: Option<PathBuf>, rec_path: Option<PathBuf>) -> Self {
        let detector = det_path.and_then(|p| {
            if p.exists() {
                DbNetDetector::new(&p, DbNetConfig::default()).ok()
            } else {
                None
            }
        });

        let recognizer = rec_path.and_then(|p| {
            if p.exists() {
                TextRecognizer::new(&p).ok()
            } else {
                None
            }
        });

        Self {
            detector,
            recognizer,
            spatial_filter: DualBandSpatialFilter::default(),
            debouncer: Mutex::new(SentenceDebouncer::default()),
        }
    }

    /// Construct a lightweight mock engine for tests without loaded ONNX sessions.
    pub fn without_models() -> Self {
        Self {
            detector: Some(DbNetDetector::without_session(DbNetConfig::default())),
            recognizer: Some(TextRecognizer::with_decoder(CtcDecoder::new(vec![]))),
            spatial_filter: DualBandSpatialFilter::default(),
            debouncer: Mutex::new(SentenceDebouncer::default()),
        }
    }

    /// Check whether both neural models are loaded and ready for inference.
    pub fn is_ready(&self) -> bool {
        self.detector.is_some() && self.recognizer.is_some()
    }

    /// Locate default models across standard search locations.
    pub fn find_default_models() -> (Option<PathBuf>, Option<PathBuf>) {
        let candidate_dirs = [
            PathBuf::from("models"),
            PathBuf::from("../models"),
            dirs::data_local_dir()
                .map(|d| d.join("subterranean-staircase").join("models"))
                .unwrap_or_else(|| PathBuf::from(".")),
            PathBuf::from(".venv/lib/python3.10/site-packages/rapidocr_onnxruntime/models"),
            PathBuf::from("../.venv/lib/python3.10/site-packages/rapidocr_onnxruntime/models"),
        ];

        let mut det_path = None;
        let mut rec_path = None;

        for dir in &candidate_dirs {
            let det = dir.join("ch_PP-OCRv4_det_infer.onnx");
            if det.exists() && det_path.is_none() {
                det_path = Some(det);
            }
            let rec = dir.join("ch_PP-OCRv4_rec_infer.onnx");
            if rec.exists() && rec_path.is_none() {
                rec_path = Some(rec);
            }
        }

        (det_path, rec_path)
    }

    /// Perform end-to-end OCR text detection and recognition on an image buffer.
    pub fn process_image(&self, image: &RgbaImage) -> Result<Vec<OcrDetection>, String> {
        let (orig_w, orig_h) = (image.width(), image.height());
        if orig_w == 0 || orig_h == 0 {
            return Ok(Vec::new());
        }

        let detector = self
            .detector
            .as_ref()
            .ok_or_else(|| "OCR detector model is not initialized".to_string())?;

        let recognizer = self
            .recognizer
            .as_ref()
            .ok_or_else(|| "OCR recognizer model is not initialized".to_string())?;

        // 1. Detect candidate subtitle boxes
        let boxes = detector.detect(image)?;
        if boxes.is_empty() {
            return Ok(Vec::new());
        }

        // 2. Recognize text within each detected box
        let mut raw_detections = Vec::with_capacity(boxes.len());
        for (sub_box, box_conf) in boxes {
            let strip = TextRecognizer::crop_box(image, &sub_box);
            if strip.width() < 5 || strip.height() < 5 {
                continue;
            }

            let (text, rec_conf) = recognizer.recognize_strip(&strip)?;
            let trimmed = text.trim();
            if trimmed.is_empty() {
                continue;
            }

            // Blended confidence: geometric detection confidence * text recognition confidence
            let final_conf = (box_conf * 0.4) + (rec_conf * 0.6);

            raw_detections.push(OcrDetection {
                text: trimmed.to_string(),
                confidence: final_conf,
                box_points: sub_box,
                timestamp: 0.0,
            });
        }

        // 3. Spatial filtering (Dual-Band top/bottom priority & reading-order sorting)
        let filtered = self.spatial_filter.filter(&raw_detections, orig_h as f32);
        Ok(filtered)
    }

    /// Combine detected subtitle lines into a consolidated sentence string.
    pub fn consolidate_detections(detections: &[OcrDetection]) -> String {
        let lines: Vec<&str> = detections.iter().map(|d| d.text.trim()).filter(|t| !t.is_empty()).collect();
        lines.join(" ")
    }

    /// Evaluate temporal debouncing on an extracted sentence.
    pub fn debounce_sentence(&self, sentence: &str) -> DebounceStatus {
        if let Ok(mut debouncer) = self.debouncer.lock() {
            debouncer.process(sentence, Instant::now())
        } else {
            DebounceStatus::Ready(sentence.trim().to_string())
        }
    }

    /// Reset sentence debouncer state.
    pub fn reset_debouncer(&self) {
        if let Ok(mut debouncer) = self.debouncer.lock() {
            debouncer.reset();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn test_subtitle_box_geometry() {
        let sbox = SubtitleBox::new([[10.0, 20.0], [90.0, 20.0], [90.0, 60.0], [10.0, 60.0]]);
        assert_eq!(sbox.center_x(), 50.0);
        assert_eq!(sbox.center_y(), 40.0);
        assert_eq!(sbox.min_x(), 10.0);
        assert_eq!(sbox.max_x(), 90.0);
        assert_eq!(sbox.min_y(), 20.0);
        assert_eq!(sbox.max_y(), 60.0);
    }

    #[test]
    fn test_consolidate_detections() {
        let d1 = OcrDetection {
            text: "Hello".to_string(),
            confidence: 0.95,
            box_points: SubtitleBox::new([[0.0, 0.0]; 4]),
            timestamp: 0.0,
        };
        let d2 = OcrDetection {
            text: "world".to_string(),
            confidence: 0.92,
            box_points: SubtitleBox::new([[0.0, 0.0]; 4]),
            timestamp: 0.0,
        };
        let res = OcrEngine::consolidate_detections(&[d1, d2]);
        assert_eq!(res, "Hello world");
    }

    #[test]
    fn test_ocr_engine_without_models() {
        let engine = OcrEngine::without_models();
        let deb = engine.debounce_sentence("Test phrase");
        assert_eq!(deb, DebounceStatus::Ready("Test phrase".to_string()));
    }

    #[test]
    fn test_ocr_engine_real_inference_benchmark() {
        let img_path = if Path::new("tests/fixtures/test_subtitle.png").exists() {
            PathBuf::from("tests/fixtures/test_subtitle.png")
        } else if Path::new("../tests/fixtures/test_subtitle.png").exists() {
            PathBuf::from("../tests/fixtures/test_subtitle.png")
        } else {
            return;
        };

        let engine = OcrEngine::new_default();
        if !engine.is_ready() {
            println!("Engine not ready: detector or recognizer missing");
            return;
        }

        let dynamic_img = image::open(&img_path).expect("open test image");
        let rgba_img = dynamic_img.to_rgba8();

        let t0 = Instant::now();
        let detections = engine.process_image(&rgba_img).expect("process image");
        let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;

        assert!(!detections.is_empty(), "Expected at least one detection");
        let recognized_text = OcrEngine::consolidate_detections(&detections);
        assert!(
            recognized_text.contains("HELLO") || recognized_text.contains("WORLD"),
            "Expected 'HELLO WORLD', got: {}",
            recognized_text
        );
        println!("OCR End-to-end Latency: {:.2} ms | Text: '{}'", elapsed_ms, recognized_text);
    }

    #[test]
    fn test_benchmark_dataset_manifest_integrity() {
        let manifest_path = if Path::new("tests/fixtures/benchmark/dataset_manifest.json").exists() {
            PathBuf::from("tests/fixtures/benchmark/dataset_manifest.json")
        } else if Path::new("../tests/fixtures/benchmark/dataset_manifest.json").exists() {
            PathBuf::from("../tests/fixtures/benchmark/dataset_manifest.json")
        } else {
            return;
        };

        let content = std::fs::read_to_string(&manifest_path).expect("read manifest");
        let parsed: serde_json::Value = serde_json::from_str(&content).expect("parse json");
        let list = parsed.as_array().expect("array");
        assert_eq!(list.len(), 25, "Expected 25 benchmark scenarios");
    }
}
