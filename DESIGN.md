---
name: run-coach
description: Quiet post-run reports built from type, space, hairlines and one muted green; the plan sits as a soft band under what you ran.
colors:
  page: "#fbfbfa"
  ink: "#18181a"
  ink-2: "#5c5c62"
  muted: "#8b8b91"
  rule: "#ececea"
  axis: "#d6d6d3"
  accent: "#2f6f55"
  target: "#e6f0ea"
  target-edge: "#b9d3c4"
  easy: "#f2f2f0"
  hit: "#2f6f55"
  off: "#d0603f"
  off-ink: "#b04a2c"
  caution: "#d39a2a"
  z1: "#dcebe2"
  z2: "#b3d2c0"
  z3: "#7fb198"
  z4: "#4b8a6c"
  z5: "#2f6f55"
  z-ink-light: "#1f3a2d"
  z-ink-dark: "#ffffff"
  chip: "#f3f3f1"
  focus: "#2f6f55"
  page-dark: "#111113"
  ink-dark: "#ededee"
  ink-2-dark: "#a8a8ad"
  muted-dark: "#7c7c82"
  rule-dark: "#232326"
  axis-dark: "#333337"
  accent-dark: "#7fc3a2"
  target-dark: "rgba(127,195,162,.13)"
  target-edge-dark: "rgba(127,195,162,.4)"
  easy-dark: "#1b1b1e"
  hit-dark: "#7fc3a2"
  off-dark: "#ec8a6b"
  off-ink-dark: "#f09a7d"
  z1-dark: "#24392f"
  z2-dark: "#2f5443"
  z3-dark: "#3f7a5f"
  z4-dark: "#5c9e7f"
  z5-dark: "#7fc3a2"
  z-ink-light-dark: "#e6f2eb"
  z-ink-dark-dark: "#10241a"
  chip-dark: "#1b1b1e"
  focus-dark: "#7fc3a2"
typography:
  display:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "clamp(32px, 7vw, 44px)"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  figure-xl:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "48px"
    fontWeight: 300
    lineHeight: 1
    letterSpacing: "-0.03em"
    fontFeature: "tnum"
  figure:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  figure-sm:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 400
    lineHeight: 1.25
    letterSpacing: "-0.015em"
    fontFeature: "tnum"
  quote:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "20px"
    fontWeight: 300
    lineHeight: 1.5
    letterSpacing: "-0.01em"
  lead:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
  body:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.55
  data:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    fontFeature: "tnum"
  meta:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
  label:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
  caption:
    fontFamily: "Onest, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
rounded:
  tick: "2px"
  mark: "3px"
  bar: "4px"
  tip: "8px"
  round: "50%"
spacing:
  hair: "4px"
  tight: "8px"
  row: "16px"
  gutter: "20px"
  cluster: "24px"
  band: "28px"
  block: "40px"
  section-compact: "56px"
  section: "64px"
  coda: "80px"
components:
  stat:
    textColor: "{colors.ink}"
    typography: "{typography.figure}"
  stat-label:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
  jump-link:
    textColor: "{colors.accent}"
    height: "40px"
  theme-toggle:
    backgroundColor: "transparent"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.round}"
    size: "40px"
  theme-toggle-hover:
    backgroundColor: "{colors.chip}"
  table-cell:
    textColor: "{colors.ink}"
    typography: "{typography.data}"
    padding: "13px 8px"
  table-head:
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    padding: "0 8px 10px"
  status-ok:
    textColor: "{colors.ink-2}"
    typography: "{typography.meta}"
  status-off:
    textColor: "{colors.off-ink}"
    typography: "{typography.meta}"
  tooltip:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.page}"
    rounded: "{rounded.tip}"
    padding: "8px 11px"
    typography: "{typography.label}"
    width: "240px"
  plan-band:
    backgroundColor: "{colors.target}"
    rounded: "{rounded.mark}"
  plan-band-easy:
    backgroundColor: "{colors.easy}"
    rounded: "{rounded.mark}"
  zone-bar:
    rounded: "{rounded.bar}"
    height: "28px"
---

# Design System: run-coach

