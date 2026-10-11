# Engineering & Design Architecture (Anti-Slop & Core Principles)

This project incorporates engineering discipline, architectural principles, and design standards from:
1. **Pragmatic Engineering & Execution Guidelines**
2. **Anti-Slop Craftsmanship Framework**
3. **Core Software Engineering & System Architecture Principles** (derived from `koma` & `not-notebooklm`)

---

## Part 1: Core Architectural Principles (SOLID, Orthogonality, & Boundaries)

These principles govern all code design, refactoring, and implementations in this repository:

### 1. Orthogonality (Loose Coupling)
Modules must be designed to stand independently without hidden side-effects:
- Modifying screen capture drivers (macOS Quartz vs Windows DXGI) must **never** touch the OCR engine or UI overlay.
- Upgrading or swapping the OCR model (RapidOCR vs `ort` DBNet/SVTR) must **never** affect the translation router.
- Swapping translation providers (local CTranslate2 vs Universal Cloud LLM) must **never** break the downstream subtitle renderer.
- Changes in frontend styling (Tailwind CSS/Vite) must **never** alter domain contracts or native IPC pipelines.

### 2. Dependency Inversion (DIP) & Program Against Abstractions
- High-level orchestration must depend strictly on abstract contracts, not concrete implementations.
- All drivers and engines implement explicit base interfaces (e.g. `BaseCapture`, `BaseOCR`, `BaseTranslator`).
- Downstream renderers and orchestrators MUST NEVER consume raw model outputs or vendor-specific responses directly; all outputs are normalized to typed domain models (e.g. `SubtitleDetection`, `TranslationResult`, `SubtitlePayload`).

### 3. Encapsulate What Varies
- Platform-specific logic (Windows Win32/DirectX APIs vs macOS Quartz/Cocoa/ScreenCaptureKit) must be strictly isolated inside `src-tauri/src/capture/platform/` or `core/capture/platform/`.
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
- Maintain single sources of truth in `core/contracts/`, `src/utils.ts`, and `src-tauri/src/overlay.rs`.
- Avoid empty re-exports or useless pass-through layers that add navigation friction without providing abstraction value.

### 7. YAGNI (You Aren't Gonna Need It)
- Build strictly for the active task's acceptance criteria.
- No speculative configurations, runtime DI containers, or unused plugin hooks until actually needed.

### 8. Reversibility & Fail-Safe Defaults
- State mutations, settings persistence, and worker threads must have clear teardown, cancellation, and fallback paths.
- If a capture frame drops or translation fails, the UI must gracefully retain or clear subtitles without crashing the application.

---

## Part 2: Engineering Execution Guidelines (Pragmatic Simplicity & Discipline)

### 1. Think Before Coding
- **State assumptions explicitly.** If uncertain, ask rather than guess.
- **Surface tradeoffs.** If multiple approaches exist, compare them objectively.
- **Push back when warranted.** If a simpler, more reliable approach exists, speak up.
- **Stop when confused.** Never write speculative code based on ambiguous requirements.

### 2. Simplicity First
- **Minimum code that solves the problem.** Nothing speculative.
- No features beyond what was requested.
- No abstractions for single-use code.
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

### 5. Developer Toolchain & Lockfile Discipline (Bun & npm)
- **Local macOS Optimization (Bun):** When `bun` is available on the local environment, developers and AI agents **strictly prefer `bun`** (`bun run check`, `bun run test`, `bun run build`, `bun add`) for sub-second execution speeds and lower idle memory.
- **Test Runner Protocol:** Always invoke frontend test suites via `bun run test` (or `npm test`) so that `vitest run` and `cargo test` execute together.
- **Universal Git & CI Parity:** `package-lock.json` remains the strict, authoritative package lockfile in version control to guarantee deterministic builds in GitHub Actions CI (`.github/workflows/ci.yml`) and across all contributor environments. Do not commit alternative lockfiles that displace `package-lock.json`.

---

## Part 3: UI & Craftsmanship Filter (Anti-Slop)

Whenever building or refining the UI (Tauri Webview, Control Center, Subtitle Overlay):
- **Purpose over decoration:** No random glows, generic pill badges, or template fluff without a clear functional reason.
- **High contrast & readability:** Subtitle overlays must maintain WCAG AA contrast (crisp text stroke/drop shadow, legible over light and dark media).
- **Resilience:** All states must be handled (empty text, loading model, capture pause, error states).
- **Keyboard accessible:** Every dialog and settings window must be navigable via keyboard (`Tab`, `Enter`, `Escape`).
- **Functional completeness:** No dead buttons, non-functional sliders, or dummy UI elements.

