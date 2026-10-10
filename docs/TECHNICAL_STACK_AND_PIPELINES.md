# Technical Stack, Pipeline Architecture & Mathematical Specifications

> Comprehensive engineering specification for **Subterranean Staircase (Subtitle Translator)**: a private, ultra-low latency on-device desktop subtitle translator for macOS and Windows, featuring localized OCR, quantized Neural Machine Translation (NMT), hybrid cloud LLM routing, and an Anti-Slop WCAG AA floating overlay.

---

## 1. High-Level System Architecture

Subterranean Staircase runs as an unprivileged native desktop daemon using an orthogonal, multi-threaded pipeline. Hardware capture, visual frame-diff gating, neural text detection/recognition, temporal sentence debouncing, translation engine routing, and hardware-accelerated GUI rendering are completely decoupled:

```text
+---------------------------------------------------------------------------------------------------+
|                           FRONTEND CLIENT & OVERLAY (PyQt6 Desktop Shell)                         |
|  - Unified Control Center (580x720 Scrollable QDialog): Live ROI OBS Monitor, Language Matrix,   |
|    Atomic Packs Table, Universal LLM Settings, Preferences, Session History Exporter (.srt/.vtt)  |
|  - SubtitleOverlayWindow: Transparent, Click-Through (WindowTransparentForInput), Frameless,      |
|    Bottom-Center Anchored (800x160), Anti-Slop WCAG AA High-Contrast Stroked Font                 |
|  - macOS WindowServer Privilege: NSScreenSaverWindowLevel (1000) + FullScreenAuxiliary Spaces      |
+-------------------------------------------------+-------------------------------------------------+
                                                  | UI Commands / Events (Qt Signals & Slots)
                                                  v
+---------------------------------------------------------------------------------------------------+
|                         BACKGROUND PIPELINE WORKER (TranslationPipelineWorker QThread)            |
|                                                                                                   |
|  +---------------------------------------------------------------------------------------------+  |
|  | [1] Screen & Window Capture Abstraction (BaseCapture)                                        |  |
|  |     • macOS Native: Apple Quartz / ScreenCaptureKit (CGWindowListCreateImage)               |  |
|  |     • Windows Native: DirectX / Win32 (BitBlt / PrintWindow)                                |  |
|  |     • Universal Fallback: Fast memory-mapped mss                                             |  |
|  |     • Frame Output: BGR NumPy Buffer (W x H x 3) + Timestamp                                 |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 | Raw Frame @ 10 FPS                              |
|                                                 v                                                 |
|  +---------------------------------------------------------------------------------------------+  |
|  | [2] Perceptual Vision Gating (FrameDiffDetector)                                            |  |
|  |     • Pixel Downsampling + Mean Absolute Difference (Threshold: 1.5% variance)              |  |
|  |     • If scene is static: Short-circuit, bypass 100% of OCR compute (Saves CPU & Battery)    |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 | Changed Frame Buffer                            |
|                                                 v                                                 |
|  +---------------------------------------------------------------------------------------------+  |
|  | [3] Neural OCR Inference Engine (RapidOCR ONNX Runtime)                                     |  |
|  |     • Text Detection: DBNet (det_limit_type='max', det_unclip_ratio=2.0)                      |  |
|  |     • Text Recognition: SVTR / MobileNetV4 CTC ONNX Models                                  |  |
|  |     • Output: List[SubtitleDetection] (bounding polygon, confidence, text)                   |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 | Detections                                      |
|                                                 v                                                 |
|  +---------------------------------------------------------------------------------------------+  |
|  | [4] Subtitle Intelligence & Signal Stabilization (core/subtitle/)                            |  |
|  |     • DualBandSpatialFilter: Priority scanning (top 20%, bottom 30%); rejects middle slides |  |
|  |     • SubtitleTextFilter: Regex-free Unicode token filtering & watermark noise purge        |  |
|  |     • SubtitleHistoryTracker: Jaccard token similarity temporal stabilization               |  |
|  |     • Sentence Debouncer: 0.12s cooldown on streaming subtitles to avoid fragment drops     |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 | Stabilized Clean Sentence String                |
|                                                 v                                                 |
|  +---------------------------------------------------------------------------------------------+  |
|  | [5] Translation Engine Routing (Local CTranslate2 vs Universal OpenAI-Compatible LLM)       |  |
|  |     • Level 1 Cache: SQLite WAL Translation Memory (0ms repeated phrase recall)             |  |
|  |     • Offline Engine: CTranslate2 INT8 MarianMT (beam_size=3, English 2-Hop Pivot Matrix)    |  |
|  |     • Cloud/BYOK Engine: OpenAI-Compatible /v1/chat/completions (Groq, DeepSeek, Ollama)    |  |
|  |     • Fail-Safe Mechanism: Auto-fallback to local CTranslate2 on HTTP timeout or 429 error  |  |
|  +----------------------------------------------+----------------------------------------------+  |
|                                                 | Translated Subtitle Result                      |
|                                                 v                                                 |
+-------------------------------------------------+-------------------------------------------------+
                                                  | Qt Signal: subtitle_ready(translated_text)
                                                  v
                                     [ SubtitleOverlayWindow ]
```

