use image::RgbaImage;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MonitorTargetInfo {
    pub id: u32,
    pub name: String,
    pub width: u32,
    pub height: u32,
    pub scale_factor: f32,
    pub is_primary: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WindowTargetInfo {
    pub id: u32,
    pub title: String,
    pub app_name: String,
    pub width: u32,
    pub height: u32,
    pub is_minimized: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaptureRoi {
    pub left: u32,
    pub top: u32,
    pub width: u32,
    pub height: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CaptureTargets {
    pub monitors: Vec<MonitorTargetInfo>,
    pub windows: Vec<WindowTargetInfo>,
}

pub struct CaptureEngine;

impl CaptureEngine {
    pub fn list_targets() -> Result<CaptureTargets, String> {
        let mut monitors = Vec::new();
        match xcap::Monitor::all() {
            Ok(all_monitors) => {
                for (idx, m) in all_monitors.into_iter().enumerate() {
                    monitors.push(MonitorTargetInfo {
                        id: idx as u32,
                        name: m.name().unwrap_or_else(|_| format!("Display {}", idx + 1)),
                        width: m.width().unwrap_or(1920),
                        height: m.height().unwrap_or(1080),
                        scale_factor: m.scale_factor().unwrap_or(1.0),
                        is_primary: m.is_primary().unwrap_or(idx == 0),
                    });
                }
            }
            Err(e) => {
                eprintln!("[CAPTURE-WARN] Failed to list monitors: {}", e);
            }
        }

        let mut windows = Vec::new();
        match xcap::Window::all() {
            Ok(all_windows) => {
                for w in all_windows {
                    let title = w.title().unwrap_or_default();
                    let app_name = w.app_name().unwrap_or_default();
                    let is_minimized = w.is_minimized().unwrap_or(false);

                    // Filter out invisible, background or empty utility windows
                    if !is_minimized && (!title.trim().is_empty() || !app_name.trim().is_empty()) {
                        let width = w.width().unwrap_or(0);
                        let height = w.height().unwrap_or(0);
                        if width > 100 && height > 100 {
                            windows.push(WindowTargetInfo {
                                id: w.id().unwrap_or(0),
                                title,
                                app_name,
                                width,
                                height,
                                is_minimized,
                            });
                        }
                    }
                }
            }
            Err(e) => {
                eprintln!("[CAPTURE-WARN] Failed to list windows: {}", e);
            }
        }

        Ok(CaptureTargets { monitors, windows })
    }

    /// Captures the primary screen, optionally cropping to an ROI bounding box.
    pub fn capture_screen(monitor_idx: Option<usize>, roi: Option<&CaptureRoi>) -> Result<RgbaImage, String> {
        let all_monitors = xcap::Monitor::all().map_err(|e| format!("Failed to list monitors: {}", e))?;
        if all_monitors.is_empty() {
            return Err("No active displays found".to_string());
        }

        let idx = monitor_idx.unwrap_or(0).min(all_monitors.len() - 1);
        let monitor = &all_monitors[idx];
        let raw_img = monitor.capture_image().map_err(|e| format!("Capture display failed: {}", e))?;

        if let Some(r) = roi {
            Self::crop_image(&raw_img, r)
        } else {
            Ok(raw_img)
        }
    }

    /// Captures a specific window by its window ID, falling back to primary screen if closed.
    pub fn capture_window(window_id: u32, roi: Option<&CaptureRoi>) -> Result<RgbaImage, String> {
        if let Ok(all_windows) = xcap::Window::all() {
            if let Some(target_window) = all_windows.into_iter().find(|w| w.id().unwrap_or(0) == window_id) {
                if let Ok(raw_img) = target_window.capture_image() {
                    if let Some(r) = roi {
                        return Self::crop_image(&raw_img, r);
                    } else {
                        return Ok(raw_img);
                    }
                }
            }
        }

        // Fallback to primary screen
        Self::capture_screen(None, roi)
    }

    /// Safely crops an RgbaImage to the specified ROI boundaries.
    pub fn crop_image(img: &RgbaImage, roi: &CaptureRoi) -> Result<RgbaImage, String> {
        let img_w = img.width();
        let img_h = img.height();

        if roi.width == 0 || roi.height == 0 {
            return Err("ROI width and height must be > 0".to_string());
        }

        let crop_x = roi.left.min(img_w);
        let crop_y = roi.top.min(img_h);
        let crop_w = roi.width.min(img_w.saturating_sub(crop_x));
        let crop_h = roi.height.min(img_h.saturating_sub(crop_y));

        if crop_w == 0 || crop_h == 0 {
            return Err("Crop bounds fall completely outside image dimensions".to_string());
        }

        let cropped = image::imageops::crop_imm(img, crop_x, crop_y, crop_w, crop_h).to_image();
        Ok(cropped)
    }

    /// Encodes an RgbaImage into a base64 JPEG data URL for lightweight frontend preview streaming.
    pub fn to_base64_jpeg(img: &RgbaImage, quality: u8) -> Result<String, String> {
        let rgb_img = image::DynamicImage::ImageRgba8(img.clone()).to_rgb8();
        let mut jpeg_bytes: Vec<u8> = Vec::new();
        let mut encoder = image::codecs::jpeg::JpegEncoder::new_with_quality(&mut jpeg_bytes, quality);
        encoder
            .encode(rgb_img.as_raw(), rgb_img.width(), rgb_img.height(), image::ExtendedColorType::Rgb8)
            .map_err(|e| format!("JPEG encode failed: {}", e))?;

        use base64::Engine;
        let b64 = base64::engine::general_purpose::STANDARD.encode(&jpeg_bytes);
        Ok(format!("data:image/jpeg;base64,{}", b64))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::Rgba;

    #[test]
    fn test_crop_image_bounds() {
        let mut img = RgbaImage::new(200, 100);
        img.put_pixel(10, 10, Rgba([255, 0, 0, 255]));

        let roi = CaptureRoi {
            left: 5,
            top: 5,
            width: 50,
            height: 50,
        };

        let cropped = CaptureEngine::crop_image(&img, &roi).expect("crop succeeds");
        assert_eq!(cropped.width(), 50);
        assert_eq!(cropped.height(), 50);
        assert_eq!(cropped.get_pixel(5, 5), &Rgba([255, 0, 0, 255]));
    }

    #[test]
    fn test_crop_image_out_of_bounds_clamped() {
        let img = RgbaImage::new(100, 100);
        let roi = CaptureRoi {
            left: 80,
            top: 80,
            width: 100,
            height: 100,
        };

        let cropped = CaptureEngine::crop_image(&img, &roi).expect("clamped crop succeeds");
        assert_eq!(cropped.width(), 20);
        assert_eq!(cropped.height(), 20);
    }

    #[test]
    fn test_to_base64_jpeg_encoding() {
        let img = RgbaImage::from_pixel(64, 36, Rgba([100, 150, 200, 255]));
        let b64 = CaptureEngine::to_base64_jpeg(&img, 60).expect("JPEG encoding succeeds");
        assert!(b64.starts_with("data:image/jpeg;base64,"));
        assert!(b64.len() > 50);
    }
}
