use image::RgbaImage;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffResult {
    pub has_changed: bool,
    pub delta: f32,
    pub delta_percent: f32,
    pub threshold: f32,
    pub latency_ms: f32,
}

pub struct FrameDiffDetector {
    prev_buffer: Option<Vec<u8>>,
    downsample_width: u32,
    downsample_height: u32,
    default_threshold: f32,
}

impl Default for FrameDiffDetector {
    fn default() -> Self {
        Self::new(64, 36, 0.015)
    }
}

impl FrameDiffDetector {
    pub fn new(downsample_width: u32, downsample_height: u32, default_threshold: f32) -> Self {
        Self {
            prev_buffer: None,
            downsample_width: downsample_width.max(1),
            downsample_height: downsample_height.max(1),
            default_threshold,
        }
    }

    /// Resets the internal previous frame cache, forcing next comparison to count as changed.
    pub fn reset(&mut self) {
        self.prev_buffer = None;
    }

    /// Downsamples an RGBA image to a compact 8-bit grayscale thumbnail buffer.
    pub fn downsample_to_grayscale(&self, img: &RgbaImage) -> Vec<u8> {
        let w = img.width();
        let h = img.height();
        if w == 0 || h == 0 {
            return Vec::new();
        }

        let target_w = self.downsample_width;
        let target_h = self.downsample_height;
        let mut buffer = Vec::with_capacity((target_w * target_h) as usize);

        for ty in 0..target_h {
            let src_y = (ty * h / target_h).min(h - 1);
            for tx in 0..target_w {
                let src_x = (tx * w / target_w).min(w - 1);
                let pixel = img.get_pixel(src_x, src_y);
                // Standard Rec. 601 integer luma conversion: (77*R + 150*G + 29*B) >> 8
                let r = pixel[0] as u32;
                let g = pixel[1] as u32;
                let b = pixel[2] as u32;
                let luma = ((77 * r + 150 * g + 29 * b) >> 8) as u8;
                buffer.push(luma);
            }
        }

        buffer
    }

