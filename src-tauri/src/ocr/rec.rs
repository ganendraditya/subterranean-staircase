//! Text Recognition Engine (PP-OCRv4 / SVTR + CTC Decoder)

use image::RgbaImage;
use ndarray::Array4;
use ort::session::builder::GraphOptimizationLevel;
use ort::session::Session;
use std::path::Path;
use std::sync::Mutex;

use super::ctc::CtcDecoder;
use super::SubtitleBox;

pub struct TextRecognizer {
    session: Option<Mutex<Session>>,
    pub decoder: CtcDecoder,
}

impl TextRecognizer {
    /// Initialize recognizer from ONNX model file.
    /// Automatically extracts embedded "character" dictionary from model metadata.
    pub fn new<P: AsRef<Path>>(model_path: P) -> Result<Self, String> {
        let session = Session::builder()
            .map_err(|e| format!("Failed to create ONNX session builder: {e}"))?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|e| format!("Failed to set graph optimization level: {e}"))?
            .with_intra_threads(2)
            .map_err(|e| format!("Failed to set intra threads: {e}"))?
            .commit_from_file(model_path)
            .map_err(|e| format!("Failed to load PP-OCR recognition ONNX model: {e}"))?;

        let character_list = if let Ok(meta) = session.metadata() {
            if let Some(char_str) = meta.custom("character") {
                char_str.lines().map(|s| s.to_string()).collect::<Vec<String>>()
            } else {
                Vec::new()
            }
        } else {
            Vec::new()
        };

        if character_list.is_empty() {
            return Err("Recognition ONNX model does not embed a character dictionary in metadata".to_string());
        }

        let decoder = CtcDecoder::new(character_list);

        Ok(Self {
            session: Some(Mutex::new(session)),
            decoder,
        })
    }

    /// Construct recognizer with a pre-configured CTC decoder (useful for tests or custom dictionaries).
    pub fn with_decoder(decoder: CtcDecoder) -> Self {
        Self {
            session: None,
            decoder,
        }
    }

    /// Preprocess an image strip into a [1, 3, 48, W] float tensor.
    pub fn preprocess_strip(&self, strip: &RgbaImage) -> (Array4<f32>, usize) {
        let (w, h) = (strip.width(), strip.height());
        if w == 0 || h == 0 {
            return (Array4::<f32>::zeros((1, 3, 48, 32)), 32);
        }

        let target_h = 48.0f32;
        let scale = target_h / (h as f32);
        let mut target_w = (w as f32 * scale).round() as u32;
        target_w = target_w.clamp(32, 1024);

        let resized = image::imageops::resize(
            strip,
            target_w,
            48,
            image::imageops::FilterType::Triangle,
        );

        let mut tensor = Array4::<f32>::zeros((1, 3, 48, target_w as usize));
        for y in 0..48 {
            for x in 0..target_w as usize {
                let p = resized.get_pixel(x as u32, y as u32);
                tensor[[0, 0, y, x]] = (p[0] as f32 - 127.5) / 127.5;
                tensor[[0, 1, y, x]] = (p[1] as f32 - 127.5) / 127.5;
                tensor[[0, 2, y, x]] = (p[2] as f32 - 127.5) / 127.5;
            }
        }

        (tensor, target_w as usize)
    }

    /// Crop an oriented subtitle bounding box from the frame buffer.
    pub fn crop_box(image: &RgbaImage, box_points: &SubtitleBox) -> RgbaImage {
        let min_x = box_points.min_x().max(0.0).floor() as u32;
        let max_x = (box_points.max_x().ceil() as u32).min(image.width().saturating_sub(1));
        let min_y = box_points.min_y().max(0.0).floor() as u32;
        let max_y = (box_points.max_y().ceil() as u32).min(image.height().saturating_sub(1));

        if min_x >= max_x || min_y >= max_y {
            return RgbaImage::new(10, 10);
        }

        let crop_w = (max_x - min_x + 1).max(1);
        let crop_h = (max_y - min_y + 1).max(1);

        let mut strip = RgbaImage::new(crop_w, crop_h);
        for y in 0..crop_h {
            for x in 0..crop_w {
                let src_x = min_x + x;
                let src_y = min_y + y;
                if src_x < image.width() && src_y < image.height() {
                    strip.put_pixel(x, y, *image.get_pixel(src_x, src_y));
                }
            }
        }
        strip
    }

    /// Run text recognition on a cropped subtitle strip.
    pub fn recognize_strip(&self, strip: &RgbaImage) -> Result<(String, f32), String> {
        let (tensor, target_w) = self.preprocess_strip(strip);

        let session_mutex = self
            .session
            .as_ref()
            .ok_or_else(|| "Recognition ONNX session is not loaded".to_string())?;

        let mut session = session_mutex
            .lock()
            .map_err(|e| format!("Failed to lock recognition ONNX session: {e}"))?;

        let tensor_val = ort::value::Tensor::from_array(tensor)
            .map_err(|e| format!("Failed to create recognition input tensor: {e}"))?;

        let inputs = ort::inputs![tensor_val];
        let outputs = session
            .run(inputs)
            .map_err(|e| format!("Recognition inference failed: {e}"))?;

        let (shape, logits_slice) = outputs[0]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("Failed to extract output logits tensor: {e}"))?;

        // Output shape is [1, T, num_classes]
        let num_classes = if shape.len() >= 3 { shape[2] as usize } else { self.decoder.len() };
        let t_steps = if shape.len() >= 2 { shape[1] as usize } else { target_w / 4 };

        Ok(self.decoder.decode_slice(logits_slice, t_steps, num_classes))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_crop_box_safety() {
        let img = RgbaImage::new(200, 100);
        let box_pts = SubtitleBox::new([[10.0, 20.0], [80.0, 20.0], [80.0, 50.0], [10.0, 50.0]]);
        let cropped = TextRecognizer::crop_box(&img, &box_pts);
        assert!(cropped.width() > 50);
        assert!(cropped.height() > 20);
    }

    #[test]
    fn test_preprocess_strip_aspect_ratio() {
        let recognizer = TextRecognizer::with_decoder(CtcDecoder::new(vec![]));
        let strip = RgbaImage::new(100, 25);
        let (tensor, target_w) = recognizer.preprocess_strip(&strip);
        assert_eq!(tensor.shape()[0], 1);
        assert_eq!(tensor.shape()[1], 3);
        assert_eq!(tensor.shape()[2], 48);
        assert_eq!(tensor.shape()[3], target_w);
        assert!(target_w >= 32);
    }

    #[test]
    fn test_load_real_rec_metadata_if_present() {
        let model_path = Path::new("models/ch_PP-OCRv4_rec_infer.onnx");
        if !model_path.exists() {
            return;
        }
        let recognizer = TextRecognizer::new(model_path).expect("load recognizer");
        assert!(recognizer.decoder.len() > 6600);
    }
}
