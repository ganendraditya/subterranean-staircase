import { invoke } from "@tauri-apps/api/core";

export interface SystemInfo {
  app_name: string;
  version: string;
  architecture: string;
  status: string;
}

export interface OverlayStyle {
  font_size: number;
  text_color: string;
  stroke_color: string;
  stroke_width: number;
}

export interface OverlayState {
  is_visible: boolean;
  is_interactive: boolean;
  style: OverlayStyle;
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

  // DOM Elements - Subtitle Test Harness
  const customSubtitleInput = document.getElementById("custom-subtitle-input") as HTMLInputElement | null;
  const btnSendCustom = document.getElementById("btn-send-custom");
  const btnPresetShort = document.getElementById("btn-preset-short");
  const btnPresetMulti = document.getElementById("btn-preset-multi");
  const btnPresetJp = document.getElementById("btn-preset-jp");
  const btnClearOverlay = document.getElementById("btn-clear-overlay");
  const btnToggleOverlayVis = document.getElementById("btn-toggle-overlay-vis");

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

  // Local State
  let overlayVisible = true;
  let overlayInteractive = false;

  function log(msg: string) {
    if (!consoleOutput) return;
    const ts = new Date().toLocaleTimeString();
    const line = `[${ts}] ${msg}\n`;
    const lines = (consoleOutput.textContent || "").split("\n");
    if (lines.length > MAX_LOG_LINES) {
      consoleOutput.textContent = lines.slice(lines.length - MAX_LOG_LINES).join("\n");
    }
    consoleOutput.textContent += line;
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
  }

  // 1. Tab Navigation
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTabId = btn.getAttribute("data-tab");
      if (!targetTabId) return;

      tabButtons.forEach((b) => b.classList.remove("active"));
      tabPanes.forEach((p) => p.classList.remove("active"));

      btn.classList.add("active");
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

    if (sliderFontSize && lblFontSizeVal) {
      sliderFontSize.value = String(state.style.font_size);
      lblFontSizeVal.textContent = `${state.style.font_size}px`;
    }
    if (sliderStrokeWidth && lblStrokeVal) {
      sliderStrokeWidth.value = String(state.style.stroke_width);
      lblStrokeVal.textContent = `${state.style.stroke_width}px`;
    }
  } catch (err) {
    log(`Overlay state query: ${String(err)}`);
  }

  // 3. Subtitle Emitter Functions
  async function sendSubtitle(text: string, durationMs = 4500) {
    try {
      await invoke("emit_subtitle", { text, durationMs });
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

  if (btnToggleOverlayVis) {
    btnToggleOverlayVis.addEventListener("click", async () => {
      try {
        overlayVisible = !overlayVisible;
        await invoke("toggle_overlay_visibility", { visible: overlayVisible });
        log(`Overlay visibility toggled: ${overlayVisible ? "Visible" : "Hidden"}`);
      } catch (err) {
        log(`Error toggling visibility: ${String(err)}`);
      }
    });
  }

  // 4. Interactive Repositioning
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
      try {
        overlayInteractive = !overlayInteractive;
        await invoke("toggle_overlay_interactive", { interactive: overlayInteractive });
        updateInteractiveUI(overlayInteractive);
        log(`Interactive mode toggled: ${overlayInteractive ? "UNLOCKED (Drag enabled)" : "LOCKED (Passthrough)"}`);
      } catch (err) {
        log(`Error toggling interactive mode: ${String(err)}`);
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

  // 5. Typography Settings
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
      const fontSize = parseInt(sliderFontSize?.value || "24", 10);
      const strokeWidth = parseInt(sliderStrokeWidth?.value || "2", 10);
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

  // 6. Translation & LLM Settings
  function updateLanguagePairUI() {
    const src = (selectSourceLang?.value || "auto").toUpperCase();
    const tgt = (selectTargetLang?.value || "en").toUpperCase();
    if (valLangPair) {
      valLangPair.textContent = `${src} → ${tgt}`;
    }
  }

  selectSourceLang?.addEventListener("change", updateLanguagePairUI);
  selectTargetLang?.addEventListener("change", updateLanguagePairUI);

  if (btnSaveLlm) {
    btnSaveLlm.addEventListener("click", () => {
      const url = inputLlmUrl?.value.trim() || "";
      const model = inputLlmModel?.value.trim() || "";
      const key = inputLlmKey?.value.trim() || "";

      try {
        localStorage.setItem("subtrans_llm_url", url);
        localStorage.setItem("subtrans_llm_model", model);
        if (key) localStorage.setItem("subtrans_llm_key", key);
        if (valEngine) valEngine.textContent = model ? "Cloud LLM" : "Local";
        log(`Saved translation config: Model ${model} via ${url}`);
      } catch (err) {
        log(`Error saving LLM config: ${String(err)}`);
      }
    });
  }

  // Load stored LLM settings from localStorage if present
  try {
    const savedUrl = localStorage.getItem("subtrans_llm_url");
    const savedModel = localStorage.getItem("subtrans_llm_model");
    if (savedUrl && inputLlmUrl) inputLlmUrl.value = savedUrl;
    if (savedModel && inputLlmModel) inputLlmModel.value = savedModel;
  } catch {
    // Ignore storage errors
  }

  // 7. Console Actions
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
