//! Spatial Intelligence, Reading-Order Clustering & Sentence Debouncing
//!
//! Provides dual-band screen filtering, natural 2D reading-order sorting,
//! and temporal sentence debouncing (0.12s cooldown) for real-time video subtitles.

use std::time::{Duration, Instant};
use super::OcrDetection;

#[derive(Debug, Clone)]
pub struct DualBandSpatialFilter {
    pub top_band_ratio: f32,
    pub bottom_band_ratio: f32,
    pub min_confidence: f32,
    pub min_text_length: usize,
    pub allow_central_band: bool,
}

impl Default for DualBandSpatialFilter {
    fn default() -> Self {
        Self {
            top_band_ratio: 0.20,
            bottom_band_ratio: 0.30,
            min_confidence: 0.40,
            min_text_length: 1,
            allow_central_band: false,
        }
    }
}

impl DualBandSpatialFilter {
    pub fn new(top_band_ratio: f32, bottom_band_ratio: f32, min_confidence: f32) -> Self {
        Self {
            top_band_ratio: top_band_ratio.clamp(0.01, 0.49),
            bottom_band_ratio: bottom_band_ratio.clamp(0.01, 0.49),
            min_confidence: min_confidence.clamp(0.0, 1.0),
            min_text_length: 1,
            allow_central_band: false,
        }
    }

    /// Filter a set of raw detections according to vertical screen boundaries.
    /// `frame_height`: Total pixel height of the captured frame/ROI.
    /// If `frame_height < 400.0` or `allow_central_band` is true, central screening is bypassed.
    pub fn filter(&self, detections: &[OcrDetection], frame_height: f32) -> Vec<OcrDetection> {
        if detections.is_empty() || frame_height <= 0.0 {
            return Vec::new();
        }

        let is_compact_roi = frame_height < 400.0;
        let top_cutoff = frame_height * self.top_band_ratio;
        let bottom_cutoff = frame_height * (1.0 - self.bottom_band_ratio);

        let mut filtered: Vec<OcrDetection> = detections
            .iter()
            .filter(|d| {
                let trimmed = d.text.trim();
                if trimmed.len() < self.min_text_length || d.confidence < self.min_confidence {
                    return false;
                }
                if is_compact_roi || self.allow_central_band {
                    return true;
                }
                let cy = d.box_points.center_y();
                cy <= top_cutoff || cy >= bottom_cutoff
            })
            .cloned()
            .collect();

        // Sort in natural reading order
        sort_reading_order(&mut filtered, 20.0);
        filtered
    }
}

/// Sort detected text blocks in natural reading order:
/// Line-quantized top-to-bottom, left-to-right within the same line.
pub fn sort_reading_order(detections: &mut [OcrDetection], line_bin_height: f32) {
    let bin_size = line_bin_height.max(5.0);
    detections.sort_by(|a, b| {
        let bin_a = (a.box_points.center_y() / bin_size).round() as i32;
        let bin_b = (b.box_points.center_y() / bin_size).round() as i32;
        if bin_a != bin_b {
            bin_a.cmp(&bin_b)
        } else {
            let x_a = a.box_points.min_x();
            let x_b = b.box_points.min_x();
            x_a.partial_cmp(&x_b).unwrap_or(std::cmp::Ordering::Equal)
        }
    });
}

#[derive(Debug, PartialEq)]
pub enum DebounceStatus {
    /// Sentence is currently accumulating character fragments; delay translation.
    Debouncing,
    /// Sentence is stabilized and ready for translation dispatch.
    Ready(String),
    /// Sentence is identical to the previously dispatched line (keep-alive, don't retranslate).
    Unchanged(String),
    /// Frame is empty / no dialogue detected.
    Empty,
}

/// Progressive sentence debouncer to aggregate rapid character-by-character updates.
pub struct SentenceDebouncer {
    cooldown: Duration,
    pending_sentence: String,
    pending_time: Option<Instant>,
    last_dispatched: String,
}

impl Default for SentenceDebouncer {
    fn default() -> Self {
        Self::new(Duration::from_millis(120))
    }
}

impl SentenceDebouncer {
    pub fn new(cooldown: Duration) -> Self {
        Self {
            cooldown,
            pending_sentence: String::new(),
            pending_time: None,
            last_dispatched: String::new(),
        }
    }