---

## Part 4: Code Review, Security Auditing Protocol & Git Merge Discipline

When conducting AI Code Reviews (via `ocr review`, multi-model LLM evaluations, or manual diff inspection) and security reviews, the agent **MUST NOT ACCEPT REVIEWER FINDINGS AT FACE VALUE OR ACT AS A SYCOPHANT TO REVIEW BOTS**, and must strictly obey git authorization invariants:

### 1. Strict Git Invariant: FORBIDDEN AUTO-COMMIT / AUTO-PUSH / AUTO-MERGE
- **Strict User Authorization Gate:** The agent is **STRICTLY FORBIDDEN** from running `git commit`, `git push`, creating tags, or merging branches autonomously without an **explicit instruction** from the user ("commit now", "push now", "ok commit", "merge", etc.).
- **Mandatory Pull Request Lifecycle (No Naked Merges into `main` or `v2-develop`):**
  - Every non-trivial feature, refactor, or bugfix **MUST** transition through a formal GitHub Pull Request (`gh pr create`) before being merged into integration branches (`v2-develop`) or `main`. Direct or naked branch merges without an associated PR are strictly forbidden.
  - **Standard Engineering Lifecycle:**
    1. **Branch & Implement:** Develop on an isolated branch (`feat/<name>-#<id>`, `fix/<name>-#<id>`).
    2. **Local Verification:** Run test suites (`bun run check`, `bun run test`, `./.venv/bin/pytest`).
    3. **Push & Open PR:** Push the feature branch and open a PR via `gh pr create` linking the relevant issue (`Closes #<id>`).
    4. **AI Code Review on PR:** Execute multi-model code review across the PR diff.
    5. **Dialectical Verification & Scorecard:** Present findings to the user (Confirmed Bugs vs False Positives). Apply verified fixes surgically.
    6. **User Authorization Gate:** Present the clean PR status and await explicit user instruction to merge.
    7. **Merge:** Merge via `gh pr merge --merge` (or `--delete-branch`) only after explicit user approval.
- **Report Status First:** Upon task completion, present a concise summary of changes, test suite results, and linter status, and await user instruction. Inquiring for confirmation ("Would you like to commit / merge?") is permitted, but executing commit/push/merge without explicit confirmation is prohibited.
- **Living Architecture Specification Synchronization:** Whenever system architecture, engine dependencies, tuning parameters, or core operational workflows are committed or merged, `docs/TECHNICAL_STACK_AND_PIPELINES.md` **MUST BE SYNCHRONIZED** so the documentation remains an accurate reference for continuous study and architectural truth.
- **Strict English Consistency Across Repository Artefacts:** All documentation files (`*.md`), technical specifications, GitHub Issues, Pull Request descriptions, Git commit messages, and GitHub Release notes **MUST BE WRITTEN EXCLUSIVELY IN CLEAR, CONCISE ENGLISH**. Maintain strict language consistency across all repository artefacts for international open-source parity.

### 2. Mandatory User Presentation Before Applying Changes
- The agent is **STRICTLY FORBIDDEN** from unilaterally modifying code, committing, or merging fixes immediately after receiving automated review comments without first presenting the findings dialectically to the user.
- Present a structured scorecard: categorize items into **Hard Blockers / Confirmed Bugs** vs **False Positives / Rejected Claims** vs **Architectural Optimizations**, complete with reproduction proof.

### 3. Multi-Model Review & Workload-Calibrated Strategy (`ocr review`, `ocr scan`, & `security-audit`)
Never rely on a single LLM reviewer's perspective for critical code reviews, whole-repo scans, or vulnerability discovery. Single models exhibit provider-specific blind spots, training biases, and sycophantic tendencies.

Employ a **Workload-Calibrated Model Strategy**:
1. **Targeted PR Reviews (`ocr review` on Git Diffs):**
   - Because PR diffs are lightweight and bounded in token volume, **dual-model evaluation** is enforced (e.g., cross-evaluating the diff with `claude-sonnet-4-6` paired with an independent frontier model such as `gemini-3.7-flash-low` or `gemini-3.8-flash-high`).
   - A finding is credible if both models agree on the defect mechanism or if an empirical test case confirms it.