---

## 2. Core Technology Stack Matrix

| Domain / Layer | Technology Component | Specification / Version | Architectural Purpose & Rationale |
| :--- | :--- | :--- | :--- |
| **Runtime Language** | Python | `>= 3.10` | High-level orchestration, rich computer vision ecosystem, fast native C++ FFI bridges. |
| **Desktop GUI Shell** | PyQt6 | `>= 6.6.0` | Cross-platform hardware-accelerated GUI shell; supports non-activating, translucent, frameless click-through overlays. |
| **Platform WindowServer (macOS)** | PyObjC (Quartz / AppKit) | `>= 10.0` | Native macOS window layering (`NSScreenSaverWindowLevel`), spaces manipulation, and active space change observation. |
| **Platform WindowServer (Windows)** | `ctypes` / Win32 | Native OS | User32/Gdi32 bindings for HWND enumeration, desktop capture, and input transparency flags. |
| **Screen Grabber** | Quartz / MSS | `mss >= 9.0.0` | Ultra-fast memory-mapped screen buffer grabbing with zero window bleeding. |
| **Computer Vision Pre-processing** | OpenCV | `opencv-python-headless >= 4.9.0` | Fast NumPy BGR frame manipulation, ROI slicing, and pixel variance calculations. |
| **Neural OCR Engine** | RapidOCR + ONNX Runtime | `rapidocr-onnxruntime >= 1.3.0` | Standalone C++ ONNX text detection and recognition without heavy PyTorch/PaddlePaddle bloat. |
| **Offline NMT Engine** | CTranslate2 | `ctranslate2 >= 4.0.0` | Custom C++ Transformer inference engine with INT8 quantization, multithreading, and zero Python GIL contention. |
| **Tokenization** | SentencePiece | `sentencepiece >= 0.2.0` | Subword BPE tokenizer used by MarianMT neural models. |
| **Local Translation Memory Cache** | SQLite (WAL Mode) | Python `sqlite3` | High-concurrency Write-Ahead Logging cache; guarantees 0ms recall for previously seen phrases. |
| **Session History Recorder** | SQLite (WAL Mode) | `core/storage/history.py` | Transactional storage of subtitle cues with millisecond timestamps; exports to SubRip (`.srt`) and WebVTT (`.vtt`). |
| **Cloud Translation Engine** | Universal OpenAI Protocol | `core/translate/llm.py` | Pure standard-library HTTP client (`/v1/chat/completions`) compatible with Groq, DeepSeek, OpenAI, and Ollama. |
| **Data Contract Validation** | Pydantic / Dataclasses | `pydantic >= 2.6.0` | Strict, immutable typed contracts enforcing Dependency Inversion (DIP) across module boundaries. |
| **Standalone Distribution** | PyInstaller + Inno Setup + hdiutil | `pyinstaller >= 6.0.0` | Self-contained packaging into macOS `.dmg` and Windows `Setup.exe` with zero external prerequisites. |

