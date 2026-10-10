//! DBNet Neural Text Detection (ONNX Runtime + Safe Rust)
//!
//! Features:
//! - Aspect-ratio preserving letterbox scaling with `limit_type = "max"`
//! - Probability map binarization and contour tracking via `imageproc`
//! - Polygon expansion via `clipper2-rust` using `unclip_ratio = 2.0`
//! - Native minimum area bounding box calculation (rotating calipers)

use clipper2_rust::core::{Path64, Paths64, Point64};
use clipper2_rust::offset::{ClipperOffset, EndType, JoinType};
use image::{GrayImage, Luma, RgbaImage};
use imageproc::contours::find_contours;
use ndarray::Array4;
use ort::session::builder::GraphOptimizationLevel;
use ort::session::Session;
use std::path::Path;
use std::sync::Mutex;

use super::SubtitleBox;

#[derive(Debug, Clone)]
pub struct DbNetConfig {
    pub limit_side_len: u32,
    pub thresh: f32,
    pub box_thresh: f32,
    pub max_candidates: usize,
    pub unclip_ratio: f64,
}

impl Default for DbNetConfig {
    fn default() -> Self {
        Self {
            limit_side_len: 736,
            thresh: 0.3,
            box_thresh: 0.5,
            max_candidates: 1000,
            unclip_ratio: 2.0,
        }
    }
}

pub struct DbNetDetector {
    session: Option<Mutex<Session>>,
    pub config: DbNetConfig,
}

impl DbNetDetector {
    /// Initialize detector from ONNX model file.
    pub fn new<P: AsRef<Path>>(model_path: P, config: DbNetConfig) -> Result<Self, String> {
        let session = Session::builder()
            .map_err(|e| format!("Failed to create ONNX session builder: {e}"))?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|e| format!("Failed to set graph optimization level: {e}"))?
            .with_intra_threads(2)
            .map_err(|e| format!("Failed to set intra threads: {e}"))?
            .commit_from_file(model_path)
            .map_err(|e| format!("Failed to load DBNet ONNX model: {e}"))?;