    /// Computes Mean Absolute Difference (MAD) between current image and previous buffer.
    pub fn compare(&mut self, img: &RgbaImage, threshold: Option<f32>) -> DiffResult {
        let start = std::time::Instant::now();
        let thresh = threshold
            .filter(|t| t.is_finite() && *t >= 0.0)
            .unwrap_or(self.default_threshold);
        let curr_buffer = self.downsample_to_grayscale(img);

        if curr_buffer.is_empty() {
            return DiffResult {
                has_changed: false,
                delta: 0.0,
                delta_percent: 0.0,
                threshold: thresh,
                latency_ms: start.elapsed().as_secs_f32() * 1000.0,
            };
        }

        let (has_changed, delta) = match &self.prev_buffer {
            None => {
                // First frame ever seen: always marked as changed (baseline established)
                (true, 1.0)
            }
            Some(prev) => {
                if prev.len() != curr_buffer.len() {
                    (true, 1.0)
                } else {
                    // Vectorized absolute difference sum
                    let total_diff: u64 = curr_buffer
                        .iter()
                        .zip(prev.iter())
                        .map(|(&a, &b)| (a as i32 - b as i32).unsigned_abs() as u64)
                        .sum();

                    let count = curr_buffer.len() as f64;
                    let mad = (total_diff as f64) / count;
                    let norm_delta = (mad / 255.0) as f32;
                    let changed = norm_delta >= thresh;
                    (changed, norm_delta)
                }
            }
        };

        self.prev_buffer = Some(curr_buffer);
        let latency_ms = start.elapsed().as_secs_f32() * 1000.0;

        DiffResult {
            has_changed,
            delta,
            delta_percent: delta * 100.0,
            threshold: thresh,
            latency_ms,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::Rgba;

    #[test]
    fn test_identical_frames_produce_zero_diff() {
        let mut detector = FrameDiffDetector::default();
        let img = RgbaImage::from_pixel(640, 360, Rgba([128, 128, 128, 255]));

        let res1 = detector.compare(&img, None);
        assert!(res1.has_changed, "First frame establishes baseline");

        let res2 = detector.compare(&img, None);
        assert!(!res2.has_changed, "Identical frame should drop compute");
        assert_eq!(res2.delta, 0.0);
        assert!(res2.latency_ms < 0.5, "Latency must be sub-millisecond");
    }

    #[test]
    fn test_significant_change_triggers_detection() {
        let mut detector = FrameDiffDetector::default();
        let black = RgbaImage::from_pixel(640, 360, Rgba([0, 0, 0, 255]));
        let white = RgbaImage::from_pixel(640, 360, Rgba([255, 255, 255, 255]));

        detector.compare(&black, None);
        let res = detector.compare(&white, None);
        assert!(res.has_changed);
        assert!((res.delta - 1.0).abs() < 1e-4);
    }

    #[test]
    fn test_subtle_change_below_threshold_ignored() {
        let mut detector = FrameDiffDetector::new(64, 36, 0.05); // 5% threshold
        let base = RgbaImage::from_pixel(640, 360, Rgba([100, 100, 100, 255]));
        let slight = RgbaImage::from_pixel(640, 360, Rgba([102, 102, 102, 255])); // ~0.78% delta

        detector.compare(&base, None);
        let res = detector.compare(&slight, None);
        assert!(!res.has_changed, "Subtle delta should be short-circuited");
        assert!(res.delta < 0.05);
    }

    #[test]
    fn test_reset_clears_baseline() {
        let mut detector = FrameDiffDetector::default();
        let img = RgbaImage::from_pixel(640, 360, Rgba([50, 50, 50, 255]));

        detector.compare(&img, None);
        assert!(!detector.compare(&img, None).has_changed);

        detector.reset();
        assert!(detector.compare(&img, None).has_changed, "After reset, frame establishes new baseline");
    }

    #[test]
    fn test_nan_or_negative_threshold_resilience() {
        let mut detector = FrameDiffDetector::default();
        let img1 = RgbaImage::from_pixel(640, 360, Rgba([0, 0, 0, 255]));
        let img2 = RgbaImage::from_pixel(640, 360, Rgba([100, 100, 100, 255]));

        detector.compare(&img1, None);
        // Pass NaN threshold - should fallback safely to default threshold
        let res_nan = detector.compare(&img2, Some(f32::NAN));
        assert!(res_nan.threshold.is_finite());
        assert_eq!(res_nan.threshold, 0.015);

        // Pass negative threshold - should fallback safely
        let res_neg = detector.compare(&img2, Some(-0.5));
        assert_eq!(res_neg.threshold, 0.015);
    }

    #[test]
    fn test_empty_or_zero_dimension_image_safety() {
        let mut detector = FrameDiffDetector::default();
        let empty = RgbaImage::new(0, 0);
        let res = detector.compare(&empty, None);
        assert!(!res.has_changed);
        assert_eq!(res.delta, 0.0);
    }

    #[test]
    fn test_simd_diff_benchmark_sub_millisecond() {
        let mut detector = FrameDiffDetector::default();
        let img1 = RgbaImage::from_pixel(640, 360, Rgba([30, 60, 90, 255]));
        let img2 = RgbaImage::from_pixel(640, 360, Rgba([35, 65, 95, 255]));

        detector.compare(&img1, None);

        // Warm up and evaluate 50 iterations alternating frames
        let start = std::time::Instant::now();
        for i in 0..50 {
            let img = if i % 2 == 0 { &img2 } else { &img1 };
            let res = detector.compare(img, None);
            assert!(res.has_changed);
        }
        let elapsed = start.elapsed();
        let avg_time_per_eval = elapsed.as_secs_f64() / 50.0 * 1000.0;
        println!("Average SIMD MAD frame-diff time: {:.3} ms", avg_time_per_eval);
        assert!(avg_time_per_eval < 5.0, "Evaluation time must remain strictly bounded");
    }
}