## Overview

**Creative North Star: "The Plan Under the Run"**

A coach's recap read on a phone straight after a session, outdoors, at a glance. The system is the category-standard training report stripped to type, space and one accent: an off-white page with no containers, hairline rules between groups, Onest at light-to-medium weights, and a single muted green that means "planned" or "in target". What the athlete planned is always drawn as a soft green band; what they ran is drawn on top of it as a line or figure. Everything else is ink on paper.

Density is calm rather than sparse. Sections stack in one column with large, even gaps (64px), key figures are big and light, and supporting text sits in a muted grey at 13–14px. Colour carries meaning, never decoration: green for plan and success, coral only for off-target, amber only as a readiness-caution dot. Status is a small dot followed by a word, never a filled pill. The world refuses cards, badges, heavy coloured bands and blue SaaS chrome.

The page carries light and dark themes as equals: it follows the OS preference and accepts a manual override (`data-theme="light" | "dark"` on the root). Dark mode is a near-black page with a lifted mint green accent and translucent plan bands.

**Key Characteristics:**
- Off-white page, no cards, hairline rules (1px) as the only structure.
- One green accent, one off-target coral, one caution amber; nothing else is chromatic.
- Planned = soft band underneath; actual = line or figure on top.
- Large, light, tabular figures; medium-weight headings; muted small labels.
- Status as dot + text.
- Light and dark at parity, OS-driven with a manual toggle.

## Colors

A near-neutral paper-and-ink palette with one muted forest green, a soft coral for misses, and amber reserved for a single caution dot.

### Primary
- **Coach Green** (`accent`, also `hit`, `focus`, `z5`): planned/in-target meaning everywhere it appears: the actual-pace line when in target, the HR line, the "good" delta in a stat, the in-page jump link, the RPE scale fill, the focus ring. In dark mode it lifts to Mint (`accent-dark`).
- **Plan Wash** (`target`) with **Plan Edge** (`target-edge`): the fill and 1px edge of a planned target band for work steps, and the `::selection` and focused-hit-area fill. In dark mode both are translucent mint.

### Secondary
- **Off-Target Coral** (`off`): marks only, for a measured value outside its planned band: the actual-pace line of a slow rep, the status dot of a "Slow" row.
- **Coral Ink** (`off-ink`): the text form of coral, for gap values ("+4 s") and the "Slow" status word. Text uses `off-ink`, never `off`.

### Tertiary
- **Readiness Amber** (`caution`): appears only as a 7–8px dot beside a word (the verdict status line, the "Readiness" context label). Never text, never fill, never border. It currently has no dark-mode override.

### Neutral
- **Paper** (`page`): page background; also the tooltip text and the knockout stroke around chart dots.
- **Ink** (`ink`): headings, verdict, key figures, table values; also the tooltip background (inverted).
- **Graphite** (`ink-2`): secondary prose, impact detail lines, in-target status words, chart step labels, the theme toggle icon.
- **Muted Grey** (`muted`): labels, meta lines, axis ticks, legend text, table heads, footer. At 3.3:1 on Paper in light mode it falls short of PRODUCT.md's sunlight-contrast requirement. Treat it as a known gap to fix, not a pattern to copy into longer text.
- **Hairline** (`rule`): every 1px divider and chart gridline.
- **Axis** (`axis`): the chart baseline and the `·` separators in the status line.
- **Easy Wash** (`easy`): planned bands for easy, warm-up, jog and cool-down steps, with no edge.
- **Chip** (`chip`): the theme-toggle hover wash, the only hover background in the system.

### Zone Ramp
Five steps of the accent hue from pale to full (`z1`…`z5`; dark: `z1-dark`…`z5-dark`, dark-to-mint). Zone 5 equals the accent. Labels on zone bars use `z-ink-light` (deep green) or `z-ink-dark` (white in light mode, deep green-black in dark mode); choose whichever clears 4.5:1 against the bar.

### Named Rules
**The One Green Rule.** Green means planned or in target. It is never used for decoration, headings or brand flourish.

**The Coral Means Off Rule.** Coral appears only where a measured value falls outside its planned band. A screen with every rep on target has no coral on it.