        Ok(Self {
            session: Some(Mutex::new(session)),
            config,
        })
    }

    /// Construct detector without a loaded ONNX session (useful for unit tests and post-processing).
    pub fn without_session(config: DbNetConfig) -> Self {
        Self {
            session: None,
            config,
        }
    }

    /// Preprocess an RGBA image buffer into an NCHW [1, 3, H, W] float32 tensor
    /// scaled to multiples of 32 with limit_type = "max".
    /// Returns (tensor, resized_w, resized_h).
    pub fn preprocess(&self, image: &RgbaImage) -> (Array4<f32>, u32, u32) {
        let (orig_w, orig_h) = (image.width(), image.height());
        if orig_w == 0 || orig_h == 0 {
            return (Array4::<f32>::zeros((1, 3, 32, 32)), 32, 32);
        }

        let max_side = orig_w.max(orig_h);
        let ratio = if max_side > self.config.limit_side_len {
            self.config.limit_side_len as f32 / max_side as f32
        } else {
            1.0
        };

        let mut resize_w = ((orig_w as f32 * ratio) / 32.0).round() as u32 * 32;
        let mut resize_h = ((orig_h as f32 * ratio) / 32.0).round() as u32 * 32;
        resize_w = resize_w.max(32);
        resize_h = resize_h.max(32);

        let resized = image::imageops::resize(
            image,
            resize_w,
            resize_h,
            image::imageops::FilterType::Triangle,
        );

        let mut tensor = Array4::<f32>::zeros((1, 3, resize_h as usize, resize_w as usize));

        for y in 0..resize_h as usize {
            for x in 0..resize_w as usize {
                let p = resized.get_pixel(x as u32, y as u32);
                // PP-OCR standard normalization: (x / 255.0 - 0.5) / 0.5 = (x - 127.5) / 127.5
                tensor[[0, 0, y, x]] = (p[0] as f32 - 127.5) / 127.5;
                tensor[[0, 1, y, x]] = (p[1] as f32 - 127.5) / 127.5;
                tensor[[0, 2, y, x]] = (p[2] as f32 - 127.5) / 127.5;
            }
        }

        (tensor, resize_w, resize_h)
    }

    /// Detect subtitle boxes within an RGBA image.
    pub fn detect(&self, image: &RgbaImage) -> Result<Vec<(SubtitleBox, f32)>, String> {
        let (orig_w, orig_h) = (image.width(), image.height());
        if orig_w == 0 || orig_h == 0 {
            return Ok(Vec::new());
        }

        let (input_tensor, resize_w, resize_h) = self.preprocess(image);

        let session_mutex = self
            .session
            .as_ref()
            .ok_or_else(|| "DBNet ONNX session is not loaded".to_string())?;

        let mut session = session_mutex
            .lock()
            .map_err(|e| format!("Failed to lock DBNet ONNX session: {e}"))?;

        let tensor_val = ort::value::Tensor::from_array(input_tensor)
            .map_err(|e| format!("Failed to create input tensor value: {e}"))?;

        let inputs = ort::inputs![tensor_val];
        let outputs = session
            .run(inputs)
            .map_err(|e| format!("DBNet inference execution failed: {e}"))?;

        let (_shape, prob_slice) = outputs[0]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("Failed to extract DBNet output probability tensor: {e}"))?;

        Ok(self.postprocess(prob_slice, resize_w, resize_h, orig_w, orig_h))
    }

    /// Postprocess DBNet raw sigmoid output probability map to extract unclipped subtitle bounding boxes.
    pub fn postprocess(
        &self,
        prob_slice: &[f32],
        resize_w: u32,
        resize_h: u32,
        dest_w: u32,
        dest_h: u32,
    ) -> Vec<(SubtitleBox, f32)> {
        let total_pixels = (resize_w * resize_h) as usize;
        if prob_slice.len() < total_pixels || resize_w == 0 || resize_h == 0 {
            return Vec::new();
        }

        // 1. Create binary mask (thresh = 0.3)
        let mut mask_img = GrayImage::new(resize_w, resize_h);
        for y in 0..resize_h {
            for x in 0..resize_w {
                let idx = (y * resize_w + x) as usize;
                let val = prob_slice[idx];
                if val > self.config.thresh {
                    mask_img.put_pixel(x, y, Luma([255]));
                }
            }
        }

        // 2. Find contours via imageproc
        let contours = find_contours::<u32>(&mask_img);
        let mut results = Vec::new();

        let num_candidates = contours.len().min(self.config.max_candidates);
        for i in 0..num_candidates {
            let contour = &contours[i];
            if contour.points.len() < 4 {
                continue;
            }

            let pts: Vec<[f32; 2]> = contour
                .points
                .iter()
                .map(|p| [p.x as f32, p.y as f32])
                .collect();

            // Compute mini box
            let (mini_box, side) = min_area_rect(&pts);
            if side < 3.0 {
                continue;
            }

            // Calculate confidence score from probability map
            let score = box_score_fast(prob_slice, resize_w, resize_h, &mini_box);
            if score < self.config.box_thresh {
                continue;
            }

            // Unclip polygon expansion
            let unclipped_pts = unclip_polygon(&mini_box, self.config.unclip_ratio);
            let (final_box_resized, final_side) = min_area_rect(&unclipped_pts);
            if final_side < 4.0 {
                continue;
            }

            // Map box coordinates from resized (W, H) space back to original (dest_w, dest_h) space
            let scale_x = dest_w as f32 / resize_w as f32;
            let scale_y = dest_h as f32 / resize_h as f32;

            let mut mapped_points = [[0.0f32; 2]; 4];
            for k in 0..4 {
                mapped_points[k][0] = (final_box_resized[k][0] * scale_x)
                    .clamp(0.0, dest_w.saturating_sub(1) as f32);
                mapped_points[k][1] = (final_box_resized[k][1] * scale_y)
                    .clamp(0.0, dest_h.saturating_sub(1) as f32);
            }

            results.push((SubtitleBox::new(mapped_points), score));
        }

        results
    }
}