---

## 3. Computer Vision & OCR Tuning Specifications

### 3.1 Perceptual Frame-Diff Gating (100% Idle Conservation)
Video subtitles only change when an actor speaks or a new dialogue line appears. Running OCR at 10 FPS on static scenes wastes excessive CPU cycles and drains laptop batteries.
* **Algorithm:** Pixel downsampling to $64 \times 36$ followed by Mean Absolute Difference:
  $$\Delta = \frac{1}{N} \sum_{i=1}^N \frac{|I_t(i) - I_{t-1}(i)|}{255}$$
* **Threshold:** $\Delta \ge 0.015$ (1.5% variance).
* **Short-circuiting:** If $\Delta < 0.015$ and the history tracker has no pending unstable sentences, OCR is completely bypassed, reducing CPU overhead by over 80% during dialogues.

### 3.2 DBNet Detection Scaling (`det_limit_type='max'`)
Standard PaddleOCR/RapidOCR defaults to `det_limit_type='min'`, which scales images so that the *shorter* edge equals 736px. On 1080p/4K wide video frames, this causes severe aspect-ratio distortion and inflates the image to over $2000 \times 1300$, causing massive inference latency.
* **Our Tuning:** Set `det_limit_type='max'`, ensuring the *longer* dimension is clamped to 736px. Aspect ratios are preserved, and inference latency is reduced from ~400ms down to **~120-150ms**.

### 3.3 Glyph Descender Protection (`det_unclip_ratio=2.0`)
DBNet outputs a shrunk kernel of text regions that must be expanded back using the Vatti clipping algorithm.
* **Problem:** Default `unclip_ratio=1.5` frequently chops descenders (e.g. `g`, `y`, `p`, `j`, `,`, `.`) and diacritics in foreign fonts.
* **Our Tuning:** Tuned to `det_unclip_ratio=2.0`, capturing the full vertical extent of stylized subtitle fonts and commas.

---

## 4. Subtitle Intelligence & Temporal Stabilization

```text
[ Raw OCR Detections ]
          │
          ▼
┌──────────────────────────────────────────────┐
│ 1. DualBandSpatialFilter                     │
│    • In Full Screen: Prioritizes top 20%     │
│      and bottom 30% bands.                   │
│    • Rejects middle slides & UI clutter.     │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 2. SubtitleTextFilter                        │
│    • Regex-free Unicode codepoint inspection │
│    • Strips watermark noise & punctuation bug│
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 3. SubtitleHistoryTracker                    │
│    • Jaccard Token-Level Similarity (>= 0.60)│
│    • Multi-frame confirmation (min_count=2)  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│ 4. Sentence Debouncing                       │
│    • Cooldown: 0.12s on progressive text     │
│    • Waits for completed thought before NMT  │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
         [ Stabilized Dialogue Line ]
```

### 4.1 Regex-Free Unicode Tokenization & Jaccard Similarity
To maintain high throughput on battery power, tokenization uses pure Unicode code point ranges without regular expressions:
* CJK (`0x4E00`–`0x9FFF`), Hiragana (`0x3040`–`0x309F`), Katakana (`0x30A0`–`0x30FF`), and Hangul (`0xAC00`–`0xD7AF`) are partitioned into discrete single-character tokens.
* Latin/alphanumeric words are delimited by whitespace and punctuation.
* Two detected text boxes $A$ and $B$ are matched using Jaccard token similarity:
  $$J(A, B) = \frac{|T_A \cap T_B|}{|T_A \cup T_B|}$$
  If $J(A, B) \ge 0.60$, detections are clustered as the same moving or updating subtitle cue.