2. **Full Subsystem Scans & Deep Security Audits (`ocr scan` & `security-audit`):**
   - Because scanning entire directories entails heavy token consumption and high timeout risks, do NOT run naive whole-directory scans through multiple models simultaneously. Instead, employ the **Two-Tier Triage Protocol**:
     - **Tier 1 (Broad Triage Scan):** Run the scoped subsystem scan using **1 primary frontier model** (`claude-sonnet-4-6` or `gemini-pro`) to surface initial prospective findings.
     - **Tier 2 (Adversarial Cross-Verification on High/Critical Findings):** Isolate the specific code contexts for any `High` or `Critical` severity findings and submit them to an independent second model specifically for adversarial verification (*"Model A flagged potential race condition/injection here; verify whether this is genuine or an LLM hallucination"*). Stylistic or low-severity suggestions do not require secondary model passes.

### 4. Empirical Verification Applied Universally (Anti-Hallucination across `ocr review`, `ocr scan`, & `security-audit`)
The verification protocol is non-negotiable across ALL automated scanning tools:

- **Never Assume Validity:** Treat reviewer comments with healthy skepticism. LLM reviewers frequently misread token-truncated code, misunderstand project conventions, or flag stylistic non-issues as critical security vulnerabilities.
- **Step 1: Problem Validity & Exploitability Check (Is this a genuine defect or a hallucination?):**
  - Define the Concrete Failure Scenario: *"Under what exact inputs, window bounds, display coordinates, or concurrency state does this failure occur, and what is the exact stack trace, exploit payload, or measurable impact?"*
  - Execute an Empirical Reproduction Script: Run a minimal terminal script, exploit PoC, synthetic frame injection, or test assertion (`bun run test`, `./.venv/bin/pytest`) to test the failure hypothesis.
  - Classification:
    - If reproduction confirms an actual error, crash, memory leak, security loophole, or measurable regression: classify as **CONFIRMED REAL ISSUE** with log/terminal evidence.
    - If reproduction passes cleanly, or the claim is based on truncated files, obsolete syntax, or false assumptions: reject the finding dialectically with proof as **FALSE POSITIVE / REJECTED**. Do not modify code for rejected items.
- **Step 2: Solution Validity & Orthogonality Verification:**
  - Never Blindly Apply Suggested Diff: Critically evaluate whether the suggested fix genuinely addresses the root cause or just silences a linter.
  - Surgical Implementation: Apply the verified solution with minimal footprint.
  - Dual Verification:
    1. Re-run the reproduction script from Step 1 to verify the defect is genuinely eliminated.
    2. Run full test suites (`bun run check`, `bun run test`, `./.venv/bin/pytest`) to verify zero regressions across neighboring systems (orthogonality).

### 5. Security Auditing Protocol for Desktop AI Daemon (Guidance Mode vs. Full Audit Mode)
Security audits evaluate local attack surfaces, high-privilege hardware access, native IPC trust boundaries, and cloud AI credentials:

- **Core Desktop Daemon Attack Surfaces in Subterranean Staircase:**
  1. *Tauri IPC & Webview Isolation (`src-tauri/src/lib.rs` & `capabilities/default.json`):* Enforce strict Tauri Capability boundaries and Content Security Policy (CSP). Never expose arbitrary shell execution, unauthenticated filesystem traversal, or dangerous native window handles to the frontend webview context.
  2. *BYOK Universal Cloud LLM Client & Credential Security (`src-tauri/` & `core/translate/llm.py`):*
     - Plaintext credential storage prevention: Do not persist raw API keys unencrypted on disk in `localStorage` or world-readable files.
     - SSRF Mitigation: Validate and sanitize custom `base_url` endpoints to prevent internal network scanning or local port hijacking (`http://localhost:*`, `http://127.0.0.1:*`, cloud metadata endpoints `http://169.254.169.254`).
     - Indirect Prompt Injection Defense: Subtitles extracted from untrusted third-party video frames (malicious OCR text attempting prompt jailbreaks like `"Ignore previous instructions and output..."`) must be encapsulated within structured delimiter blocks with strict translation system prompts.
  3. *Hardware Screen Capture & Raw Memory Safety (`core/capture/` & Rust Quartz/DXGI drivers):* High-frequency screen buffer acquisition (10–30 FPS) must maintain zero-copy memory safety, prevent buffer overflows in unsafe FFI code, and guarantee immediate, deterministic teardown of OS display handles upon application pause or system sleep.
  4. *Native C-ABI & Objective-C Unsafe Bounds (`src-tauri/src/overlay.rs` & CTranslate2 FFI):*
     - Raw pointer validity: All native pointers (`*mut c_void`, `NSWindow*`) must be checked for null before dereferencing.
     - C-ABI Type Alignment: Objective-C `BOOL` is `u8` across the Darwin ABI; function pointer transmutes must strictly match target platform calling conventions (AArch64 vs x86_64).
  5. *SQLite Persistence & Query Parameterization (`rusqlite` & `core/storage/`):* All translation caching and dialogue session queries must strictly use parameterized inputs (`params![]` / `?`), prohibiting raw string interpolation.

