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

# Run V2 Native Desktop App (Rust + Tauri v2 + Vite)
bun install         # or npm install
bun run tauri dev   # or npm run tauri dev

# Or run V1 Prototype (Python 3.10+ / PyQt6)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
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

## Architecture & Benchmark Performance (V1 vs V2)

The `v2.0.0` release introduces a complete, pure native rewrite to **Rust + Tauri v2**, replacing Python 3 and PyQt6:

| Architectural Metric | Prototype (V1 Python + PyQt6) | Production (V2 Rust + Tauri v2) | Impact / Performance Delta |
| :--- | :---: | :---: | :--- |
| **Installer Size** | ~150 MB (PyInstaller) | **$\le$ 35 MB** | **4.3× Smaller Package** |
| **Standalone Executable** | 142 MB | **26 MB** | **5.4× Smaller Binary** |
| **Idle Memory Footprint** | 156.4 MB (Dual Window) | **58.2 MB** | **62.8% RAM Reduction (2.7× leaner)** |
| **Active Memory (Peak)** | 184 MB – 420 MB | **96.5 MB** | **Zero memory growth & zero GIL contention** |
| **Cold Boot Startup Time** | 1.8 s – 2.5 s | **0.25 s** | **8× – 10× Instant Launch** |
| **Perceptual Frame-Diff** | 0.044 ms (NumPy) | **0.005 ms** (SIMD AVX/NEON) | **8.8× Faster Gating (< 5 µs)** |
| **Neural OCR Latency (P50)**| 190.2 ms (RapidOCR 720p) | **101.6 ms** (`ort` DBNet+SVTR) | **~2× Faster Full-Frame Processing** |
| **SQLite WAL Memory Recall**| 0.025 ms | **< 0.005 ms** | **Sub-millisecond repeat phrase recall** |

### Core Subsystems (V2):
- **Screen & Window Grabber:** Native Quartz (`CGWindowListCreateImage`) on macOS and DXGI Desktop Duplication on Windows via zero-copy `xcap`.
- **Vision Gating:** SIMD-accelerated Mean Absolute Difference (MAD) skipping 100% of OCR compute on static video frames.
- **Neural OCR Pipeline:** Standalone ONNX Runtime (`ort` v2) with DBNet letterbox scaling (`unclip_ratio = 2.0`), PP-OCRv4 text recognition, and native Rust CTC greedy decoder (6,625 glyph dictionary).
- **Dual-Engine Translation Matrix:** Model-agnostic OpenAI-compatible HTTP client (`reqwest` + `tokio`, SSRF-hardened, timeout-bounded) with instant SQLite WAL translation memory and built-in offline dictionary fallback.
- **Floating Subtitle Overlay:** Non-activating, transparent, click-through webview window configured with `NSScreenSaverWindowLevel` (1000) for native macOS fullscreen spaces support.

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
