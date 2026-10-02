# Subterranean Staircase

Real-time, on-device screen subtitle translator for macOS and Windows.

Watch foreign films, anime, livestreams, or video courses without language barriers. The app runs quietly in your menu bar / system tray, reads on-screen hardcoded or soft subtitles directly from your media player (e.g. VLC, MPV, Browser, YouTube), translates them in real-time on-device, and renders a crisp, click-through overlay on top of your video.

> **Status:** Active rewrite (V1 Architecture).  
> The legacy monolithic Windows prototype is archived in the [`legacy/v0-windows-prealpha`](https://github.com/ganendraditya/subterranean-staircase/tree/legacy/v0-windows-prealpha) branch and [`v0.1.0-prealpha`](https://github.com/ganendraditya/subterranean-staircase/releases/tag/v0.1.0-prealpha) release.

---

## Quick Install (Terminal)

### macOS / Linux
Run in your terminal:
```bash
curl -fsSL https://raw.githubusercontent.com/ganendraditya/subterranean-staircase/main/install.sh | bash
```

Installs to `~/.local/share/subtitle-translator` and creates a launcher at `~/.local/bin/subtrans`.  
On macOS, the installer will optionally configure a **LaunchAgent** (`~/Library/LaunchAgents/com.subtitle-translator.subtrans.plist`) to auto-start subtrans at login.

### Windows (PowerShell)
Run in PowerShell:
```powershell
irm https://raw.githubusercontent.com/ganendraditya/subterranean-staircase/main/install.ps1 | iex
```

Installs to `%LOCALAPPDATA%\SubtitleTranslator` and creates a launcher at `%LOCALAPPDATA%\Programs\SubtitleTranslator\subtrans.cmd`, added to your user `PATH` automatically.

### Running & Auto-Start
- **Auto-Start on Boot:** If enabled during installation (or toggled anytime in **Settings → System & Autostart**), Subterranean Staircase runs silently in your background menu bar / system tray whenever your computer boots.
- **Manual Launch:** You can also launch the app from terminal anytime:
```bash
subtrans
```

### Model Management
Manage on-device offline translation models directly in **Settings → Offline Translation Models**:
- Download language pairs (e.g. Japanese → English, Korean → English, English → Indonesian, Chinese → English) on-demand with progress tracking.
- Delete unused models anytime to free up disk space.

### Updates
- **In-App (1-Click):** When an update is available, a notification and tray banner `✨ Update Available` will appear. Click to update dependencies and restart automatically without opening terminal.
- **Settings Dialog:** You can also toggle automatic checks or manually click **"Check for Updates Now"** under Settings.

### Uninstalling
Remove the app cleanly (keeps your configs and cached models):
```bash
subtrans uninstall
```

To also remove all translation caches and config files:
```bash
subtrans uninstall --purge
```

On Windows (PowerShell):
```powershell
subtrans uninstall -RemoveAllData
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
git clone https://github.com/ganendraditya/subterranean-staircase.git
cd subterranean-staircase

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
