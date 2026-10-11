use serde::Serialize;
use std::env;
use std::path::Path;
use std::time::Instant;
use subterranean_staircase_lib::ocr::OcrEngine;

#[derive(Serialize)]
struct BenchResult {
    image: String,
    text: String,
    latency_ms: f64,
    detections: usize,
    success: bool,
    error: Option<String>,
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: ocr_bench <image_path_1> [image_path_2 ...]");
        std::process::exit(1);
    }

    let engine = OcrEngine::new_default();
    if !engine.is_ready() {
        eprintln!("Error: OCR models not found or uninitialized.");
        std::process::exit(2);
    }

    let mut results = Vec::new();

    for img_path_str in &args[1..] {
        let path = Path::new(img_path_str);
        if !path.exists() {
            results.push(BenchResult {
                image: img_path_str.clone(),
                text: String::new(),
                latency_ms: 0.0,
                detections: 0,
                success: false,
                error: Some("File not found".to_string()),
            });
            continue;
        }

        let dyn_img = match image::open(path) {
            Ok(im) => im,
            Err(e) => {
                results.push(BenchResult {
                    image: img_path_str.clone(),
                    text: String::new(),
                    latency_ms: 0.0,
                    detections: 0,
                    success: false,
                    error: Some(format!("Failed to open image: {e}")),
                });
                continue;
            }
        };

        let rgba_img = dyn_img.to_rgba8();
        let t0 = Instant::now();
        match engine.process_image(&rgba_img) {
            Ok(detections) => {
                let latency_ms = t0.elapsed().as_secs_f64() * 1000.0;
                let text = OcrEngine::consolidate_detections(&detections);
                results.push(BenchResult {
                    image: img_path_str.clone(),
                    text,
                    latency_ms,
                    detections: detections.len(),
                    success: true,
                    error: None,
                });
            }
            Err(e) => {
                results.push(BenchResult {
                    image: img_path_str.clone(),
                    text: String::new(),
                    latency_ms: 0.0,
                    detections: 0,
                    success: false,
                    error: Some(e),
                });
            }
        }
    }

    let json_output = serde_json::to_string_pretty(&results).unwrap();
    println!("{}", json_output);
}