### 4.2 Progressive Sentence Debouncing (0.12s)
Streaming captions (such as YouTube auto-captions) frequently render word-by-word. Sending partial fragments (e.g. *"I remember"*, *"I remember I"*, *"I remember I had"*) to NMT creates choppy UI updates and translation errors.
* **Debounce Rule:** If an incoming stable string extends the previous fragment ($S_{t}.startswith(S_{prev})$) and elapsed time $\Delta t < 0.12$ seconds, NMT dispatch is delayed until the thought completes or pauses.

---

## 5. Machine Translation Routing & Model Parameters

### 5.1 CTranslate2 Beam Decoding Tuning (`beam_size=3`)
* **Beam 1 (Greedy):** ~73ms latency, but struggles with long compound sentences and complex syntax.
* **Beam 2:** ~94ms latency, but prone to omitting rare entities (e.g. dropping *"Toy Story"*) or hallucinating repetitive scriptural phrases on poetic metaphors.
* **Beam 3 (Our Standard):** **~99-108ms latency**. Eliminates entity dropouts, provides natural Indonesian grammar (*"berusia 30 tahun"* instead of literal *"berbalik 30"*), and completely eliminates degenerative hallucination loops without perceptible latency penalty (+5ms vs Beam 2).

### 5.2 Symmetric Big 5 Language Matrix & English Pivot
The Big 5 matrix supports **English (en), Indonesian (id), Japanese (ja), Korean (ko), and Chinese (zh)**:
* **Direct Route:** If a direct model exists (e.g. `en-id`, `id-en`, `ja-en`, `zh-en`), inference executes directly in 1 hop.
* **2-Hop English Pivot:** If no direct paired model exists (e.g. `ja -> id` or `ko -> id`), the router dynamically executes:
  $$\text{Source} \xrightarrow{\text{Hop 1}} \text{English} \xrightarrow{\text{Hop 2}} \text{Target}$$
  Both hops are cached individually in the SQLite WAL cache, ensuring intermediate English phrases are instantly reused.

### 5.3 Universal OpenAI-Compatible Cloud LLM Provider
For users who prefer slang-aware, contextual translations via Bring-Your-Own-Key (BYOK):
* **Standard Protocol:** Uses `/v1/chat/completions` with pure Python standard library `urllib` (no external SDK bloat).
* **Universal Compatibility:** Works seamlessly with Groq (`llama-3.3-70b-versatile`), DeepSeek (`deepseek-chat`), OpenAI (`gpt-4o-mini`), OpenRouter, or local Ollama instances (`http://localhost:11434/v1`).
* **Direct Subtitle System Prompt:**
  > *"You are a professional real-time subtitle translator. Translate the following subtitle line from {Source} to {Target}. Output ONLY the direct translated text. Do NOT include explanations, notes, quotes, or markdown formatting."*
* **Automatic Code-Fence Sanitization:** Strips accidental wrapping quotes and Markdown blocks (````markdown ... ````).
* **Fail-Safe Local Fallback:** If network connection fails, times out (>3.0s), or returns HTTP 429 rate limits, the pipeline immediately falls back to offline local CTranslate2 without dropping the subtitle.

---

## 6. Floating Overlay & macOS WindowServer Privilege

### 6.1 Native macOS Fullscreen Spaces & Level Floating
When video players (such as YouTube in Safari/Firefox) enter native macOS Fullscreen mode, the OS moves the video into an isolated virtual desktop Space. Standard floating windows (Level 3) are trapped in Desktop 1.
* **Window Configuration (`ui/overlay.py`):**
  ```python
  behavior = (
      NSWindowCollectionBehaviorCanJoinAllSpaces
      | NSWindowCollectionBehaviorFullScreenAuxiliary
      | NSWindowCollectionBehaviorStationary
  )
  nswindow.setCollectionBehavior_(behavior)
  nswindow.setLevel_(NSScreenSaverWindowLevel)  # Level 1000
  nswindow.setHidesOnDeactivate_(False)
  ```
