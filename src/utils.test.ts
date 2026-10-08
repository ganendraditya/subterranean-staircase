import { describe, expect, it } from "vitest";
import {
  clampNumber,
  formatLanguagePairLabel,
  generateOverlayCssTokens,
  isHexColor,
  sanitizeSubtitleText,
} from "./utils";

describe("formatLanguagePairLabel", () => {
  it("formats standard language codes with arrow", () => {
    expect(formatLanguagePairLabel("ja", "en")).toBe("JA → EN");
    expect(formatLanguagePairLabel("auto", "id")).toBe("Auto → ID");
    expect(formatLanguagePairLabel("zh", "ko")).toBe("ZH → KO");
  });

  it("handles empty or default values gracefully", () => {
    expect(formatLanguagePairLabel()).toBe("Auto → EN");
    expect(formatLanguagePairLabel("", "")).toBe("Auto → EN");
  });

  it("falls back to uppercase for unknown language codes", () => {
    expect(formatLanguagePairLabel("es", "de")).toBe("ES → DE");
  });
});

describe("clampNumber", () => {
  it("preserves numbers within range", () => {
    expect(clampNumber(24, 16, 38, 24)).toBe(24);
    expect(clampNumber("30", 16, 38, 24)).toBe(30);
  });

  it("clamps numbers exceeding max or below min", () => {
    expect(clampNumber(50, 16, 38, 24)).toBe(38);
    expect(clampNumber(10, 16, 38, 24)).toBe(16);
    expect(clampNumber("-5", 1, 4, 2)).toBe(1);
  });

  it("returns fallback on NaN, null, or undefined", () => {
    expect(clampNumber("abc", 16, 38, 24)).toBe(24);
    expect(clampNumber("", 16, 38, 24)).toBe(24);
    expect(clampNumber("   ", 16, 38, 24)).toBe(24);
    expect(clampNumber(null, 16, 38, 24)).toBe(24);
    expect(clampNumber(undefined, 16, 38, 24)).toBe(24);
    expect(clampNumber(NaN, 16, 38, 24)).toBe(24);
  });
});

describe("isHexColor", () => {
  it("recognizes valid hex color formats", () => {
    expect(isHexColor("#fff")).toBe(true);
    expect(isHexColor("#FFFFFF")).toBe(true);
    expect(isHexColor("#38bdf8")).toBe(true);
    expect(isHexColor("#000000ee")).toBe(true);
  });

  it("rejects invalid color strings", () => {
    expect(isHexColor("red")).toBe(false);
    expect(isHexColor("rgb(0,0,0)")).toBe(false);
    expect(isHexColor("#xyz")).toBe(false);
    expect(isHexColor("")).toBe(false);
  });
});

describe("generateOverlayCssTokens", () => {
  it("maps overlay style attributes to CSS custom properties", () => {
    const tokens = generateOverlayCssTokens({
      font_size: 28,
      text_color: "#ffffff",
      stroke_color: "#000000",
      stroke_width: 3,
    });

    expect(tokens["--overlay-font-size"]).toBe("28px");
    expect(tokens["--overlay-text-color"]).toBe("#ffffff");
    expect(tokens["--overlay-stroke-color"]).toBe("#000000");
    expect(tokens["--overlay-stroke-width"]).toBe("3px");
  });
});

describe("sanitizeSubtitleText", () => {
  it("trims whitespace while preserving linebreaks", () => {
    const input = "  Hello, world!  \n  This is a subtitle.  ";
    expect(sanitizeSubtitleText(input)).toBe("Hello, world!\nThis is a subtitle.");
  });

  it("trims external whitespace while preserving intentional paragraph breaks", () => {
    const input = "  Line 1  \n\n  Line 2  ";
    expect(sanitizeSubtitleText(input)).toBe("Line 1\n\nLine 2");
  });

  it("returns empty string on empty input", () => {
    expect(sanitizeSubtitleText("")).toBe("");
  });
});
