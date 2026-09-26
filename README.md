# Subtitle Translator

Real-time screen subtitle translator for Windows. It helps when you find a video, stream, or other media with subtitles in a language you do not understand: the app captures the screen or a selected window, detects subtitle regions, runs OCR, translates the text, and displays a click-through PyQt overlay.

> **Status:** `v0.1.0-prealpha` (Legacy / Monolithic prototype — currently being redesigned for cross-platform V1).

## Stack

- Screen/window capture: dxcam and Windows `PrintWindow`
- Subtitle detection: YOLO via Ultralytics and ONNX Runtime
- OCR: PaddleOCR in a subprocess
- Translation: MarianMT / Helsinki-NLP, with 2-hop routing through English
- Overlay/UI: PyQt6 tray app and transparent click-through overlay windows

## Setup

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

The default requirements target NVIDIA GPU acceleration for ONNX Runtime and PaddleOCR. CPU-only setups may need to replace `onnxruntime-gpu` with `onnxruntime` and `paddlepaddle-gpu` with `paddlepaddle`.

Download or export a compatible subtitle detector model, then place it at:

```text
yolo/epoch51.onnx
```

The app expects an ONNX YOLO detector at that path. Large model files are distributed outside the Git repository, for example through GitHub Releases.

## Run

```powershell
.\venv\Scripts\python.exe run.py
.\venv\Scripts\python.exe run.pyw
```

Use `run.py` for debugging with terminal logs. Use `run.pyw` for no-console startup.

## Test

```powershell
.\venv\Scripts\python.exe -m unittest discover tests
```

## Languages

Supported UI language codes:

| Code | Language |
| --- | --- |
| `en` | English |
| `id` | Indonesian |
| `ja` | Japanese |
| `zh` | Chinese |
| `ko` | Korean |
| `fr` | French |
| `de` | German |
| `es` | Spanish |
| `ar` | Arabic |

Translation caveat: Japanese and Korean use non-standard Helsinki model IDs internally, so the app maps UI codes `ja` and `ko` before loading MarianMT models.
