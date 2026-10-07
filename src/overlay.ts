import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { generateOverlayCssTokens, OverlayStyle, sanitizeSubtitleText } from "./utils";

export interface SubtitlePayload {
  text: string;
  duration_ms?: number;
}

window.addEventListener("DOMContentLoaded", async () => {
  const container = document.getElementById("overlay-container");
  const subtitleText = document.getElementById("subtitle-text");
  const repositionBadge = document.getElementById("reposition-badge");
  const appWindow = getCurrentWindow();

  let fadeTimeout: number | null = null;
  let clearTextTimeout: number | null = null;
  let isInteractive = false;

  function clearFadeTimers() {
    if (fadeTimeout !== null) {
      window.clearTimeout(fadeTimeout);
      fadeTimeout = null;
    }
    if (clearTextTimeout !== null) {
      window.clearTimeout(clearTextTimeout);
      clearTextTimeout = null;
    }
  }

  function setSubtitle(rawText: string, durationMs = 4000) {
    if (!subtitleText) return;
    clearFadeTimers();

    const text = sanitizeSubtitleText(rawText);
    subtitleText.textContent = text;
    subtitleText.classList.remove("faded");

    if (durationMs > 0) {
      fadeTimeout = window.setTimeout(() => {
        subtitleText.classList.add("faded");
        clearTextTimeout = window.setTimeout(() => {
          if (subtitleText.classList.contains("faded")) {
            subtitleText.textContent = "";
          }
          clearTextTimeout = null;
        }, 250);
      }, durationMs);
    }
  }

  function clearSubtitle() {
    clearFadeTimers();
    if (subtitleText) {
      subtitleText.textContent = "";
      subtitleText.classList.remove("faded");
    }
  }

  function setInteractive(interactive: boolean) {
    isInteractive = interactive;
    if (container) {
      if (interactive) {
        container.classList.add("interactive");
        repositionBadge?.classList.remove("hidden");
      } else {
        container.classList.remove("interactive");
        repositionBadge?.classList.add("hidden");
      }
    }
  }

  function applyStyle(style: OverlayStyle) {
    const root = document.documentElement;
    const tokens = generateOverlayCssTokens(style);
    for (const [key, val] of Object.entries(tokens)) {
      root.style.setProperty(key, val);
    }
  }

  // Native window drag handler in interactive repositioning mode
  if (container) {
    container.addEventListener("mousedown", async (e) => {
      if (isInteractive && e.button === 0) {
        try {
          await appWindow.startDragging();
        } catch (err) {
          console.error("Failed to initiate native window drag:", err);
        }
      }
    });
  }

  // Subscribe to Tauri IPC events in parallel
  try {
    await Promise.all([
      listen<SubtitlePayload>("subtitle_update", (event) => {
        setSubtitle(event.payload.text, event.payload.duration_ms ?? 4000);
      }),
      listen("subtitle_clear", () => {
        clearSubtitle();
      }),
      listen<boolean>("overlay_interactive_changed", (event) => {
        setInteractive(event.payload);
      }),
      listen<OverlayStyle>("overlay_style_changed", (event) => {
        applyStyle(event.payload);
      }),
    ]);
  } catch (err) {
    console.error("Failed to attach Tauri event listeners to overlay:", err);
  }
});
