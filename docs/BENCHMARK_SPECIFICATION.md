# Heterogeneous Subtitle Benchmark Specification & Evaluation Matrix

## 1. Executive Summary & Objective

To ensure Subterranean Staircase is objectively reliable, accurate, and memory-safe across diverse real-world video content, this specification establishes an empirical, multi-tiered evaluation testbed.

Rather than relying on qualitative spot-checks or uniform single-speaker test clips (e.g. clean YouTube speech with high-contrast white captions), system releases are quantitatively benchmarked across **5 difficulty tiers** measuring:
1. **Character Error Rate (CER)** and **Word Error Rate (WER)**.
2. **Translation Semantic Parity (BLEU & chrF++)**.
3. **P90 / P95 End-to-End Latency Profiles**.
4. **Perceptual Gating Rejection Rate (Zero Redundant Compute on Static Frames)**.

---

## 2. The 5-Tier Stress Benchmark Matrix

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   HETEROGENEOUS BENCHMARK MATRIX                       │
├─────────┬────────────────────────────┬─────────────────────────────────┤
│ Level 1 │ Standard Baseline          │ YouTube 1080p, White Font, EN,  │
│         │ (Clean Lab)                │ Dark Background, Bottom-Center  │
├─────────┼────────────────────────────┼─────────────────────────────────┤
│ Level 2 │ Multilingual & Dense       │ Japanese Kanji/Kana, Chinese,   │
│         │ (Character Challenge)      │ Korean Hangul, Serif/Mincho     │
├─────────┼────────────────────────────┼─────────────────────────────────┤
│ Level 3 │ Burned-In & Dynamic BG     │ Yellow cinema font, Italics,    │
│         │ (Visual Noise Challenge)   │ High-key bright video scenes    │
├─────────┼────────────────────────────┼─────────────────────────────────┤
│ Level 4 │ Rapid Motion & Splitting   │ Fast dialogue (< 0.7s pacing),  │
│         │ (Temporal & Dual-Band)     │ Dual-band split (Top & Bottom)  │
├─────────┼────────────────────────────┼─────────────────────────────────┤
│ Level 5 │ Spatial Anomalies          │ Vertical text (Tategaki - 縦書き│
│         │ (Nightmare & Edge Cases)   │ on right/left edges), semi-trans│
└─────────┴────────────────────────────┴─────────────────────────────────┘
```

---

### Level 1: Clean Baseline (Easy)
- **Visual Attributes:** 1080p video, standard sans-serif font (Arial, Roboto), white text with solid black outline stroke, centered bottom of video frame.
- **Timing:** 3.0–5.0 seconds per subtitle line.
- **Target Pass Criteria:**
  - $\text{WER} \le 2.0\%$
  - $\text{CER} \le 1.0\%$
  - End-to-End Latency $\le 150\text{ ms}$

### Level 2: Multilingual Dense Typography (Medium)
- **Visual Attributes:** Non-Latin glyphs with high stroke density:
  - Japanese: Kanji, Hiragana, Katakana with mixed ASCII numerals. Mincho and Gothic typography.
  - Chinese: Simplified and Traditional characters across standard video aspect ratios.
  - Korean: Hangul syllable blocks with varied typographical weights.
- **Target Pass Criteria:**
  - Multilingual $\text{CER} \le 2.0\%$
  - Zero CTC blank-index hallucination loops.

### Level 3: Stylized Burned-In Hardcoded Subtitles (Hard)
- **Visual Attributes:**
  - Burned-in yellow cinema captions (`#FDE047`), italicized speaker dialogue.
  - Minimal bounding box contrast (e.g. captions superimposed directly over snowfields, desert glare, explosions, or dynamic concert lighting).
  - Soft semi-transparent drop shadows rather than crisp opaque borders.
- **Target Pass Criteria:**
  - $\text{CER} \le 3.5\%$
  - Zero ghost box hallucination on background text (t-shirts, street signs).

### Level 4: Rapid Motion & Dual-Band Splitting (Very Hard)
- **Visual Attributes:**
  - High-velocity dialogue exchanges where subtitle lines transition every $< 0.8\text{s}$ (stresses frame-diff gating and temporal debouncing).
  - **Dual-Band Concurrent Captions:** Speaker translation or song lyrics rendered in top 20% horizontal strip, while dialogue subtitles appear concurrently in bottom 25% strip.
- **Target Pass Criteria:**
  - Zero dialogue line dropouts.
  - Reading order clustering correctly separates top band from bottom band.

### Level 5: Spatial Anomalies & Extreme Edge Cases (Nightmare)
- **Visual Attributes:**
  - **Vertical Subtitles (Tategaki - 縦書き):** Captions arranged vertically along the right or left edge of the video (common in Japanese variety shows, anime songs, vintage Hong Kong cinema).
  - **Low-Opacity Captions:** 40% to 60% alpha translucency blending with video backgrounds.
  - Multi-line paragraph stacking exceeding 3 lines.
- **Target Pass Criteria:**
  - Identify failure boundaries gracefully without pipeline crashes or infinite OCR latency spikes.

---

## 3. Mathematical Evaluation Metrics

### 1. Character Error Rate (CER)
$$\text{CER} = \frac{S + D + I}{N_{\text{ref\_chars}}}$$
Where:
- $S$: Substitutions (incorrect characters recognized)
- $D$: Deletions (characters missed by OCR)
- $I$: Insertions (spurious characters hallucinated)
- $N_{\text{ref\_chars}}$: Total character count in ground truth reference transcript

### 2. Word Error Rate (WER)
$$\text{WER} = \frac{S + D + I}{N_{\text{ref\_words}}}$$

### 3. Translation Quality (chrF++ & BLEU)
- Measure semantic fidelity of machine-translated outputs against official studio-localized subtitle tracks.

### 4. P90 / P95 Latency Telemetry
- Measure elapsed time across individual pipeline stages:
  $$\Delta t_{\text{total}} = \Delta t_{\text{capture}} + \Delta t_{\text{diff}} + \Delta t_{\text{ocr}} + \Delta t_{\text{translate}} + \Delta t_{\text{render}}$$
- Target V2 Rust Performance: $\Delta t_{\text{total}} \le 110\text{ ms}$ (P95).