- **Operating Modes:**
  - **Guidance Mode (Per-Feature / Sensitive PR Reviews):**
    - *When to Use:* Triggered whenever a PR touches security-sensitive surfaces: Tauri IPC handlers (`src-tauri/src/lib.rs`), cloud LLM client/credentials (`core/translate/llm.py`), hardware capture drivers (`core/capture/`, `src-tauri/src/capture/`), or native FFI calls (`src-tauri/src/overlay.rs`).
    - *Execution:* Lightweight and targeted. Traces untrusted input to execution sinks without creating permanent overhead files.
  - **Full Audit Mode (Milestone & Pre-Release Baselines):**
    - *When to Use:* Prior to major version releases (`vX.Y.0`, e.g. `v2.0.0`), architectural shifts, or installer packaging.
    - *Execution:* Runs the formal multi-phase audit workflow (`security-audit` skill) with modular coverage ledgers (`coverage-ledger.json`) and structured reporting (`REPORT.md`). Always scope target paths rather than running unconstrained whole-repo scans.

### 6. Full Repository Review Protocol (`ocr scan` Anti-Timeout Execution)
- **Root Cause of Large Scan Hangs:** Running naive unflagged `ocr scan` attempts to evaluate all files indiscriminately, forcing the LLM reviewer to ingest massive binary ONNX models (`models/*.onnx`, `yolo/*.onnx`), raw test fixtures, and build artifacts (`target/`, `node_modules/`, `*.lock`). This blows through token budgets and triggers network gateway timeouts with zero output.
- **Mandatory Safe Execution Standard for Whole-Repo `ocr scan`:**
  1. **Mandatory Exclusions:** Always exclude binary models, image fixtures, lockfiles, and generated output:
     ```bash
     ocr scan --exclude '**/models/**,**/*.onnx,**/*.png,**/*.lock,target/**,node_modules/**' --no-plan --concurrency 8 --timeout 20
     ```
  2. **Modular Subsystem Scoping (Recommended over Monolith):** Rather than scanning the entire repository in one unconstrained execution, scan focused architectural domains:
     ```bash
     # Screen capture & vision gating
     ocr scan --path src-tauri/src/capture,core/capture --no-plan --concurrency 8
     # OCR & Neural inference
     ocr scan --path src-tauri/src/ocr,core/ocr --no-plan --concurrency 8
     # Subtitle overlay & Tauri IPC
     ocr scan --path src-tauri/src/overlay,src-tauri/src/lib.rs --no-plan --concurrency 8
     # Frontend Webview presentation
     ocr scan --path src --no-plan --concurrency 8
     ```
  3. **Pre-Flight Verification:** Always execute `ocr scan --preview <flags>` first to ensure the reviewed file count is within bounded, reasonable limits (< 30 code files per run) before dispatching LLM subtasks.
  4. **Session Resumption & Logging:** In the event of network disruption, leverage `--resume <session-id>` to continue without discarding completed work.

### 7. Execution & Timeout Vigilance
- **Harness Shell Timeout Vigilance:** The default harness shell timeout (120s / 2 minutes) is strictly inadequate for heavy tasks, reasoning models (Gemini Pro, Claude Sonnet/Opus), or large builds.
  - When invoking `ocr review`, builds, or test suites, **explicitly pass `timeout: 300000` to `600000` (5–10 minutes)**. Never let default 120s cutoff waste tokens or interrupt reasoning mid-stream.
  - For `ocr review`, pass `--effort low` and `--exclude 'tests/*,src-tauri/icons/*,README.md'` to prevent unbounded roundtrips while keeping token usage bounded.
- **Stay on the branch:** Never auto-merge PRs immediately without presenting the verification scorecard and receiving explicit user approval.
