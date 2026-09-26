# Guidelines & Standards (Karpathy & Anti-Slop)

This project incorporates engineering discipline and design standards from:
1. **Andrej Karpathy's LLM Guidelines** (`CLAUDE.md` / `AGENTS.md`)
2. **Anti-Slop Framework** (`antislop.md`)

---

## Part 1: Engineering Guidelines (Karpathy)

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

### 3. Surgical Changes
- **Touch only what you must.** Clean up only your own mess.
- Don't "improve" adjacent code, comments, or formatting unnecessarily.
- Don't refactor things that aren't broken.
- Every changed line must trace directly to the goal.

### 4. Goal-Driven Execution
- **Define success criteria. Loop until verified.**
- Transform tasks into verifiable criteria (write test/smoke script, verify, commit).
- Loop independently against tangible feedback before declaring done.

---

## Part 2: Design & UI Filter (Anti-Slop)

Whenever building or refining the UI (PyQt6 Overlay, Settings, Dialogs):
- **Purpose over decoration:** No random glows, generic pill badges, or template fluff without a clear functional reason.
- **High contrast & readability:** Subtitle overlays must maintain WCAG AA contrast (crisp text stroke/drop shadow, legible over light and dark media).
- **Resilience:** All states must be handled (empty text, loading model, capture pause, error states).
- **Keyboard accessible:** Every dialog and settings window must be navigable via keyboard (`Tab`, `Enter`, `Escape`).
- **Functional completeness:** No dead buttons, non-functional sliders, or dummy UI elements.

---

## Quick Reference
- Engineering Rules: Follow Karpathy's 4 Principles for all backend, capture, vision, and core algorithms.
- UI & Interaction: Enforce Anti-Slop craftsmanship on all PyQt6 widgets and user-facing dialogs.
