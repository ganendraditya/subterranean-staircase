import { invoke } from "@tauri-apps/api/core";
import {
  clampNumber,
  formatCacheCountLabel,
  formatDiffStatus,
  formatLanguagePairLabel,
  formatOcrMetric,
  formatOcrStatusBadge,
  formatTranslationMetric,
  OcrResultPayload,
  OcrStatusPayload,
  OverlayStyle,
  parseCaptureTargetValue,
} from "./utils";

export interface SystemInfo {
  app_name: string;
  version: string;
  architecture: string;
  status: string;
}

export interface OverlayState {
  is_visible: boolean;
  is_interactive: boolean;
  style: OverlayStyle;
}

export interface MonitorTargetInfo {
  id: number;
  name: string;
  width: number;
  height: number;
  scale_factor: number;
  is_primary: boolean;
}

export interface WindowTargetInfo {
  id: number;
  title: string;
  app_name: string;
  width: number;
  height: number;
  is_minimized: boolean;
}

export interface CaptureTargets {
  monitors: MonitorTargetInfo[];
  windows: WindowTargetInfo[];
}

export interface DiffResult {
  has_changed: boolean;
  delta: number;
  delta_percent: number;
  threshold: number;
  latency_ms: number;
}

export interface PreviewTickResult {
  preview_data_url: string;
  diff: DiffResult;
}

export interface LlmConfig {
  base_url: string;
  model_name: string;
  api_key?: string | null;
  timeout_seconds?: number | null;
}

export interface TranslationRequest {
  source_text: string;
  source_lang: string;
  target_lang: string;
}

export interface TranslationResponse {
  source_text: string;
  translated_text: string;
  source_lang: string;
  target_lang: string;
  from_cache: boolean;
  latency_ms: number;
}

const PING_PAYLOAD = "Hello from Vite Frontend!";
const MAX_LOG_LINES = 200;

