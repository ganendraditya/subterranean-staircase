# Subterranean Staircase

Real-time, on-device screen subtitle translator for macOS and Windows.

Watch foreign films, anime, livestreams, or video courses without language barriers. The app runs quietly in your menu bar / system tray, reads on-screen hardcoded or soft subtitles directly from your media player (e.g. VLC, MPV, Browser, YouTube), translates them in real-time on-device, and renders a crisp, click-through overlay on top of your video.

---

## Download & Installation

### Option 1: Standalone Desktop Installers (Recommended for End-Users)

Download the prebuilt, standalone installer for your operating system (no Python, terminal, or compiler required):

| Platform | Architecture / Device | Installer Type | Direct Download Link |
| :--- | :--- | :--- | :--- |
| **macOS** | **Apple Silicon** (M1 / M2 / M3 / M4) | Standalone `.dmg` | [**Download `.dmg` (Apple Silicon)**](https://github.com/ganendraditya/subterranean-staircase/releases/latest/download/Subterranean-Staircase-macos-arm64.dmg) |
| **macOS** | **Intel** (Core i5 / i7 / i9) | Standalone `.dmg` | [**Download `.dmg` (Intel)**](https://github.com/ganendraditya/subterranean-staircase/releases/latest/download/Subterranean-Staircase-macos-x86_64.dmg) |
| **Windows** | **64-bit** (Windows 10 / 11) | Setup Wizard (`.exe`) | [**Download `Setup.exe` (Windows)**](https://github.com/ganendraditya/subterranean-staircase/releases/latest/download/Subterranean-Staircase-windows-x64-Setup.exe) |
| **Windows** | **64-bit** (Windows 10 / 11) | Portable Archive (`.zip`) | [**Download Portable `.zip`**](https://github.com/ganendraditya/subterranean-staircase/releases/latest/download/Subterranean-Staircase-windows-x64-portable.zip) |

* On macOS: Open the downloaded `.dmg` and drag **Subterranean Staircase** into your `Applications` folder.
* On Windows: Run `Subterranean-Staircase-windows-x64-Setup.exe` and follow the guided setup wizard.

---

### Option 2: Terminal Installation (One-Liner)

For users who prefer installing directly via terminal without manually downloading files in a browser:

#### macOS / Linux
Run in your terminal:
```bash
curl -fsSL https://raw.githubusercontent.com/ganendraditya/subterranean-staircase/main/install.sh | bash
```
Installs to `~/.local/share/subtitle-translator` and creates a launcher at `~/.local/bin/subtrans`.  
On macOS, the installer configures a native `.app` bundle and an optional **LaunchAgent** (`~/Library/LaunchAgents/com.subtitle-translator.subtrans.plist`) to auto-start at login.

#### Windows (PowerShell)
Run in PowerShell:
```powershell
irm https://raw.githubusercontent.com/ganendraditya/subterranean-staircase/main/install.ps1 | iex
```
Installs to `%LOCALAPPDATA%\SubtitleTranslator` and creates a launcher at `%LOCALAPPDATA%\Programs\SubtitleTranslator\subtrans.cmd`, added to your user `PATH` automatically.

---

### Option 3: Local Clone & Development Setup (For Contributors)

For developers contributing to the codebase, testing bug fixes, or running from local source:

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

# Run full test suite
pytest tests/

# Launch application
python run.py
```

---

## Usage & Management

### 1. Daily Desktop Usage (GUI)
- **Menu Bar & Tray:** Once running, Subterranean Staircase lives in your system tray / menu bar. Click the tray icon to open the **Control Center**, pause/resume capture, or adjust settings.
- **Auto-Start on Boot:** If enabled during installation (or toggled in **Control Center → System & Autostart**), the application starts silently in the background whenever your system boots.
- **Draggable Subtitle Positioning:** Click **"Move Subtitles"** in Control Center to unlock the overlay canvas, drag it to your desired position on screen, and lock it in place.

### 2. Translation Engine Modes (Offline & Cloud)
Switch between translation backends anytime under **Control Center → Language & Translation**:
- **Offline Mode:** Download Big 5 language packs (English, Indonesian, Japanese, Korean, Chinese) for zero-latency, private, and offline translation powered by quantized CTranslate2.
- **Universal OpenAI-Compatible Mode (BYOK):** Connect any cloud API provider or self-hosted local model adhering to the standard `/v1/chat/completions` protocol (OpenAI, Groq, DeepSeek, Together AI, Ollama, vLLM, LM Studio). Simply provide your Base URL, Model Name, and API Key.

### 3. Updates & Data Management
- **1-Click Updates:** When a new release is available, an in-app banner will appear. Click to update dependencies and restart automatically.
- **Factory Reset (0 Bytes):** Need a clean slate? Click **"Factory Reset..."** in Control Center to wipe all downloaded language models, caches, and user preferences.

### 4. Advanced CLI Usage (For Terminal Users)
For users running from source or installed via the terminal one-liner:
- **Launch Application:**
  ```bash
  subtrans
  ```
- **Clean Interactive Uninstall:**
  ```bash
  subtrans uninstall
  ```
- **Purge All Data Non-Interactively:**
  ```bash
  subtrans uninstall --purge
  ```

---

## Architecture & Stack (V1)

- **Screen & Window Capture:** Modular backend supporting macOS (ScreenCaptureKit / Quartz) and Windows (DirectX / Win32) with universal fallback via `mss`.
- **Vision & OCR:** RapidOCR (ONNX Runtime, CoreML/DirectML/CPU) with perceptual frame-diff short-circuiting to minimize CPU/GPU usage when scenes are static.
- **Subtitle Intelligence:** Dual-band spatial scanning (top & bottom priority), Jaccard similarity temporal tracking, and multi-language script filtering.
- **Translation Engine:** CTranslate2 offline INT8 quantized MarianMT models with SQLite WAL caching + Universal OpenAI-Compatible Cloud LLM provider with fail-safe local fallback.
- **UI & Overlay:** Hardware-accelerated PyQt6 transparent, click-through frameless overlay adhering to Anti-Slop WCAG AA contrast standards, anchored at bottom-center.
- **Distribution:** Standalone `.dmg` (macOS arm64/x86_64), `Setup.exe` (Windows), and lightweight CLI installer.

> **Deep Technical Specifications:** For full mathematical formulas, DBNet unclip scaling, NMT beam tuning benchmarks, and macOS WindowServer Spaces privilege specifications, see [`docs/TECHNICAL_STACK_AND_PIPELINES.md`](docs/TECHNICAL_STACK_AND_PIPELINES.md).

---

## Project Structure

```text
subterranean-staircase/
├── core/
│   ├── contracts/          # Single source of truth domain data models (DIP)
│   ├── capture/            # Screen & window grabbers (multi-OS)
│   ├── vision/             # Frame difference hashing and image processing
│   ├── ocr/                # RapidOCR ONNX wrapper
│   ├── subtitle/           # Temporal stabilization and spatial filters
│   ├── translate/          # CTranslate2 engine, LLM engine & language routing
│   ├── storage/            # SQLite WAL cache & history storage
│   ├── pipeline.py         # Event-driven background orchestrator
│   └── config.py           # Configuration schema and manager
├── ui/                     # PyQt6 overlay, ROI selector, tray, and control center
├── docs/                   # Architectural specifications and pipeline formulas
├── scripts/                # Packaging, evaluation benchmarks, and installer builders
├── tests/                  # Unit and integration test suite
├── subtrans.spec           # Cross-platform PyInstaller standalone spec
├── install.sh              # Single-line installer (macOS/Linux)
├── uninstall.sh            # Clean uninstaller (macOS/Linux)
├── install.ps1             # Single-line installer (Windows)
├── uninstall.ps1           # Clean uninstaller (Windows)
├── AGENTS.md               # Engineering rules & Anti-Slop guidelines
├── requirements.txt        # Cross-platform dependencies
└── run.py                  # Application launcher
```

---

## License

MIT