* **Dynamic Activation Policy:** When translation is active, the app switches to `NSApplicationActivationPolicyAccessory`, granting it auxiliary status across Spaces. When Control Center opens, it switches back to `Regular` so the window is easily accessible.
* **Space Transition Listener:** Subscribes to `NSWorkspaceActiveSpaceDidChangeNotification`. When the user enters fullscreen (`F` key), the overlay detects the space change and calls `orderFrontRegardless()`.

### 6.2 Anchored Bottom-Center Canvas (800x160)
* **Problem:** Subtitle lengths vary from 1 short word to 3 full lines. If the overlay resizes its window based on top-left coordinates, the window erratically jumps across the screen.
* **Our Architecture:**
  - Bounding canvas has fixed stability ($800 \times 160$ px).
  - Subtitle text renders aligned to the **bottom boundary** (`AlignBottom`).
  - As dialogue grows from 1 line to 3 lines, text naturally **expands upwards** like standard cinema/Netflix subtitles, while the baseline anchor remains rock solid.
* **Interactive Repositioning Mode:**
  - Control Center toggle `Move Subtitles` temporarily disables `WindowTransparentForInput`.
  - Displays an elegant cyan dashed outline (`#00E5FF`) with `SizeAllCursor`.
  - While dragging, coordinates update in memory; upon mouse release (`mouseReleaseEvent`), final `(center_x, bottom_y)` coordinates are atomically persisted to `config.json`.

---

## 7. Packaging & Cross-Platform Distribution Matrix

Standalone release binaries bundle all Python runtimes, C++ dynamic libraries, and neural model files into a single zero-dependency installer:

| Platform | Runner / Architecture | Packaging Engine | Output Artifact |
| :--- | :--- | :--- | :--- |
| **macOS (Apple Silicon)** | `macos-14` (`arm64`) | PyInstaller + native `hdiutil` | `Subterranean-Staircase-macos-arm64.dmg` |
| **macOS (Intel)** | `macos-14` (`x86_64` via Rosetta) | PyInstaller + native `hdiutil` | `Subterranean-Staircase-macos-x86_64.dmg` |
| **Windows 64-bit** | `windows-2022` (`x64`) | PyInstaller + Inno Setup 6 | `Subterranean-Staircase-windows-x64-Setup.exe` & `.zip` |

* **macOS Drag-and-Drop DMG:** Built with native `hdiutil create` using an isolated temporary staging directory, featuring a symlink to `/Applications`.
* **Windows Setup Wizard:** Built with Inno Setup using LZMA2 ultra compression, bundling uninstaller, Start Menu shortcut, and optional Startup shortcut.
* **CI/CD Integrity Smoke Verification:**
  - macOS runners verify DMG integrity using `hdiutil verify` and validate Mach-O binary architecture using `lipo -info`.
  - Windows runners verify non-zero byte artifacts and executables before uploading to GitHub Releases.

---

## 8. Uninstallation & Data Purge Protocols (0-Byte Hygiene)

Subterranean Staircase implements zero-byte data purge workflows across all supported platforms to ensure complete privacy and prevent orphan disk bloat:

* **Windows GUI Uninstaller (`scripts/installer.iss`):**
  - Features an interactive Pascal Script callback during uninstallation (`CurUninstallStepChanged`).
  - Prompts the user: *"Do you also want to completely delete all downloaded translation models, caches, and user configurations?"*
  - When confirmed, recursively deletes `%LOCALAPPDATA%\SubtitleTranslator`, `%APPDATA%\subtitle-translator`, `~/.config/subtitle-translator`, and `~/.cache/subtitle-translator` using `DelTree`.