window.addEventListener("DOMContentLoaded", async () => {
  // DOM Elements - Status & Header
  const lblStatus = document.getElementById("lbl-status");
  const lblArch = document.getElementById("lbl-arch");
  const versionTag = document.getElementById("version-tag");
  const valEngine = document.getElementById("val-engine");
  const valLangPair = document.getElementById("val-lang-pair");
  const valInputMode = document.getElementById("val-input-mode");

  // DOM Elements - Console
  const btnPing = document.getElementById("btn-ping");
  const btnClearLog = document.getElementById("btn-clear-log");
  const consoleOutput = document.getElementById("console-output");

  // DOM Elements - Tabs
  const tabButtons = document.querySelectorAll<HTMLButtonElement>(".tab-btn");
  const tabPanes = document.querySelectorAll<HTMLElement>(".tab-pane");

  // DOM Elements - Screen Capture & Preview
  const selectCaptureTarget = document.getElementById("select-capture-target") as HTMLSelectElement | null;
  const btnRefreshTargets = document.getElementById("btn-refresh-targets");
  const btnTogglePreview = document.getElementById("btn-toggle-preview");
  const imgPreview = document.getElementById("img-preview") as HTMLImageElement | null;
  const previewPlaceholder = document.getElementById("preview-placeholder");
  const previewTag = document.getElementById("preview-tag");
  const badgeGateStatus = document.getElementById("badge-gate-status");
  const valDiffDelta = document.getElementById("val-diff-delta");
  const valDiffThresh = document.getElementById("val-diff-thresh");
  const valDiffLatency = document.getElementById("val-diff-latency");
  const valCaptureRes = document.getElementById("val-capture-res");

  // DOM Elements - Subtitle Test Harness
  const customSubtitleInput = document.getElementById("custom-subtitle-input") as HTMLInputElement | null;
  const btnSendCustom = document.getElementById("btn-send-custom");
  const btnPresetShort = document.getElementById("btn-preset-short");
  const btnPresetMulti = document.getElementById("btn-preset-multi");
  const btnPresetJp = document.getElementById("btn-preset-jp");
  const btnClearOverlay = document.getElementById("btn-clear-overlay");
  const btnToggleOverlayVis = document.getElementById("btn-toggle-overlay-vis");

  // DOM Elements - Neural OCR Pipeline
  const badgeOcrStatus = document.getElementById("badge-ocr-status");
  const btnTriggerOcr = document.getElementById("btn-trigger-ocr");
  const btnOcrToTrans = document.getElementById("btn-ocr-to-trans");
  const boxOcrResult = document.getElementById("box-ocr-result");

  // DOM Elements - Overlay Settings
  const btnToggleInteractive = document.getElementById("btn-toggle-interactive");
  const badgeInteractiveStatus = document.getElementById("badge-interactive-status");
  const btnResetPos = document.getElementById("btn-reset-pos");
  const sliderFontSize = document.getElementById("slider-font-size") as HTMLInputElement | null;
  const lblFontSizeVal = document.getElementById("lbl-font-size-val");
  const sliderStrokeWidth = document.getElementById("slider-stroke-width") as HTMLInputElement | null;
  const lblStrokeVal = document.getElementById("lbl-stroke-val");
  const selectTextColor = document.getElementById("select-text-color") as HTMLSelectElement | null;
  const selectStrokeColor = document.getElementById("select-stroke-color") as HTMLSelectElement | null;
  const btnApplyStyle = document.getElementById("btn-apply-style");

  // DOM Elements - Translation Settings
  const selectSourceLang = document.getElementById("select-source-lang") as HTMLSelectElement | null;
  const selectTargetLang = document.getElementById("select-target-lang") as HTMLSelectElement | null;
  const inputLlmUrl = document.getElementById("input-llm-url") as HTMLInputElement | null;
  const inputLlmModel = document.getElementById("input-llm-model") as HTMLInputElement | null;
  const inputLlmKey = document.getElementById("input-llm-key") as HTMLInputElement | null;
  const btnSaveLlm = document.getElementById("btn-save-llm");
  const btnTestLlm = document.getElementById("btn-test-llm");
  const lblLlmTestFeedback = document.getElementById("lbl-llm-test-feedback");

  // DOM Elements - Cache & Translation Test
  const lblCacheCount = document.getElementById("lbl-cache-count");
  const btnRefreshCacheStats = document.getElementById("btn-refresh-cache-stats");
  const btnClearCache = document.getElementById("btn-clear-cache");
  const inputTestTranslate = document.getElementById("input-test-translate") as HTMLInputElement | null;
  const btnRunTranslation = document.getElementById("btn-run-translation");
  const boxTransResult = document.getElementById("box-trans-result");

  // Local State
  let overlayVisible = true;
  let overlayInteractive = false;
  let previewActive = false;
  let previewInterval: number | null = null;

  function log(msg: string) {
    if (!consoleOutput) return;
    const ts = new Date().toLocaleTimeString();
    const line = `[${ts}] ${msg}\n`;
    const existing = consoleOutput.textContent || "";
    const lines = existing.split("\n");
    const visibleLines = lines[lines.length - 1] === "" ? lines.length - 1 : lines.length;
    if (visibleLines > MAX_LOG_LINES) {
      consoleOutput.textContent = lines.slice(lines.length - MAX_LOG_LINES).join("\n");
    }
    consoleOutput.textContent += line;
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  }

  // 1. Tab Navigation with Accessibility ARIA
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTabId = btn.getAttribute("data-tab");
      if (!targetTabId) return;

      tabButtons.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      tabPanes.forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      const targetPane = document.getElementById(targetTabId);
      if (targetPane) {
        targetPane.classList.add("active");
      }
    });
  });

  // 2. Initial Handshake with Rust Core
  log("Control Center initialized. Establishing IPC bridge...");

  try {
    const info = await invoke<SystemInfo>("get_system_info");
    if (lblStatus) lblStatus.textContent = info.status;
    if (lblArch) lblArch.textContent = info.architecture;
    if (versionTag) versionTag.textContent = `v${info.version}`;
    log(`Connected to Rust core: ${info.app_name} (${info.version}) on ${info.architecture}`);
  } catch (err) {
    if (lblStatus) lblStatus.textContent = "Standby (Web Mode)";
    log(`IPC handshake note: ${String(err)}`);
  }

  // Query Initial Overlay State
  try {
    const state = await invoke<OverlayState>("get_overlay_state");
    overlayVisible = state.is_visible;
    overlayInteractive = state.is_interactive;
    updateInteractiveUI(overlayInteractive);
    updateOverlayVisibilityUI(overlayVisible);

    if (sliderFontSize && lblFontSizeVal) {
      sliderFontSize.value = String(state.style.font_size);
      lblFontSizeVal.textContent = `${state.style.font_size}px`;
    }
    if (sliderStrokeWidth && lblStrokeVal) {
      sliderStrokeWidth.value = String(state.style.stroke_width);
      lblStrokeVal.textContent = `${state.style.stroke_width}px`;
    }
    if (selectTextColor && state.style.text_color) {
      selectTextColor.value = state.style.text_color;
    }
    if (selectStrokeColor && state.style.stroke_color) {
      selectStrokeColor.value = state.style.stroke_color;
    }
  } catch (err) {
    log(`Overlay state query: ${String(err)}`);
  }

  // 3. Screen Capture & Live Vision Gating
  async function loadCaptureTargets() {
    if (!selectCaptureTarget) return;
    try {
      const targets = await invoke<CaptureTargets>("get_capture_targets");
      const currentVal = selectCaptureTarget.value;
      selectCaptureTarget.replaceChildren();

      // Add Displays
      targets.monitors.forEach((m) => {
        const opt = document.createElement("option");
        opt.value = `screen:${m.id}`;
        opt.textContent = `${m.name} (${m.width}×${m.height}${m.is_primary ? " - Primary" : ""})`;
        selectCaptureTarget.appendChild(opt);
      });

      // Add Application Windows
      if (targets.windows.length > 0) {
        const group = document.createElement("optgroup");
        group.label = "Active Application Windows";
        targets.windows.forEach((w) => {
          const opt = document.createElement("option");
          opt.value = `window:${w.id}`;
          const title = w.title.length > 36 ? `${w.title.slice(0, 33)}...` : w.title;
          opt.textContent = `${w.app_name}: ${title}`;
          group.appendChild(opt);
        });
        selectCaptureTarget.appendChild(group);
      }

      if (currentVal && Array.from(selectCaptureTarget.options).some((o) => o.value === currentVal)) {
        selectCaptureTarget.value = currentVal;
      }

      if (valCaptureRes && selectCaptureTarget.selectedOptions[0]) {
        valCaptureRes.textContent = selectCaptureTarget.selectedOptions[0].text;
      }

      log(`Enumerated ${targets.monitors.length} display(s) and ${targets.windows.length} window(s).`);
    } catch (err) {
      log(`Error enumerating capture targets: ${String(err)}`);
    }
  }

  await loadCaptureTargets();

  if (btnRefreshTargets) {
    btnRefreshTargets.addEventListener("click", () => {
      loadCaptureTargets();
    });
  }

  selectCaptureTarget?.addEventListener("change", () => {
    if (valCaptureRes && selectCaptureTarget.selectedOptions[0]) {
      valCaptureRes.textContent = selectCaptureTarget.selectedOptions[0].text;
    }
    if (previewActive) {
      tickPreview();
    }
  });

  let isTicking = false;
  async function tickPreview() {
    if (!previewActive || isTicking) return;
    isTicking = true;
    const targetVal = selectCaptureTarget?.value || "screen:0";
    const parsed = parseCaptureTargetValue(targetVal);

    const winId = parsed.kind === "window" ? parsed.id : null;
    const monId = parsed.kind === "screen" ? parsed.id : null;

    try {
      const res = await invoke<PreviewTickResult>("capture_preview_and_diff", {
        window_id: winId,
        monitor_id: monId,
        roi: null,
        threshold: 0.015,
      });

      if (imgPreview) {
        imgPreview.src = res.preview_data_url;
      }

      const diff = res.diff;
      if (valDiffDelta) valDiffDelta.textContent = `${diff.delta_percent.toFixed(2)}%`;
      if (valDiffThresh) valDiffThresh.textContent = `${(diff.threshold * 100).toFixed(1)}%`;
      if (valDiffLatency) valDiffLatency.textContent = `${diff.latency_ms.toFixed(3)} ms`;

      if (badgeGateStatus) {
        const status = formatDiffStatus(diff.has_changed, diff.delta_percent);
        badgeGateStatus.textContent = status.label;
        badgeGateStatus.className = `settings-card-badge ${status.badgeClass}`;
      }
    } catch (err) {
      console.warn("Standby preview tick failed:", err);
    } finally {
      isTicking = false;
    }
  }

  function startPreview() {
    previewActive = true;
    if (previewPlaceholder) previewPlaceholder.classList.add("hidden");
    if (imgPreview) imgPreview.classList.remove("hidden");
    if (previewTag) previewTag.classList.remove("hidden");
    if (btnTogglePreview) btnTogglePreview.textContent = "Pause Live Preview";

    tickPreview();
    previewInterval = window.setInterval(tickPreview, 200); // 5 FPS
    log("Started live screen preview (5 FPS) & SIMD vision gating.");
  }

  function stopPreview() {
    previewActive = false;
    if (previewInterval !== null) {
      window.clearInterval(previewInterval);
      previewInterval = null;
    }
    if (previewPlaceholder) previewPlaceholder.classList.remove("hidden");
    if (imgPreview) imgPreview.classList.add("hidden");
    if (previewTag) previewTag.classList.add("hidden");
    if (btnTogglePreview) btnTogglePreview.textContent = "Start Live Preview (5 FPS)";
    log("Paused live screen preview.");
  }

  if (btnTogglePreview) {
    btnTogglePreview.addEventListener("click", () => {
      if (previewActive) {
        stopPreview();
      } else {
        startPreview();
      }
    });
  }

  // 3.5 Neural OCR Pipeline
  let lastOcrText = "";

  async function refreshOcrStatus() {
    try {
      const status = await invoke<OcrStatusPayload>("get_ocr_status");
      if (badgeOcrStatus) {
        const badgeInfo = formatOcrStatusBadge(status);
        badgeOcrStatus.textContent = badgeInfo.label;
        badgeOcrStatus.className = `settings-card-badge ${badgeInfo.badgeClass}`;
      }
      log(`OCR Engine Status: ready=${status.is_ready}, det=${status.det_model_present}, rec=${status.rec_model_present}`);
    } catch (err) {
      log(`Error querying OCR status: ${String(err)}`);
    }
  }

  void refreshOcrStatus();

  if (btnTriggerOcr) {
    btnTriggerOcr.addEventListener("click", async () => {
      btnTriggerOcr.setAttribute("disabled", "true");
      lastOcrText = "";
      if (btnOcrToTrans) {
        btnOcrToTrans.setAttribute("disabled", "true");
      }
      if (boxOcrResult) {
        boxOcrResult.textContent = "Running neural OCR inference (DBNet + SVTR)...";
        boxOcrResult.classList.remove("hidden");
      }

      try {
        const targetVal = selectCaptureTarget?.value || "screen:0";
        const parsed = parseCaptureTargetValue(targetVal);
        const winId = parsed.kind === "window" ? parsed.id : null;
        const monId = parsed.kind === "screen" ? parsed.id : null;

        const res = await invoke<OcrResultPayload>("run_ocr_on_frame", {
          image_base64: null,
          window_id: winId,
          monitor_id: monId,
          roi: null,
        });

        lastOcrText = res.consolidated_text;
        const metric = formatOcrMetric(res.latency_ms, res.detections.length);
        const report = `[OCR ${metric} | ${res.debounce_status}]\n"${res.consolidated_text || "(No subtitle text detected)"}"`;

        if (boxOcrResult) {
          boxOcrResult.textContent = report;
        }
        log(`OCR Output: ${report.replace(/\n/g, " ")}`);

        if (btnOcrToTrans) {
          if (res.consolidated_text) {
            btnOcrToTrans.removeAttribute("disabled");
          } else {
            btnOcrToTrans.setAttribute("disabled", "true");
          }
        }
      } catch (err) {
        lastOcrText = "";
        if (btnOcrToTrans) {
          btnOcrToTrans.setAttribute("disabled", "true");
        }
        if (boxOcrResult) {
          boxOcrResult.textContent = `OCR Error: ${String(err)}`;
        }
        log(`OCR Error: ${String(err)}`);
      } finally {
        btnTriggerOcr.removeAttribute("disabled");
      }
    });
  }

  if (btnOcrToTrans) {
    btnOcrToTrans.addEventListener("click", () => {
      if (!lastOcrText) return;
      if (inputTestTranslate) {
        inputTestTranslate.value = lastOcrText;
      }
      tabButtons.forEach((b) => {
        if (b.getAttribute("data-tab") === "tab-translation") {
          b.click();
        }
      });
      log(`Transferred OCR text to Translation Harness: "${lastOcrText}"`);
    });
  }

  // 4. Subtitle Emitter Functions
  async function sendSubtitle(text: string, durationMs = 4500) {
    try {
      await invoke("emit_subtitle", { text, duration_ms: durationMs });
      log(`Emitted subtitle to overlay: "${text.replace(/\n/g, " ")}"`);
    } catch (err) {
      log(`Error emitting subtitle: ${String(err)}`);
    }
  }

  if (btnSendCustom && customSubtitleInput) {
    btnSendCustom.addEventListener("click", () => {
      const text = customSubtitleInput.value.trim();
      if (text) sendSubtitle(text);
    });
  }

  if (btnPresetShort) {
    btnPresetShort.addEventListener("click", () => {
      sendSubtitle("Wait! Is that the subterranean staircase?");
    });
  }

  if (btnPresetMulti) {
    btnPresetMulti.addEventListener("click", () => {
      sendSubtitle("We found the hidden subterranean passage!\nPlease evacuate immediately!");
    });
  }

  if (btnPresetJp) {
    btnPresetJp.addEventListener("click", () => {
      sendSubtitle("地下の階段を発見しました！\nただちに避難してください！");
    });
  }

  if (btnClearOverlay) {
    btnClearOverlay.addEventListener("click", async () => {
      try {
        await invoke("clear_subtitle");
        log("Cleared overlay subtitle canvas.");
      } catch (err) {
        log(`Error clearing subtitle: ${String(err)}`);
      }
    });
  }

  function updateOverlayVisibilityUI(visible: boolean) {
    if (btnToggleOverlayVis) {
      btnToggleOverlayVis.textContent = visible ? "Hide Overlay" : "Show Overlay";
    }
  }

  if (btnToggleOverlayVis) {
    btnToggleOverlayVis.addEventListener("click", async () => {
      const nextVisible = !overlayVisible;
      btnToggleOverlayVis.setAttribute("disabled", "true");
      try {
        await invoke("toggle_overlay_visibility", { visible: nextVisible });
        overlayVisible = nextVisible;
        updateOverlayVisibilityUI(overlayVisible);
        log(`Overlay visibility toggled: ${overlayVisible ? "Visible" : "Hidden"}`);
      } catch (err) {
        log(`Error toggling visibility: ${String(err)}`);
      } finally {
        btnToggleOverlayVis.removeAttribute("disabled");
      }
    });
  }

  // 5. Interactive Repositioning
  function updateInteractiveUI(interactive: boolean) {
    if (btnToggleInteractive) {
      btnToggleInteractive.textContent = interactive ? "Lock Position" : "Unlock for Dragging";
      if (interactive) {
        btnToggleInteractive.classList.remove("btn-primary");
        btnToggleInteractive.classList.add("btn-secondary");
      } else {
        btnToggleInteractive.classList.remove("btn-secondary");
        btnToggleInteractive.classList.add("btn-primary");
      }
    }
    if (badgeInteractiveStatus) {
      if (interactive) {
        badgeInteractiveStatus.textContent = "Unlocked (Draggable)";
        badgeInteractiveStatus.className = "settings-card-badge badge-unlocked";
      } else {
        badgeInteractiveStatus.textContent = "Locked (Click-Through)";
        badgeInteractiveStatus.className = "settings-card-badge badge-locked";
      }
    }
    if (valInputMode) {
      valInputMode.textContent = interactive ? "Draggable" : "Click-Through";
    }
  }

  if (btnToggleInteractive) {
    btnToggleInteractive.addEventListener("click", async () => {
      const nextInteractive = !overlayInteractive;
      btnToggleInteractive.setAttribute("disabled", "true");
      try {
        await invoke("toggle_overlay_interactive", { interactive: nextInteractive });
        overlayInteractive = nextInteractive;
        updateInteractiveUI(overlayInteractive);
        log(`Interactive mode toggled: ${overlayInteractive ? "UNLOCKED (Drag enabled)" : "LOCKED (Passthrough)"}`);
      } catch (err) {
        log(`Error toggling interactive mode: ${String(err)}`);
      } finally {
        btnToggleInteractive.removeAttribute("disabled");
      }
    });
  }

  if (btnResetPos) {
    btnResetPos.addEventListener("click", async () => {
      try {
        await invoke("reset_overlay_position");
        log("Overlay position reset to primary monitor bottom-center.");
      } catch (err) {
        log(`Error resetting position: ${String(err)}`);
      }
    });
  }

  // 6. Typography Settings
  if (sliderFontSize && lblFontSizeVal) {
    sliderFontSize.addEventListener("input", () => {
      lblFontSizeVal.textContent = `${sliderFontSize.value}px`;
    });
  }

  if (sliderStrokeWidth && lblStrokeVal) {
    sliderStrokeWidth.addEventListener("input", () => {
      lblStrokeVal.textContent = `${sliderStrokeWidth.value}px`;
    });
  }

  if (btnApplyStyle) {
    btnApplyStyle.addEventListener("click", async () => {
      const fontSize = clampNumber(sliderFontSize?.value, 16, 38, 24);
      const strokeWidth = clampNumber(sliderStrokeWidth?.value, 1, 4, 2);
      const textColor = selectTextColor?.value || "#ffffff";
      const strokeColor = selectStrokeColor?.value || "#000000";

      const style: OverlayStyle = {
        font_size: fontSize,
        stroke_width: strokeWidth,
        text_color: textColor,
        stroke_color: strokeColor,
      };

      try {
        await invoke("update_overlay_style", { style });
        log(`Applied typography: Font ${fontSize}px, Stroke ${strokeWidth}px, Text ${textColor}`);
      } catch (err) {
        log(`Error updating style: ${String(err)}`);
      }
    });
  }

  // 7. Translation & LLM Settings
  function updateLanguagePairUI() {
    const srcVal = selectSourceLang?.value || "auto";
    const tgtVal = selectTargetLang?.value || "en";
    if (valLangPair) {
      valLangPair.textContent = formatLanguagePairLabel(srcVal, tgtVal);
    }
  }

  selectSourceLang?.addEventListener("change", updateLanguagePairUI);
  selectTargetLang?.addEventListener("change", updateLanguagePairUI);

  // Load authoritative LLM config from Rust persistent storage
  async function loadLlmConfig() {
    try {
      const cfg = await invoke<LlmConfig>("get_llm_config");
      if (inputLlmUrl) inputLlmUrl.value = cfg.base_url;
      if (inputLlmModel) inputLlmModel.value = cfg.model_name;
      if (inputLlmKey) inputLlmKey.value = cfg.api_key || "";
      if (valEngine) valEngine.textContent = cfg.model_name ? "Cloud LLM" : "Local";
      log(`Loaded persistent LLM config: ${cfg.model_name} @ ${cfg.base_url}`);
    } catch (err) {
      log(`Note loading persistent LLM config: ${String(err)}`);
    }
  }

  await loadLlmConfig();

  if (btnSaveLlm) {
    btnSaveLlm.addEventListener("click", async () => {
      const url = inputLlmUrl?.value.trim() || "https://api.groq.com/openai/v1";
      const model = inputLlmModel?.value.trim() || "llama-3.3-70b-versatile";
      const key = inputLlmKey?.value.trim() || "";

      const config: LlmConfig = {
        base_url: url,
        model_name: model,
        api_key: key ? key : null,
        timeout_seconds: 10,
      };

      btnSaveLlm.setAttribute("disabled", "true");
      try {
        await invoke("save_llm_config", { config });
        if (valEngine) valEngine.textContent = model ? "Cloud LLM" : "Local";
        log(`Saved and secured LLM configuration: Model ${model} via ${url}`);
      } catch (err) {
        log(`Error saving LLM config: ${String(err)}`);
      } finally {
        btnSaveLlm.removeAttribute("disabled");
      }
    });
  }

  if (btnTestLlm) {
    btnTestLlm.addEventListener("click", async () => {
      const url = inputLlmUrl?.value.trim() || "https://api.groq.com/openai/v1";
      const model = inputLlmModel?.value.trim() || "llama-3.3-70b-versatile";
      const key = inputLlmKey?.value.trim() || "";

      const config: LlmConfig = {
        base_url: url,
        model_name: model,
        api_key: key ? key : null,
        timeout_seconds: 8,
      };

      if (lblLlmTestFeedback) {
        lblLlmTestFeedback.textContent = "Connecting to API...";
        lblLlmTestFeedback.className = "settings-card-badge";
        lblLlmTestFeedback.classList.remove("hidden");
      }
      btnTestLlm.setAttribute("disabled", "true");

      try {
        const reply = await invoke<string>("test_llm_connection", { config: SomeConfig(config) });
        if (lblLlmTestFeedback) {
          lblLlmTestFeedback.textContent = reply;
          lblLlmTestFeedback.className = "settings-card-badge badge-locked";
        }
        log(`LLM Probe Result: ${reply}`);
      } catch (err) {
        if (lblLlmTestFeedback) {
          lblLlmTestFeedback.textContent = `Failed: ${String(err)}`;
          lblLlmTestFeedback.className = "settings-card-badge badge-unlocked";
        }
        log(`LLM Probe Error: ${String(err)}`);
      } finally {
        btnTestLlm.removeAttribute("disabled");
      }
    });
  }

  function SomeConfig(cfg: LlmConfig): LlmConfig | null {
    return cfg;
  }

  // Cache Statistics & Management
  async function refreshCacheStats() {
    try {
      const count = await invoke<number>("get_cache_stats");
      if (lblCacheCount) {
        lblCacheCount.textContent = formatCacheCountLabel(count);
      }
    } catch (err) {
      console.warn("Failed to query cache stats:", err);
    }
  }

  await refreshCacheStats();

  if (btnRefreshCacheStats) {
    btnRefreshCacheStats.addEventListener("click", () => {
      refreshCacheStats();
    });
  }

  if (btnClearCache) {
    btnClearCache.addEventListener("click", async () => {
      btnClearCache.setAttribute("disabled", "true");
      try {
        await invoke("clear_translation_cache");
        await refreshCacheStats();
        log("Cleared on-device SQLite WAL translation memory.");
      } catch (err) {
        log(`Error clearing translation cache: ${String(err)}`);
      } finally {
        btnClearCache.removeAttribute("disabled");
      }
    });
  }

  // Interactive Live Translation Test Harness
  if (btnRunTranslation && inputTestTranslate) {
    btnRunTranslation.addEventListener("click", async () => {
      const text = inputTestTranslate.value.trim();
      if (!text) return;

      const src = selectSourceLang?.value || "auto";
      const tgt = selectTargetLang?.value || "en";

      const request: TranslationRequest = {
        source_text: text,
        source_lang: src,
        target_lang: tgt,
      };

      btnRunTranslation.setAttribute("disabled", "true");
      if (boxTransResult) {
        boxTransResult.textContent = "Translating sentence...";
        boxTransResult.classList.remove("hidden");
      }

      try {
        const res = await invoke<TranslationResponse>("translate_subtitle", {
          request,
          config: null,
        });

        const metric = formatTranslationMetric(res.latency_ms, res.from_cache);
        const report = `[${formatLanguagePairLabel(res.source_lang, res.target_lang)} | ${metric}]\n"${res.translated_text}"`;
        if (boxTransResult) {
          boxTransResult.textContent = report;
        }
        log(`Translation Output: ${report.replace(/\n/g, " ")}`);

        // Also emit translated line to floating subtitle overlay (non-fatal)
        try {
          await invoke("emit_subtitle", {
            text: res.translated_text,
            duration_ms: 5000,
          });
        } catch (overlayErr) {
          log(`Subtitle overlay notification skipped: ${String(overlayErr)}`);
        }
        await refreshCacheStats();
      } catch (err) {
        if (boxTransResult) {
          boxTransResult.textContent = `Translation Error: ${String(err)}`;
        }
        log(`Translation Error: ${String(err)}`);
      } finally {
        btnRunTranslation.removeAttribute("disabled");
      }
    });
  }

  // Initial sync of language pair
  updateLanguagePairUI();

  // 8. Console Actions
  if (btnClearLog && consoleOutput) {
    btnClearLog.addEventListener("click", () => {
      consoleOutput.textContent = "";
    });
  }

  if (btnPing) {
    btnPing.addEventListener("click", async () => {
      try {
        const reply = await invoke<string>("ping", { message: PING_PAYLOAD });
        log(`Rust Core Reply: ${reply}`);
      } catch (err) {
        log(`Ping error: ${String(err)}`);
      }
    });
  }
});