**The Amber Dot Rule.** Readiness caution is a single small amber dot beside a word. It never becomes a banner, a fill or a text colour.

## Typography

**Display Font:** Onest (with system-ui, sans-serif)
**Body Font:** Onest (with system-ui, sans-serif)

**Character:** One humanist grotesque at weights 300–500 does every job. Light weights carry big numbers and the athlete's own words; medium weight carries headings and the one-line outcome. Loaded from Google Fonts as the `300..600` variable range.

### Hierarchy
- **Display** (500, clamp(32px, 7vw, 44px), 1.1, -0.025em, balanced wrap): the session title, once per page.
- **Headline** (500, 19px, 1.3, -0.01em): section titles. Each is followed by a muted 14px sub-line (max 64ch) explaining how to read the section.
- **Figure XL** (300, 48px, 1, -0.03em): the single hero number of a section (RPE).
- **Figure** (400, 28px, 1.2, -0.02em): summary stats.
- **Figure Small** (400, 22px, 1.25, -0.015em): context readings (HRV, sleep, RHR, load).
- **Quote** (300, 20px, 1.5, -0.01em, max 46ch): the athlete's own words, in their language.
- **Lead** (400, 18px, 1.6, max 62ch): the coach's verdict paragraph, in the athlete's language.
- **Body** (400, 16px, 1.55): impact items and running text.
- **Data** (400, 15px; 14px under 720px): table cells.
- **Meta** (400, 14px): date line, status line, sub-lines, proposal note.
- **Label** (400, 13px): stat labels, table heads, legend, tags, tooltip.
- **Caption** (400, 12px): chart tick labels, RPE scale ends, footer.

### Named Rules
**The Light Figures Rule.** Numbers get bigger and lighter, not bolder: key figures sit at 300–400, and no text exceeds 500.

**The Tabular Figures Rule.** Every number that can be compared (table cells, stats, tooltip rows) uses `font-variant-numeric: tabular-nums`.

**The Sentence Case Rule.** Labels, heads and status words are sentence case at normal tracking. Hierarchy comes from size, weight and the ink/graphite/muted steps.

## Layout

A single centred column (max 760px, 1000px from 900px wide) with 20px side gutters and 64px bottom padding. The header opens 40px below the chrome line; sections are separated by 64px (56px under 720px), and the footer sits 80px below the last section.

Summary stats are a 4-column grid with 24px gaps between two hairlines with 28px inner padding; under 720px it becomes 2×2 with 24px/16px gaps. Context readings are a 3-column grid (2 columns under 720px) with 28px/24px gaps. From 900px, paired sections (reps + HR, zones + feel) sit side by side in two equal columns with a 64px gap; below that they stack.

Spacing rhythm inside a section: headline, 4px, sub-line, 20px, content, 14px, legend. List rows and table rows breathe at 13–16px vertical padding, separated by hairlines, with the first row's top rule and the last row's bottom rule removed. Tap targets (theme toggle, jump link) are at least 40px tall.

Charts are fluid SVGs drawn to their container width and redrawn on resize (120ms debounce); below 520px the pace chart shortens (310px to 260px), labels collapse to "R1"…"R5", and tick spacing halves.

## Elevation & Depth

Fully flat. There are no shadows; depth comes only from the Paper/Ink contrast, tonal washes (plan bands, zone ramp) and 1px hairlines. The one floating element, the tooltip, separates by inverting colour (Ink background, Paper text), not by casting a shadow. The legend swatch for the plan band uses a 1px inset box-shadow purely as a border for the swatch.

### Named Rules
**The No Container Rule.** Nothing is boxed. Groups are separated by space and hairlines, never by cards, panels, fills or shadows.

## Shapes

Small, soft corners on data marks only: 2px on RPE ticks, 3px on plan bands and legend swatches, 4px on zone bars and the focus ring, 8px on the tooltip. Status dots, the HR markers and the theme toggle are full circles. Text blocks, sections and tables have no corners because they have no boxes. Lines (actual pace, HR) use round caps and joins.

## Components