* **macOS GUI Clean Wipe (Control Center Factory Reset):**
  - Features a dedicated **"Factory Reset..."** button in Control Center under Appearance & Preferences.
  - Upon confirmation, halts active background pipelines, closes SQLite connections, and wipes `~/.cache/subtitle-translator` (including all MarianMT quantized models and databases) and `~/.config/subtitle-translator/config.json`, resetting in-memory state to factory defaults.
* **Terminal CLI Uninstaller (`uninstall.sh` / `uninstall.ps1`):**
  - Canonical `subtrans uninstall` command provides interactive prompt to retain or purge data.
  - `subtrans uninstall --purge` performs non-interactive 100% removal down to 0 bytes.

---

## 9. V2 Architecture: Native Rust + Tauri v2 Subsystem Specifications

The `v2.0.0` milestone introduces an ultra-performant native desktop architecture replacing Python/PyQt6 with Rust and Tauri v2:

```text
+---------------------------------------------------------------------------------------------------+
|                        FRONTEND WEBVIEW (Vite + TypeScript + Tailwind CSS)                       |
|  - Control Center (`index.html`): Capture Target, Language Pair, Cloud LLM BYOK, Live Preview      |
|  - Subtitle Overlay (`overlay.html`): High-Contrast WCAG AA Frameless Click-Through Window        |
+-------------------------------------------------+-------------------------------------------------+
                                                  | Tauri v2 IPC Commands & Events
                                                  v
+---------------------------------------------------------------------------------------------------+
|                            NATIVE TAURI DAEMON IN RUST (`src-tauri`)                              |
|                                                                                                   |
|  [Phase 2] Dual-Window System (`overlay.rs`)                                                      |
|      • macOS Cocoa: NSScreenSaverWindowLevel (1000), NSWindowCollectionBehaviorFullScreenAuxiliary |
|      • Windows User32: WS_EX_LAYERED, WS_EX_TRANSPARENT (Click-through)                           |
|                                                                                                   |
|  [Phase 3] Native Screen Capture & SIMD Vision Gating (`capture/`, `diff.rs`)                     |
|      • Screen & Window Acquisition: Quartz / DXGI via zero-copy `xcap` crate                      |
|      • Perceptual Frame-Diff: SIMD Mean Absolute Difference (MAD) evaluated in < 0.2 ms           |
|      • Static Frame Gating: Bypasses downstream inference when scene variance < 1.5%              |
|                                                                                                   |
|  [Phase 4] Universal Cloud LLM Provider & SQLite WAL Cache (`translate.rs`, `cache.rs`)          |
|      • HTTP Client: Asynchronous `reqwest` + `tokio` (rustls-tls, hermetic OpenSSL-free)          |
|      • OpenAI /v1/chat/completions Protocol: Groq, DeepSeek, OpenAI, Ollama, vLLM                 |
|      • SSRF Mitigation: Strict scheme validation (HTTP/HTTPS only), cloud metadata IP rejection   |
|        (169.254.169.254 and IPv6 link-local blocked)                                              |
|      • Translation Memory: Embedded SQLite WAL (`PRAGMA journal_mode=WAL; synchronous=NORMAL`)    |
|      • Sub-Millisecond Recall: Instant retrieval for repetitive dialogue with LRU eviction        |
|      • Credential Protection: Permissions 0600 on config files, masked IPC keys (••••••••)        |
|                                                                                                   |
|  [Phase 5] Neural OCR Pipeline in Rust (`ocr/`, `ort`, `dbnet.rs`, `rec.rs`)                       |
|      • ONNX Runtime Engine: Multi-threaded CPU (`ort` v2) with zero Python GIL contention         |
|      • DBNet Text Detection: Aspect-ratio preserving resize (`det_limit_type="max"`) &           |
|        polygon unclip expansion (`unclip_ratio = 2.0` via `clipper2-rust`)                        |
|      • SVTR / PP-OCR Text Recognition: Bounding strip normalization & logit extraction            |
|      • Native CTC Greedy Decoder: Maps character indices across Big 5 scripts with 0 blank leaks  |
|      • Subtitle Stabilization: Dual-band spatial screening & temporal sentence debouncing (0.12s) |
|      • Measured Latency: End-to-end OCR inference executes in ~28.3 ms (3x faster than 90 ms goal)|
+---------------------------------------------------------------------------------------------------+
```

