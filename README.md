# Subterranean Staircase

Real-time, on-screen subtitle translator for macOS and Windows.

Subterranean Staircase captures on-screen subtitles directly from active media players, video browsers, or desktop windows (such as VLC, MPV, YouTube, or browser streams), runs on-device neural text detection and recognition, translates dialog lines in real-time, and renders a clean, click-through overlay on top of the playback window without requiring external subtitle files.

---

## Download & Installation

### Option 1: Standalone Desktop Installers (Recommended)

Prebuilt standalone installers for macOS and Windows:

| Platform | Architecture | Package Type | Download Link |
| :--- | :--- | :--- | :--- |
| **macOS** | Apple Silicon (M1 / M2 / M3 / M4) | Disk Image (`.dmg`) | [Download `.dmg` (Apple Silicon)](https://github.com/ganendraditya/subterranean-staircase/releases/latest/download/Subterranean-Staircase-macos-arm64.dmg) |
| **macOS** | Intel (x86_64) | Disk Image (`.dmg`) | [Download `.dmg` (Intel)](https://github.com/ganendraditya/subterranean-staircase/releases/latest/download/Subterranean-Staircase-macos-x86_64.dmg) |
| **Windows** | 64-bit (Windows 10 / 11) | Installer (`.exe` / `.msi`) | [Download `Setup.exe` (Windows)](https://github.com/ganendraditya/subterranean-staircase/releases/latest/download/Subterranean-Staircase-windows-x64-Setup.exe) |

- On macOS: Open the downloaded `.dmg` and drag **Subterranean Staircase** into the `Applications` folder.
- On Windows: Run the setup executable and follow the installation wizard.

---

### Option 2: Build from Source

Requirements:
- Node.js 20+ and Bun (or npm)
- Rust stable toolchain (`rustup`)
- Platform build dependencies (Xcode command-line tools on macOS; Visual Studio C++ Build Tools on Windows)

```bash
# Clone the repository
git clone https://github.com/ganendraditya/subterranean-staircase.git
cd subterranean-staircase

# Install frontend dependencies
bun install   # or: npm install

# Run in development mode (hot-reloading UI + native backend daemon)
bun run tauri dev   # or: npm run tauri dev

# Build production binaries
bun run tauri build # or: npm run tauri build
```

---

## Architecture Overview

Subterranean Staircase runs as a lightweight native desktop daemon built on Rust and Tauri v2:

- **Native Screen Capture:** Zero-copy display and window frame grabber on macOS (Quartz via `CGWindowListCreateImage`) and Windows (DXGI Desktop Duplication API) via `xcap`.
- **Perceptual SIMD Frame-Diff Gating:** Vectorized Mean Absolute Difference (MAD) calculation executed in under 0.2 ms. Frames with scene variance below 1.5% bypass neural OCR inference entirely, conserving CPU and battery during dialogue pauses.
- **On-Device Neural OCR:** Standalone ONNX Runtime (`ort` v2) executing DBNet text detection with aspect-preserving resize (`det_limit_type = "max"`) and polygon unclip expansion (`unclip_ratio = 2.0` via `clipper2-rust`) to prevent glyph descender truncation. Text recognition runs through PP-OCRv4 with a native Rust CTC greedy decoder mapping to 6,625 dictionary characters.
- **Dual-Engine Translation Router:** Model-agnostic OpenAI-compatible HTTP client (`reqwest` + `tokio`, SSRF-mitigated, timeout-bounded) supporting Bring-Your-Own-Key (BYOK) providers (Groq, DeepSeek, OpenAI, Ollama, vLLM). Integrates embedded SQLite write-ahead logging (`PRAGMA journal_mode = WAL`) for sub-millisecond repeat recall, and a built-in offline dictionary fallback when network connectivity is lost.
- **Floating Subtitle Overlay:** Non-activating, transparent, input-transparent webview window configured with `NSScreenSaverWindowLevel` (1000) and `NSWindowCollectionBehaviorFullScreenAuxiliary` for native macOS Fullscreen Spaces persistence.

> For comprehensive mathematical formulas, polygon unclip proofs, and execution benchmarks, see [`docs/TECHNICAL_STACK_AND_PIPELINES.md`](docs/TECHNICAL_STACK_AND_PIPELINES.md).

---

## Usage

### 1. Control Center
- **Capture Source:** Select the primary display or target a specific media player window.
- **Language Routing:** Choose dialogue source language (Auto-Detect, English, Indonesian, Japanese, Chinese, Korean) and destination language.
- **Live Preview:** Monitor screen capture, frame variance telemetry, and real-time OCR text recognition.

### 2. Subtitle Positioning & Styling
- **Input Transparency:** By default, mouse clicks pass directly through the subtitle overlay to the underlying media player.
- **Repositioning:** Toggle interactive mode in Control Center to unlock the canvas, drag the overlay to any screen position, and lock it back in place.
- **Typography:** Configure font size, stroke color, and outline width adhering to high-contrast WCAG AA readability standards.

### 3. Translation Configuration (BYOK)
- Configure any OpenAI-compatible base URL, model name, and API key under the Translation tab.
- API keys are persisted locally with `0600` permissions and masked in the user interface.

---

## Project Structure

```text
subterranean-staircase/
├── src/                    # Frontend shell (Vite, TypeScript, Tailwind CSS)
│   ├── main.ts             # Control Center dashboard logic and IPC handlers
│   ├── overlay.ts          # Transparent click-through subtitle renderer
│   ├── utils.ts            # Formatting utilities and data contracts
│   └── styles.css          # Design system and typography styles
├── src-tauri/              # Native backend daemon (Rust)
│   ├── Cargo.toml          # Rust dependencies and binary targets
│   ├── tauri.conf.json     # Window topology and capabilities manifest
│   └── src/
│       ├── lib.rs          # Application state, commands, and IPC bridge
│       ├── capture.rs      # Native display and window capture driver
│       ├── diff.rs         # SIMD Mean Absolute Difference frame-diff gating
│       ├── ocr/            # On-device neural OCR pipeline
│       │   ├── dbnet.rs    # DBNet text detection and polygon unclip math
│       │   ├── rec.rs      # Text recognition strip normalizer
│       │   ├── ctc.rs      # Native CTC greedy token decoder
│       │   └── spatial.rs  # Dual-band spatial filter and sentence debouncer
│       ├── translate.rs    # Universal cloud LLM client and offline fallback
│       ├── cache.rs        # SQLite WAL high-concurrency translation memory
│       ├── overlay.rs      # Native macOS Cocoa window layering bindings
│       └── pipeline.rs     # Background orchestrator thread and state machine
├── docs/                   # Architectural specifications and pipeline formulas
├── scripts/                # Benchmark evaluation runner and dataset generator
├── tests/fixtures/         # Heterogeneous benchmark frames and manifests
├── index.html              # Control Center HTML template
└── overlay.html            # Subtitle Overlay HTML template
```

---

## License

MIT
