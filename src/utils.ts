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
 * Trims extraneous whitespace while preserving intentional newline breaks.
 */
export function sanitizeSubtitleText(text: string): string {
  if (!text) return "";
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .join("\n");
}