### 9.1 High-Concurrency Translation Memory Specifications
- **Database Engine:** Embedded `rusqlite` bundled with SQLite 3.
- **Concurrency Mode:** `PRAGMA journal_mode = WAL;` (readers never block writers, writers never block readers).
- **Disk Synchronization:** `PRAGMA synchronous = NORMAL;` with `PRAGMA busy_timeout = 5000;`.
- **Primary Key & Indexing:** Composite primary key `(source_text, source_lang, target_lang)` with LRU index on `last_accessed` timestamp for deterministic eviction when table size reaches `max_entries = 10,000`.
- **Measured Latency:** Indexed in-memory/WAL cache hits resolve in $< 0.1\,\text{ms}$, completely bypassing network sockets.

### 9.2 Universal Cloud LLM Engine & Security Hardening
- **Protocol:** Standard `/v1/chat/completions` REST request using JSON payloads.
- **SSRF Mitigation:** Base URLs undergo URL parsing where only `http` and `https` schemes are allowed. Local development endpoints (`localhost`, `127.0.0.1`) remain permitted for local inference daemons (Ollama / vLLM), while link-local and cloud metadata addresses (`169.254.169.254`, `fe80::/10`) are strictly rejected.
- **Timeout Bound Checking:** Configured timeouts are clamped between $1\,\text{s}$ and $120\,\text{s}$ to prevent 64-bit integer overflows in Tokio timer allocations.
- **Credential Hygiene:** API keys saved to disk use POSIX `0o600` permissions. When retrieved by frontend views, keys are masked (`••••••••`) to prevent DOM-based secret leakage. Save operations preserve existing keys if the mask or empty string is submitted.

### 9.3 Neural OCR Pipeline & Native CTC Decoding Specifications
- **Inference Runtime:** `ort` (ONNX Runtime v2) configured with Level 3 graph optimization and multi-threaded CPU execution with zero Python GIL contention.
- **DBNet Geometry & Unclip Algorithm:**
  - Input scaling clamps maximum dimension to `limit_side_len = 736` rounded to multiples of 32, preserving native aspect ratio without distortion.
  - Heatmap probability thresholding (`thresh = 0.3`) followed by contour extraction (`imageproc::contours`).
  - Polygon unclip expansion using Vatti polygon offsetting (`clipper2-rust`) with $D = \frac{\text{Area} \times 2.0}{\text{Perimeter}}$ to guarantee complete preservation of lower descenders (`g`, `y`, `p`, `,`).
- **Recognition & CTC Decoding:**
  - Cropped subtitle strips are normalized to height 48 with aspect-preserving width, normalized to $[-1.0, 1.0]$.
  - Native Rust CTC greedy decoding parses logit tensors, collapses consecutive repeated tokens, discards CTC blank tokens (index 0), and maps indices to 6,625 dictionary characters (Big 5: Latin, Kanji, Hanzi, Kana, Hangul).
  - Measured end-to-end latency executes in $\le 30\,\text{ms}$, surpassing the $\le 90\,\text{ms}$ acceptance criterion.
- **Spatial & Temporal Debouncing:**
  - Dual-band spatial filtering protects full-screen views (top 20% / bottom 30%) while bypassing compact subtitle ROIs.
  - Natural reading-order sorting applies line-height binning (20px) to sort left-to-right on identical horizontal lines before top-to-bottom.
  - Progressive sentence debouncing enforces a 0.12s cooldown on streaming word extensions.