/// Calculate the area of a 2D polygon using the Shoelace formula.
pub fn polygon_area(pts: &[[f32; 2]]) -> f64 {
    let n = pts.len();
    if n < 3 {
        return 0.0;
    }
    let mut area = 0.0f64;
    for i in 0..n {
        let j = (i + 1) % n;
        area += pts[i][0] as f64 * pts[j][1] as f64;
        area -= pts[j][0] as f64 * pts[i][1] as f64;
    }
    (area / 2.0).abs()
}

/// Calculate the perimeter of a 2D polygon.
pub fn polygon_perimeter(pts: &[[f32; 2]]) -> f64 {
    let n = pts.len();
    if n < 2 {
        return 0.0;
    }
    let mut perimeter = 0.0f64;
    for i in 0..n {
        let j = (i + 1) % n;
        let dx = pts[j][0] - pts[i][0];
        let dy = pts[j][1] - pts[i][1];
        perimeter += ((dx * dx + dy * dy) as f64).sqrt();
    }
    perimeter
}

/// Expand polygon using `clipper2-rust` polygon offset algorithm with `unclip_ratio`.
/// Distance formula: D = Area * unclip_ratio / Perimeter.
pub fn unclip_polygon(box_pts: &[[f32; 2]; 4], unclip_ratio: f64) -> Vec<[f32; 2]> {
    let area = polygon_area(box_pts);
    let perimeter = polygon_perimeter(box_pts);

    if perimeter <= 1e-4 || area <= 1e-4 {
        return box_pts.to_vec();
    }

    let distance = (area * unclip_ratio) / perimeter;
    if distance <= 0.0 {
        return box_pts.to_vec();
    }

    let scale = 1000.0f64;
    let mut path = Path64::new();
    for pt in box_pts {
        path.push(Point64::new(
            (pt[0] as f64 * scale).round() as i64,
            (pt[1] as f64 * scale).round() as i64,
        ));
    }

    let mut offset = ClipperOffset::new(2.0, 0.25, false, false);
    offset.add_path(&path, JoinType::Round, EndType::Polygon);

    let mut solution = Paths64::new();
    offset.execute(distance * scale, &mut solution);

    if solution.is_empty() || solution[0].is_empty() {
        // Fallback: scale box around center
        let cx = (box_pts[0][0] + box_pts[1][0] + box_pts[2][0] + box_pts[3][0]) / 4.0;
        let cy = (box_pts[0][1] + box_pts[1][1] + box_pts[2][1] + box_pts[3][1]) / 4.0;
        let scale_factor = (1.0 + (distance as f32 / 20.0)).clamp(1.0, 2.5);
        return box_pts
            .iter()
            .map(|p| [cx + (p[0] - cx) * scale_factor, cy + (p[1] - cy) * scale_factor])
            .collect();
    }

    solution[0]
        .iter()
        .map(|pt| [(pt.x as f64 / scale) as f32, (pt.y as f64 / scale) as f32])
        .collect()
}

/// Checks whether point `p` is inside oriented convex polygon `quad`.
#[inline]
pub fn is_point_in_quad(p: [f32; 2], quad: &[[f32; 2]; 4]) -> bool {
    let mut sign = None;
    for i in 0..4 {
        let p1 = quad[i];
        let p2 = quad[(i + 1) % 4];
        let cross = (p2[0] - p1[0]) * (p[1] - p1[1]) - (p2[1] - p1[1]) * (p[0] - p1[0]);
        if cross.abs() > 1e-4 {
            let curr_sign = cross > 0.0;
            if let Some(s) = sign {
                if s != curr_sign {
                    return false;
                }
            } else {
                sign = Some(curr_sign);
            }
        }
    }
    true
}

