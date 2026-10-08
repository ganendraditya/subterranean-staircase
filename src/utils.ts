export interface OverlayStyle {
  font_size: number;
  text_color: string;
  stroke_color: string;
  stroke_width: number;
}

const LANGUAGE_CODE_MAP: Record<string, string> = {
  auto: "Auto",
  ja: "JA",
  zh: "ZH",
  ko: "KO",
  en: "EN",
  id: "ID",
};

/**
 * Format source and target language codes into human-readable uppercase arrows (e.g. "JA → EN").
 */
export function formatLanguagePairLabel(source = "auto", target = "en"): string {
  const s = (source || "auto").toLowerCase();
  const t = (target || "en").toLowerCase();
  const srcLabel = LANGUAGE_CODE_MAP[s] ?? s.toUpperCase();
  const tgtLabel = LANGUAGE_CODE_MAP[t] ?? t.toUpperCase();
  return `${srcLabel} → ${tgtLabel}`;
}

/**
 * Validates and clamps a number between min and max bounds, falling back safely if NaN/invalid.
 */
export function clampNumber(
  value: number | string | null | undefined,
  min: number,
  max: number,
  fallback: number
): number {
  if (value === null || value === undefined) return fallback;
  if (typeof value === "string" && value.trim() === "") return fallback;
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) return fallback;
  return Math.min(Math.max(num, min), max);
}

/**
 * Validates whether a string is a valid 3, 6, or 8 digit hex color code.
 */
export function isHexColor(color: string): boolean {
  if (!color || typeof color !== "string") return false;
  return /^#([A-Fa-f0-9]{3}|[A-Fa-f0-9]{6}|[A-Fa-f0-9]{8})$/.test(color.trim());
}

/**
 * Generates CSS custom properties dictionary from OverlayStyle.
 */
export function generateOverlayCssTokens(style: OverlayStyle): Record<string, string> {
  return {
    "--overlay-font-size": `${style.font_size}px`,
    "--overlay-text-color": style.text_color,
    "--overlay-stroke-color": style.stroke_color,
    "--overlay-stroke-width": `${style.stroke_width}px`,
  };
}

/**
 * Trims extraneous line whitespace while preserving intentional newline breaks.
 */
export function sanitizeSubtitleText(text: string): string {
  if (!text) return "";
  const lines = text.split("\n").map((line) => line.trim());
  while (lines.length > 0 && lines[0] === "") {
    lines.shift();
  }
  while (lines.length > 0 && lines[lines.length - 1] === "") {
    lines.pop();
  }
  return lines.join("\n");
}

export interface ParsedCaptureTarget {
  kind: "screen" | "window";
  id: number;
}

/**
 * Parses composite select option values like "window:1234" or "screen:0".
 */
export function parseCaptureTargetValue(val: string): ParsedCaptureTarget {
  if (!val || typeof val !== "string") {
    return { kind: "screen", id: 0 };
  }
  const parts = val.split(":");
  if (parts.length < 2) {
    return { kind: "screen", id: 0 };
  }
  const kind = parts[0];
  const id = parseInt(parts[1], 10);
  if (kind === "window" && Number.isFinite(id) && id >= 0) {
    return { kind: "window", id };
  }
  return { kind: "screen", id: Number.isFinite(id) ? id : 0 };
}

/**
 * Formats delta and gating status for visual telemetry display.
 */
export function formatDiffStatus(hasChanged: boolean, deltaPercent: number): {
  label: string;
  badgeClass: string;
} {
  if (hasChanged) {
    return {
      label: `ACTIVE (${deltaPercent.toFixed(1)}% delta)`,
      badgeClass: "badge-unlocked",
    };
  }
  return {
    label: `STATIC (${deltaPercent.toFixed(1)}% - Gated)`,
    badgeClass: "badge-locked",
  };
}

/**
 * Formats translation cache count into descriptive badge string.
 */
export function formatCacheCountLabel(count: number): string {
  const safeCount = Math.max(0, Math.floor(count || 0));
  return `${safeCount} cached dialogue line${safeCount === 1 ? "" : "s"}`;
}

/**
 * Formats translation latency and cache source indicator.
 */
export function formatTranslationMetric(latencyMs: number, fromCache: boolean): string {
  if (fromCache) {
    return "< 0.1 ms (SQLite Cache Hit)";
  }
  return `${latencyMs.toFixed(1)} ms (Cloud LLM Network)`;
}
