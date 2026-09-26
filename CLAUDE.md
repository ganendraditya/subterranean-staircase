# Engineering & Design Architecture (Karpathy, Anti-Slop, & Core Principles)

This project incorporates engineering discipline, architectural principles, and design standards from:
1. **Andrej Karpathy's LLM Guidelines**
2. **Anti-Slop Craftsmanship Framework**
3. **Core Software Engineering & System Architecture Principles** (derived from `koma` & `not-notebooklm`)

---

## Part 1: Core Architectural Principles (SOLID, Orthogonality, & Boundaries)

These principles govern all code design, refactoring, and implementations in this repository:

### 1. Orthogonality (Loose Coupling)
Modules must be designed to stand independently without hidden side-effects:
- Modifying screen capture drivers (macOS vs Windows) must **never** touch the OCR engine or UI overlay.
- Upgrading or swapping the OCR model (RapidOCR vs future model) must **never** affect the translation router.
- Swapping translation providers (local CTranslate2 vs Cloud API) must **never** break the downstream subtitle renderer.
- Changes in PyQt6 styling or layout must **never** alter domain contracts or backend IPC pipelines.

### 2. Dependency Inversion (DIP) & Program Against Abstractions
- High-level orchestration must depend strictly on abstract contracts, not concrete implementations.
- All drivers and engines implement explicit base interfaces (e.g. `BaseCapture`, `BaseOCR`, `BaseTranslator`).
- Downstream renderers and orchestrators MUST NEVER consume raw model outputs or vendor-specific responses directly; all outputs are normalized to typed domain models (e.g. `SubtitleDetection`, `TranslationResult`).

### 3. Encapsulate What Varies
- Platform-specific logic (Windows Win32/DirectX APIs vs macOS Quartz/ScreenCaptureKit) must be strictly isolated inside `core/capture/platform/`.
- The rest of the application remains 100% platform-agnostic.

### 4. Tell, Don't Ask & Law of Demeter
- Components command collaborators to execute domain operations rather than inspecting their internal state to make procedural decisions externally.
- *Good:* `pipeline.process_frame(frame)`
- *Avoid:* UI code reaching into capture internals, extracting raw buffers, invoking OCR methods manually, and checking dictionary keys.

### 5. Single Responsibility (SRP) & Interface Segregation (ISP)
- Every file, class, and function has exactly one reason to change.
- Separate frame capture, frame-diff hashing, OCR inference, subtitle stabilization, and GUI rendering into isolated modules.
- Contracts and interfaces must remain granular; avoid monolithic god-objects.

### 6. DRY (Don't Repeat Yourself) Without Indirection
- Avoid duplicate calculation logic, regex patterns, or data models.
- Maintain single sources of truth in `core/contracts/` and `core/subtitle/`.
- Avoid empty re-exports or useless pass-through layers that add navigation friction without providing abstraction value.

### 7. YAGNI (You Aren't Gonna Need It)
- Build strictly for the active task's acceptance criteria.
- No speculative configurations, runtime DI containers, or unused plugin hooks until actually needed.

### 8. Reversibility & Fail-Safe Defaults
- State mutations, settings persistence, and worker threads must have clear teardown, cancellation, and fallback paths.
- If a capture frame drops or translation fails, the UI must gracefully retain or clear subtitles without crashing the application.

---

## Part 2: Engineering Execution Guidelines (Karpathy)

### 1. Think Before Coding
- **State assumptions explicitly.** If uncertain, ask rather than guess.
- **Surface tradeoffs.** If multiple approaches exist, compare them objectively.
- **Push back when warranted.** If a simpler, more reliable approach exists, speak up.
- **Stop when confused.** Never write speculative code based on ambiguous requirements.

### 2. Simplicity First
- **Minimum code that solves the problem.** Nothing speculative.
- No features beyond what was requested.
- No unnecessary abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- If 200 lines could be 50, simplify it.
- Ask: *"Would a senior engineer say this is overcomplicated?"* If yes, simplify.

### 3. Surgical Changes
- **Touch only what you must.** Clean up only your own mess.
- Don't "improve" adjacent code, comments, or formatting unnecessarily.
- Don't refactor things that aren't broken.
- Every changed line must trace directly to the user's request.

### 4. Goal-Driven Execution
- **Define success criteria. Loop until verified.**
- Transform tasks into verifiable criteria (write test/smoke script, verify, commit).
- Loop independently against tangible feedback before declaring done.

---

## Part 3: UI & Craftsmanship Filter (Anti-Slop)

Whenever building or refining the UI (PyQt6 Overlay, Settings, Dialogs):
- **Purpose over decoration:** No random glows, generic pill badges, or template fluff without a clear functional reason.
- **High contrast & readability:** Subtitle overlays must maintain WCAG AA contrast (crisp text stroke/drop shadow, legible over light and dark media).
- **Resilience:** All states must be handled (empty text, loading model, capture pause, error states).
- **Keyboard accessible:** Every dialog and settings window must be navigable via keyboard (`Tab`, `Enter`, `Escape`).
- **Functional completeness:** No dead buttons, non-functional sliders, or dummy UI elements.
