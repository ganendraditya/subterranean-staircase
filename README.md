# Subtitle Translator (V1)

Real-time, cross-platform screen subtitle translator for macOS and Windows.

The app captures video or selected application windows (e.g. VLC, Browser), extracts subtitle text via fast on-device OCR, translates it into your target language, and renders a crisp, click-through overlay in real-time.

> **Status:** Active rewrite (V1 Architecture).  
> The legacy monolithic Windows prototype is archived in the [`legacy/v0-windows-prealpha`](https://github.com/ganendraditya/subtitle-translator/tree/legacy/v0-windows-prealpha) branch and [`v0.1.0-prealpha`](https://github.com/ganendraditya/subtitle-translator/releases/tag/v0.1.0-prealpha) release.

---

## Quick Install (Terminal)

### macOS / Linux
Run in your terminal:
```bash
curl -fsSL https://raw.githubusercontent.com/ganendraditya/subtitle-translator/main/install.sh | bash
```

### Windows (PowerShell)
Run in PowerShell:
```powershell
irm https://raw.githubusercontent.com/ganendraditya/subtitle-translator/main/install.ps1 | iex
```

Once installed, simply run:
```bash
subtrans
```

To cleanly uninstall anytime:
```bash
subtrans uninstall
```

---

## Architecture & Stack (V1)

- **Screen & Window Capture:** Modular backend supporting macOS (ScreenCaptureKit / Quartz) and Windows (DirectX / Win32) with universal fallback via `mss`.
- **Vision & OCR:** RapidOCR (ONNX Runtime, CoreML/DirectML/CPU) with perceptual frame-diff short-circuiting to minimize CPU/GPU usage when scenes are static.
- **Subtitle Intelligence:** Dual-band spatial scanning (top & bottom priority), Jaccard similarity temporal tracking, and multi-language script filtering.
- **Translation:** CTranslate2 offline INT8 quantized MarianMT models with SQLite WAL caching for sub-millisecond repeated phrase retrieval.
- **UI & Overlay:** Hardware-accelerated PyQt6 transparent, click-through frameless overlay adhering to Anti-Slop WCAG AA contrast standards.
- **Distribution:** Lightweight CLI launcher (`subtrans`) and tray daemon.

---

## Project Structure

```text
subtitle-translator/
├── core/
│   ├── contracts/          # Single source of truth domain data models (DIP)
│   ├── capture/            # Screen & window grabbers (multi-OS)
│   ├── vision/             # Frame difference hashing and image processing
│   ├── ocr/                # RapidOCR ONNX wrapper
│   ├── subtitle/           # Temporal stabilization and spatial filters
│   ├── translate/          # CTranslate2 engine & language routing
│   ├── storage/            # SQLite WAL cache & history storage
│   ├── pipeline.py         # Event-driven background orchestrator
│   └── config.py           # Configuration schema and manager
├── ui/                     # PyQt6 overlay, ROI selector, tray, and settings
├── tests/                  # Unit and integration test suite
├── install.sh              # Single-line installer (macOS/Linux)
├── uninstall.sh            # Clean uninstaller (macOS/Linux)
├── install.ps1             # Single-line installer (Windows)
├── uninstall.ps1           # Clean uninstaller (Windows)
├── AGENTS.md               # Karpathy engineering rules & Anti-Slop guidelines
├── requirements.txt        # Cross-platform dependencies
└── run.py                  # Application launcher
```

---

## Manual Development Setup

```bash
# Clone the repository
git clone https://github.com/ganendraditya/subtitle-translator.git
cd subtitle-translator

# Setup Python 3.10+ virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Run test suite
pytest tests/

# Launch desktop app
python run.py
```

---

## License

MIT
