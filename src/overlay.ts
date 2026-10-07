import { listen } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";

export interface SubtitlePayload {
  text: string;
  duration_ms?: number;
}

export interface OverlayStyle {
  font_size: number;
  text_color: string;
  stroke_color: string;
  stroke_width: number;
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

  function setSubtitle(text: string, durationMs = 4000) {
    if (!subtitleText) return;
    clearFadeTimers();

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
    if (style.font_size !== undefined) {
      root.style.setProperty("--overlay-font-size", `${style.font_size}px`);
    }
    if (style.text_color) {
      root.style.setProperty("--overlay-text-color", style.text_color);
    }
    if (style.stroke_color) {
      root.style.setProperty("--overlay-stroke-color", style.stroke_color);
    }
    if (style.stroke_width !== undefined) {
      root.style.setProperty("--overlay-stroke-width", `${style.stroke_width}px`);
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