    /// Process incoming raw sentence text with temporal debouncing.
    pub fn process(&mut self, raw_sentence: &str, now: Instant) -> DebounceStatus {
        let trimmed = raw_sentence.trim();
        if trimmed.is_empty() {
            self.pending_sentence.clear();
            self.pending_time = None;
            return DebounceStatus::Empty;
        }

        if trimmed == self.last_dispatched {
            return DebounceStatus::Unchanged(trimmed.to_string());
        }

        // Check if incoming text is an immediate streaming extension of previous text
        let is_extension = !self.pending_sentence.is_empty()
            && trimmed.starts_with(&self.pending_sentence)
            && trimmed.len() > self.pending_sentence.len();

        if let Some(prev_time) = self.pending_time {
            if is_extension && now.duration_since(prev_time) < self.cooldown {
                self.pending_sentence = trimmed.to_string();
                self.pending_time = Some(now);
                return DebounceStatus::Debouncing;
            }
        }

        // Sentence has stabilized or is a new phrase
        self.pending_sentence = trimmed.to_string();
        self.pending_time = Some(now);
        self.last_dispatched = trimmed.to_string();
        DebounceStatus::Ready(trimmed.to_string())
    }

    /// Force reset all tracker state (e.g. upon scene change or capture restart).
    pub fn reset(&mut self) {
        self.pending_sentence.clear();
        self.pending_time = None;
        self.last_dispatched.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ocr::SubtitleBox;

    fn dummy_detection(text: &str, cx: f32, cy: f32, conf: f32) -> OcrDetection {
        OcrDetection {
            text: text.to_string(),
            confidence: conf,
            box_points: SubtitleBox::new([
                [cx - 50.0, cy - 10.0],
                [cx + 50.0, cy - 10.0],
                [cx + 50.0, cy + 10.0],
                [cx - 50.0, cy + 10.0],
            ]),
            timestamp: 0.0,
        }
    }

    #[test]
    fn test_dual_band_spatial_filter() {
        let filter = DualBandSpatialFilter::default();
        let frame_h = 1000.0;
        // Top cutoff = 200.0, Bottom cutoff = 700.0
        let top_det = dummy_detection("Top Speaker", 500.0, 150.0, 0.95);
        let center_noise = dummy_detection("Center Movie Logo", 500.0, 500.0, 0.98);
        let bottom_sub = dummy_detection("Bottom Dialogue", 500.0, 850.0, 0.95);
        let low_conf = dummy_detection("Low Conf Bottom", 500.0, 850.0, 0.20);

        let filtered = filter.filter(&[top_det, center_noise, bottom_sub, low_conf], frame_h);
        assert_eq!(filtered.len(), 2);
        assert_eq!(filtered[0].text, "Top Speaker");
        assert_eq!(filtered[1].text, "Bottom Dialogue");
    }

    #[test]
    fn test_reading_order_sorting() {
        // Multi-column or two lines:
        // Line 1: Word A (left), Word B (right) at y = 100
        // Line 2: Word C at y = 140
        let word_b = dummy_detection("World", 300.0, 100.0, 0.9);
        let word_a = dummy_detection("Hello", 100.0, 102.0, 0.9);
        let word_c = dummy_detection("Next Line", 100.0, 140.0, 0.9);

        let mut list = vec![word_c, word_b, word_a];
        sort_reading_order(&mut list, 20.0);

        assert_eq!(list[0].text, "Hello");
        assert_eq!(list[1].text, "World");
        assert_eq!(list[2].text, "Next Line");
    }

    #[test]
    fn test_sentence_debouncer_flow() {
        let mut debouncer = SentenceDebouncer::new(Duration::from_millis(120));
        let t0 = Instant::now();

        // 1. Initial word fragment
        let s1 = debouncer.process("I", t0);
        assert_eq!(s1, DebounceStatus::Ready("I".to_string()));

        // 2. Rapid typing extension after 30ms (< 120ms) -> Debouncing
        let t1 = t0 + Duration::from_millis(30);
        let s2 = debouncer.process("I remember", t1);
        assert_eq!(s2, DebounceStatus::Debouncing);

        // 3. Another rapid typing extension after 50ms (< 120ms) -> Debouncing
        let t2 = t1 + Duration::from_millis(50);
        let s3 = debouncer.process("I remember everything", t2);
        assert_eq!(s3, DebounceStatus::Debouncing);

        // 4. Paused for 150ms (> 120ms cooldown) -> Ready
        let t3 = t2 + Duration::from_millis(150);
        let s4 = debouncer.process("I remember everything", t3);
        assert_eq!(s4, DebounceStatus::Ready("I remember everything".to_string()));

        // 5. Subsequent frames with same text -> Unchanged
        let t4 = t3 + Duration::from_millis(100);
        let s5 = debouncer.process("I remember everything", t4);
        assert_eq!(s5, DebounceStatus::Unchanged("I remember everything".to_string()));
    }
}