/// Compute fast box average confidence score across probability bitmap inside oriented quad.
pub fn box_score_fast(
    prob_slice: &[f32],
    width: u32,
    height: u32,
    box_pts: &[[f32; 2]; 4],
) -> f32 {
    let min_x = box_pts.iter().map(|p| p[0]).fold(f32::INFINITY, f32::min).max(0.0) as u32;
    let max_x = box_pts.iter().map(|p| p[0]).fold(f32::NEG_INFINITY, f32::max).min((width.saturating_sub(1)) as f32) as u32;
    let min_y = box_pts.iter().map(|p| p[1]).fold(f32::INFINITY, f32::min).max(0.0) as u32;
    let max_y = box_pts.iter().map(|p| p[1]).fold(f32::NEG_INFINITY, f32::max).min((height.saturating_sub(1)) as f32) as u32;

    if min_x > max_x || min_y > max_y {
        return 0.0;
    }

    let mut sum = 0.0f32;
    let mut count = 0usize;

    for y in min_y..=max_y {
        let row_offset = (y * width) as usize;
        let y_f = y as f32 + 0.5;
        for x in min_x..=max_x {
            let x_f = x as f32 + 0.5;
            if is_point_in_quad([x_f, y_f], box_pts) {
                let idx = row_offset + x as usize;
                if idx < prob_slice.len() {
                    sum += prob_slice[idx];
                    count += 1;
                }
            }
        }
    }

    if count == 0 {
        0.0
    } else {
        sum / count as f32
    }
}

/// Compute 2D Convex Hull using Andrew's Monotone Chain algorithm.
pub fn convex_hull(mut pts: Vec<[f32; 2]>) -> Vec<[f32; 2]> {
    if pts.len() <= 3 {
        return pts;
    }
    pts.sort_by(|a, b| {
        a[0].partial_cmp(&b[0])
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| a[1].partial_cmp(&b[1]).unwrap_or(std::cmp::Ordering::Equal))
    });

    let cross = |o: &[f32; 2], a: &[f32; 2], b: &[f32; 2]| -> f32 {
        (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    };

    let mut lower = Vec::new();
    for p in &pts {
        while lower.len() >= 2 && cross(&lower[lower.len() - 2], &lower[lower.len() - 1], p) <= 0.0 {
            lower.pop();
        }
        lower.push(*p);
    }

    let mut upper = Vec::new();
    for p in pts.iter().rev() {
        while upper.len() >= 2 && cross(&upper[upper.len() - 2], &upper[upper.len() - 1], p) <= 0.0 {
            upper.pop();
        }
        upper.push(*p);
    }

    lower.pop();
    upper.pop();
    lower.extend(upper);
    lower
}