### Status Line
Quiet and declarative. An 8px amber or green dot, then the outcome in Ink at 500, then supporting facts in Graphite, separated by Axis-coloured `·`. Wraps freely (6px/14px gaps).

### Stat
A muted 13px label, a Figure (28px, 400), then a muted 13px plan line and a Graphite delta beneath it. The delta turns green only when it states success ("in target"). Stats share a grid between two hairlines and never get their own box.

### Jump Link
Accent-coloured 15px/500 text with a trailing down-arrow SVG icon, at least 40px tall. Hover: underline with 4px offset. No button chrome.

### Theme Toggle
A 40px circular icon button, transparent, Graphite icon (inline SVG moon). Hover: Chip wash. Focus: the global ring.

### Table
Full width, collapsed borders, hairline row dividers, no zebra striping, no outer border. Heads are muted 13px at weight 400, left-aligned except numeric columns, which right-align. First and last columns drop their outer padding so the table aligns with the text column. The row number is muted.

### Status Mark
Dot plus word: a 7px dot (Coach Green or Coral) and a 14px word ("In target" in Graphite, "Slow" in Coral Ink). This is the only status treatment.

### Tooltip
Inverted (Ink on Paper), 8px corners, 8px/11px padding, 13px, max 240px wide. Title row at 500; value rows at 80% opacity, tabular. Fades and rises 4px in over 160ms with `cubic-bezier(.16,1,.3,1)`; no transition under reduced motion. Every chart hit area is keyboard-focusable and shows the same tooltip on focus; a focused hit area fills with Plan Wash.

### Focus
A 2px `focus` outline with 3px offset and 4px corner radius, globally via `:focus-visible`.

### Chart Marks (signature)
- **Planned band:** a rounded (3px) rect spanning the step's duration and target range. Work steps use Plan Wash with a 1px Plan Edge; easy steps use Easy Wash with no edge.
- **Actual line:** a horizontal round-capped stroke at the measured value, inset 2.5px from the band ends: 2.5px for work steps, 1.5px for easy steps; Coach Green when in band, Coral when out.
- **Gap label:** "+Ns" in Coral Ink, 12px, just below the band of an off-target step.
- **Trend line:** a 1.75px Coach Green polyline; points are 4px-radius filled dots with a 2px Paper knockout stroke. Secondary values (max HR) are 3.5px hollow Muted circles.
- **Grid:** 1px Hairline gridlines, Axis baseline, 12px muted tick labels; step labels in Graphite.
- **Stacked zone bars:** 28px tall, 4px corners, 3px gaps, filled from the zone ramp; inline values only when the segment is wider than 22px.

### RPE Scale
A 48px light figure, then ten 4px rounded ticks (Hairline when empty, Coach Green when on), with a 12px muted scale beneath that marks the expected range.

### Impact List
An unstyled list of rows divided by hairlines: a 500-weight title and a Graphite explanation, followed by a muted note that proposals change nothing without the athlete's OK.

## Do's and Don'ts

### Do:
- **Do** draw every planned target as a soft band (Plan Wash + 1px Plan Edge for work, Easy Wash for recovery) and the actual value on top of it.
- **Do** separate groups with 1px Hairlines and the 64px section rhythm; keep the page on Paper.
- **Do** show status as a 7–8px dot plus a sentence-case word.
- **Do** set comparable numbers in tabular figures, large and light (300–400).
- **Do** make every chart datum keyboard-focusable with the inverted tooltip.
- **Do** define every colour for both themes and honour both the OS preference and the manual `data-theme` override.
- **Do** use inline SVG icons drawn with `currentColor`.

### Don't:
- **Don't** put content in cards, panels, tinted boxes or shadowed containers.
- **Don't** use filled status pills or badges; use dot + word.
- **Don't** use green, coral or amber decoratively; each carries one meaning.
- **Don't** set text in `off` coral or `caution` amber; text uses `off-ink`, and amber stays a dot.
- **Don't** introduce a second accent hue or blue product chrome.
- **Don't** set any text above weight 500.
- **Don't** use COROS or Garmin branding, colours or marks.
