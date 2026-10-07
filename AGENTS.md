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

### 5. Local Development Toolchain (Bun for JS/TS on macOS)
- When executing JavaScript/TypeScript tasks locally on macOS (running scripts, building Vite bundles, type-checking, package management), **strictly prefer `bun`** (`bun run check`, `bun run build`, `bun test`, `bun install`) instead of npm/node for sub-second execution speeds.
- In automated CI workflows (`.github/workflows/`), maintain standard `npm` compatibility for deterministic cross-platform parity across macOS and Windows runners.

---

## Part 3: UI & Craftsmanship Filter (Anti-Slop)

Whenever building or refining the UI (PyQt6 Overlay, Settings, Dialogs):
- **Purpose over decoration:** No random glows, generic pill badges, or template fluff without a clear functional reason.
- **High contrast & readability:** Subtitle overlays must maintain WCAG AA contrast (crisp text stroke/drop shadow, legible over light and dark media).
- **Resilience:** All states must be handled (empty text, loading model, capture pause, error states).
- **Keyboard accessible:** Every dialog and settings window must be navigable via keyboard (`Tab`, `Enter`, `Escape`).
- **Functional completeness:** No dead buttons, non-functional sliders, or dummy UI elements.

---

## Part 4: Code Review Scientific Verification Protocol & Git Merge Discipline

When conducting AI Code Reviews (via `ocr review`, dual LLM evaluations, or manual diff inspection) and managing git branches, the agent **MUST NOT ACCEPT REVIEWER FINDINGS AT FACE VALUE OR ACT AS A SYCOPHANT TO REVIEW BOTS**, and must strictly obey git authorization invariants:

### 1. Strict Git Invariant: FORBIDDEN AUTO-COMMIT / AUTO-PUSH / AUTO-MERGE
- **Strict User Authorization Gate:** The agent is **STRICTLY FORBIDDEN** from running `git commit`, `git push`, creating tags, or merging branches autonomously without an **explicit instruction** from the user ("commit now", "push now", "ok commit", "merge", etc.).
- **Mandatory Pull Request Lifecycle (No Naked Merges into `main`):**
  - Every non-trivial feature, refactor, or bugfix **MUST** transition through a formal GitHub Pull Request (`gh pr create`) before being merged into `main`. Direct or naked branch merges into `main` without an associated PR are strictly forbidden, even on personal projects.
  - **Standard Engineering Lifecycle:**
    1. **Branch & Implement:** Develop on an isolated branch (`feat/<name>-#<id>`, `fix/<name>-#<id>`).
    2. **Local Verification:** Run test suites (`./.venv/bin/pytest`).
    3. **Push & Open PR:** Push the feature branch and open a PR via `gh pr create` linking the relevant issue (`Closes #<id>`).
    4. **AI Code Review on PR:** Execute `ocr review --audience agent --from main --to <branch>` to review the PR diff cleanly.
    5. **Dialectical Verification & Scorecard:** Present findings to the user (Confirmed Bugs vs False Positives). Apply verified fixes surgically.
    6. **User Authorization Gate:** Present the clean PR status and await explicit user instruction to merge.
    7. **Merge:** Merge via `gh pr merge --merge` (or `--delete-branch`) only after explicit user approval.
- **Report Status First:** Upon task completion, present a concise summary of changes, test suite results, and linter status, and await user instruction. Inquiring for confirmation ("Would you like to commit / merge?") is permitted, but executing commit/push/merge without explicit confirmation is prohibited.
- **Living Architecture Specification Synchronization:** Whenever system architecture, engine dependencies, tuning parameters, or core operational workflows are committed or merged into `main`, `docs/TECHNICAL_STACK_AND_PIPELINES.md` **MUST BE SYNCHRONIZED** so the documentation remains an accurate reference for continuous study and architectural truth.
- **Strict English Consistency Across Repository Artefacts:** All documentation files (`*.md`), technical specifications, GitHub Issues, Pull Request descriptions, Git commit messages, and GitHub Release notes **MUST BE WRITTEN EXCLUSIVELY IN CLEAR, CONCISE ENGLISH**. Maintain strict language consistency across all repository artefacts for international open-source parity.

### 2. Mandatory User Presentation Before Applying Changes
- The agent is **STRICTLY FORBIDDEN** from unilaterally modifying code, committing, or merging fixes immediately after receiving automated review comments without first presenting the findings dialectically to the user.
- Present a structured scorecard: categorize items into **Hard Blockers / Confirmed Bugs** vs **False Positives / Rejected Claims** vs **Architectural Optimizations**, complete with reproduction proof.

### 3. Step 1: Problem Validity Verification (Is this a genuine defect or a hallucination/misunderstanding?)
- **Never Assume Validity:** Treat reviewer comments with healthy skepticism. LLM reviewers frequently misread token-truncated code, misunderstand project conventions, or flag stylistic non-issues as critical bugs.
- **Define the Concrete Failure Scenario:** *"Under what exact inputs, window bounds, display coordinates, or concurrency state does this failure occur, and what is the exact stack trace or measurable impact?"*
- **Execute an Empirical Reproduction Script:** Run a minimal terminal script, synthetic frame injection, or test assertion (`./.venv/bin/pytest`) to test the failure hypothesis.
- **Classification:**
  - If reproduction confirms an actual error, crash, memory leak, or measurable accuracy degradation: classify as **CONFIRMED REAL ISSUE** with log/terminal evidence.
  - If reproduction passes cleanly, or the claim is based on truncated files, obsolete syntax, or false assumptions: reject the finding dialectically with proof as **FALSE POSITIVE / REJECTED**. Do not modify code for rejected items.

### 4. Step 2: Solution Validity & Orthogonality Verification
- **Never Blindly Apply Suggested Diff:** Review bot fix suggestions are often naive, incomplete, or break neighboring invariants. Critically evaluate whether the suggested fix genuinely addresses the root cause or just silences a linter.
- **Surgical Implementation:** Apply the verified solution with minimal footprint.
- **Dual Verification:**
  1. Re-run the reproduction script from Step 1 to verify the defect is genuinely eliminated.
  2. Run full test suites (`./.venv/bin/pytest`) to verify zero regressions across neighboring systems (orthogonality).

### 5. Reporting Format to User
Always report findings structured clearly into distinct sections before asking for merge/commit permission:
1. `### 1. Temuan False Positive / Ditolak (Hallucinated Findings)` (with reproduction proof of why it's rejected).
2. `### 2. Temuan Nyata & Sudah Diperbaiki Secara Bedah (Confirmed Real Issues & Fixed)` (with scenario, reproduction proof, and surgical fix).
3. `### 3. Verifikasi Pasca-Perbaikan (Orthogonality Check)` (with test pass status).

### 6. Execution & Timeout Vigilance
- **Harness Shell Timeout Vigilance:** When invoking `ocr review`, test suites, or benchmarks, **explicitly pass `timeout: 300000` to `600000` (5–10 minutes)**. Never let default 120s cutoff waste tokens or interrupt reasoning mid-stream.
- **Stay on the branch:** Never auto-merge PRs immediately without presenting the verification scorecard and receiving explicit user approval.