/// Compute Minimum Area Bounding Rectangle (oriented bounding box) for a set of points.
/// Returns (4 points ordered [top-left, top-right, bottom-right, bottom-left], shorter_side_length).
pub fn min_area_rect(pts: &[[f32; 2]]) -> ([[f32; 2]; 4], f32) {
    if pts.is_empty() {
        return ([[0.0; 2]; 4], 0.0);
    }
    if pts.len() <= 2 {
        let p0 = pts[0];
        let p1 = if pts.len() > 1 { pts[1] } else { p0 };
        return ([[p0[0], p0[1]], [p1[0], p1[1]], [p1[0], p1[1]], [p0[0], p0[1]]], 0.0);
    }

    let hull = convex_hull(pts.to_vec());
    let n = hull.len();
    if n < 3 {
        let p0 = hull[0];
        let p1 = if n > 1 { hull[1] } else { p0 };
        return ([[p0[0], p0[1]], [p1[0], p1[1]], [p1[0], p1[1]], [p0[0], p0[1]]], 0.0);
    }

    let mut min_area = f32::INFINITY;
    let mut best_corners = [[0.0f32; 2]; 4];
    let mut best_shorter_side = 0.0f32;

    for i in 0..n {
        let j = (i + 1) % n;
        let edge = [hull[j][0] - hull[i][0], hull[j][1] - hull[i][1]];
        let len = (edge[0] * edge[0] + edge[1] * edge[1]).sqrt();
        if len <= 1e-4 {
            continue;
        }

        let angle = edge[1].atan2(edge[0]);
        let cos_a = (-angle).cos();
        let sin_a = (-angle).sin();

        let mut r_min_x = f32::INFINITY;
        let mut r_max_x = f32::NEG_INFINITY;
        let mut r_min_y = f32::INFINITY;
        let mut r_max_y = f32::NEG_INFINITY;

        for p in &hull {
            let rx = p[0] * cos_a - p[1] * sin_a;
            let ry = p[0] * sin_a + p[1] * cos_a;
            r_min_x = r_min_x.min(rx);
            r_max_x = r_max_x.max(rx);
            r_min_y = r_min_y.min(ry);
            r_max_y = r_max_y.max(ry);
        }

        let w = r_max_x - r_min_x;
        let h = r_max_y - r_min_y;
        let area = w * h;

        if area < min_area {
            min_area = area;
            best_shorter_side = w.min(h);

            let cos_back = angle.cos();
            let sin_back = angle.sin();

            let corners_rot = [
                [r_min_x, r_min_y],
                [r_max_x, r_min_y],
                [r_max_x, r_max_y],
                [r_min_x, r_max_y],
            ];

            for (k, c) in corners_rot.iter().enumerate() {
                best_corners[k] = [
                    c[0] * cos_back - c[1] * sin_back,
                    c[0] * sin_back + c[1] * cos_back,
                ];
            }
        }
    }

    // Check coordinate finiteness
    if best_corners.iter().any(|p| !p[0].is_finite() || !p[1].is_finite()) {
        return ([[0.0; 2]; 4], 0.0);
    }

    // Sort corners clockwise starting from top-left safely without panicking
    let mut sorted = best_corners;
    sorted.sort_by(|a, b| a[0].partial_cmp(&b[0]).unwrap_or(std::cmp::Ordering::Equal));
    let mut left = [sorted[0], sorted[1]];
    let mut right = [sorted[2], sorted[3]];
    left.sort_by(|a, b| a[1].partial_cmp(&b[1]).unwrap_or(std::cmp::Ordering::Equal));
    right.sort_by(|a, b| a[1].partial_cmp(&b[1]).unwrap_or(std::cmp::Ordering::Equal));

    best_corners = [left[0], right[0], right[1], left[1]];
    (best_corners, best_shorter_side)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_polygon_area_and_perimeter() {
        let rect = [[0.0, 0.0], [100.0, 0.0], [100.0, 50.0], [0.0, 50.0]];
        let area = polygon_area(&rect);
        let perim = polygon_perimeter(&rect);
        assert!((area - 5000.0).abs() < 1e-4);
        assert!((perim - 300.0).abs() < 1e-4);
    }

    #[test]
    fn test_unclip_polygon_expansion() {
        let rect = [[10.0, 10.0], [110.0, 10.0], [110.0, 60.0], [10.0, 60.0]];
        let expanded = unclip_polygon(&rect, 2.0);
        assert!(!expanded.is_empty());
        let exp_area = polygon_area(&expanded);
        assert!(exp_area > 5000.0);
    }

    #[test]
    fn test_min_area_rect_axis_aligned() {
        let pts = vec![[10.0, 20.0], [110.0, 20.0], [110.0, 60.0], [10.0, 60.0]];
        let (box_pts, side) = min_area_rect(&pts);
        assert!((side - 40.0).abs() < 1e-3);
        assert_eq!(box_pts.len(), 4);
    }

    #[test]
    fn test_dbnet_postprocess_synthetic_map() {
        let detector = DbNetDetector::without_session(DbNetConfig::default());
        // Create 100x100 synthetic probability map with a high-confidence subtitle strip in center
        let mut map = vec![0.0f32; 100 * 100];
        for y in 40..60 {
            for x in 20..80 {
                map[y * 100 + x] = 0.95;
            }
        }

        let results = detector.postprocess(&map, 100, 100, 200, 200);
        assert_eq!(results.len(), 1);
        let (sub_box, score) = &results[0];
        assert!(*score > 0.8);
        assert!(sub_box.center_y() > 70.0 && sub_box.center_y() < 130.0);
    }
}
