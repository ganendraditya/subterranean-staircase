# Subterranean Staircase

Real-time on-screen subtitle translator for macOS and Windows.

When watching videos, anime, or livestreams with captions in a foreign language you don't understand, Subterranean Staircase reads those on-screen subtitles directly from your media player (e.g. VLC, MPV, YouTube, Browser), translates them in real-time, and displays a new translated subtitle overlay right on top of your video—without needing external subtitle files.

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

### Running & Auto-Start
- **Auto-Start on Boot:** If enabled during installation (or toggled anytime in **Control Center → System & Autostart**), Subterranean Staircase runs silently in your background menu bar / system tray whenever your computer boots.
- **Manual Launch:** You can also launch the app from terminal anytime:
```bash
subtrans
```

### Model & Translation Engine Management
Manage translation settings directly in **Control Center → Language & Translation Model**:
- **Offline Mode:** Download Big 5 language packs (English, Indonesian, Japanese, Korean, Chinese) on-demand with 1-click downloads.
- **Universal Cloud LLM (BYOK):** Switch to OpenAI-compatible mode and configure your API key for Groq (`llama-3.3-70b-versatile`), DeepSeek, OpenAI, or local self-hosted instances (Ollama, vLLM).
- **Draggable Positioning:** Click **"Move Subtitles"** in Control Center to reposition the overlay anywhere on your screen.

### Updates
- **In-App (1-Click):** When an update is available, a notification and tray banner `Update Available` will appear. Click to update dependencies and restart automatically without opening terminal.
- **Control Center:** You can also toggle automatic checks or manually click **"Check Now"** under Control Center.

### Uninstalling

#### Standalone Applications
- **macOS:** Open **Control Center** and click **"Factory Reset..."** to purge all downloaded models and caches down to 0 bytes, then drag `Subterranean Staircase.app` from your `/Applications` folder to Trash.
- **Windows:** Go to **Windows Settings → Apps → Installed apps**, locate **Subterranean Staircase**, and click **Uninstall**. An interactive prompt will ask whether you also want to purge all downloaded models and user configurations.

#### Terminal Installations
To uninstall cleanly from terminal:
```bash
subtrans uninstall
```
An interactive prompt will ask whether you want to preserve your configurations and cached offline models or remove them.

To bypass the prompt and completely remove all files and cached models non-interactively:
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
subtitle-translator/
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
