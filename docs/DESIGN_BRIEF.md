# Design brief — Tellumen climate platform

> **Generated — do not edit by hand.** Written by `scripts/build_project_docs.py` from `data/reference/ui_standard.json`, `web/src/index.css`, `web/src/skins.css`, `web/index.html`, the shared components (`web/src/components/ui.tsx`, `Dialog.tsx`, `Drawer.tsx`, `Toaster.tsx`, `BrandMark.tsx`) and the palette table of `docs/BRAND.md`. Regenerate with `venv/bin/python -m scripts.build_project_docs --write`; the gate (`scripts/precommit.sh`) fails when this file differs from what the code produces now.

Section 1 is the standard every screen must meet — it governs. Sections 2–9 describe the visual system as the web app's code defines it today; where today's UI differs from section 1, section 1 is the target. The brand itself — name, mark, palette and usage rules — is [BRAND.md](BRAND.md); it is linked here, not restated or extended. Screens and navigation are in [APP_FLOW.md](APP_FLOW.md).

## 1. The standard every screen must meet (governing)

Stated by the product owner on 2026-10-16; it applies to everything built and everything still to be built. Recorded in `data/reference/ui_standard.json` (the product owner's instruction of 2026-10-16, relayed by the main working session).

1. **Customer language only.** Only external-facing, customer language on screen.
   Never on screen: internal keys; file paths; layer or registry names; E-numbers; version strings; "product owner's decision"; engineering jargon (for example "named gap", "append-only").
2. **Little text on the main screen; detail on demand.** As little text as possible on the main UI; further detail in a drill-down pop-up (Dialog or Drawer) with professionally written, structured text.
3. **Visual first.** As much visual representation as possible on the main UI.
   For example: charts, maps, chips, gauges, diagrams.
4. **Legal citations one click away.** The main screen says it in plain words; an article, annex, regulation or template number, or a standard's metric code, sits in the drill-down pop-up (Dialog or Drawer) and in filings and exports. Names customers use as categories stay on screen. (Stated on 2026-10-18.)
   For example: 'Art. 90b', 'Del. Reg. 2015/35' and 'S.27.01.01' in the pop-up, an 'Article 8 fund', Pillar 3, SFDR and Solvency II on screen.

The drill-down pop-ups are the shared `Dialog` and `Drawer` (section 7); the visual building blocks in use today are listed in sections 7 and 9.

Known to break it today: `/loss` — breaks the standard and will be reworked; its text is not the house style.

## 2. The brand in the product

- **Mark** — `BrandMark` in `web/src/components/BrandMark.tsx` (props: size). Its comment: “The Tellumen mark (docs/BRAND.md §4): a hexagon — the H3 cell the engine tessellates the Earth into — holding a rising lumen. Bold stroke + bright core so it reads at small nav sizes; self-contained colours so it works on light or dark. Never recolour, rotate or stretch it; minimum 20 px. public/favicon.svg carries the same geometry. Gradient ids are per instance: the shell renders the mark more than once, and a url(#id) that resolves into a hidden copy (the sidebar below md, the small-screen header above it) paints nothing.” Colours in its SVG: `#06152e`, `#1560c4`, `#3aa0ff`, `#6cb8ff`, `#9fd4ff`, `#f2f9ff`, `#ffffff`.
- **Wordmark** — `Wordmark` in the same file (props: className). Its comment: “The wordmark (docs/BRAND.md §3): one word, with "lumen" lit — Sky on dark, Signal Blue on light. The colours are the --brand-* tokens in index.css, which follow the theme; size and layout come from the caller.” Colours: `--brand-tel` #1d1d1f / #eaf6ff and `--brand-lumen` #0071e3 / #8fd0ff (light / dark).
- **Favicon** — `web/public/favicon.svg`, linked from `web/index.html`.

The palette of [BRAND.md](BRAND.md) §5 and where each colour appears in the web app's files (`web/src`, `web/public`, `web/index.html`):

| Brand colour | Hex | Role (BRAND.md) | Found in |
|---|---|---|---|
| Space Navy | `#04070f` | Primary ground (the Earth-from-ISS dark) | `#04070f`: `web/src/components/LiveEarthHero.tsx` |
| Deep Hex | `#06152e` | Mark base, elevated panels | `#06152e`: `web/public/favicon.svg`, `web/src/components/BrandMark.tsx` |
| Signal Blue | `#0071e3` | Action, links, wordmark accent on light | `#0071e3`: `web/src/index.css` |
| Lumen Blue | `#3aa0ff` / `#6cb8ff` | The mark's light; highlights | `#3aa0ff`: `web/public/favicon.svg`, `web/src/components/BrandMark.tsx`; `#6cb8ff`: `web/public/favicon.svg`, `web/src/components/BrandMark.tsx` |
| Sky | `#8fd0ff` | Wordmark accent on dark; bright accents | `#8fd0ff`: `web/src/index.css` |
| Core | `#eaf6ff` | The lumen core; near-white on dark | `#eaf6ff`: `web/src/index.css` |
| Ink | `#1d1d1f` | Text on light surfaces | `#1d1d1f`: `web/src/index.css` |
| Surface | `#f5f5f7` | Light UI ground (the product interior is Apple-light) | `#f5f5f7`: not used |
| Blue-grey | `#8ea3c0` | Muted neutral (chosen, blue-biased — not a default grey) | `#8ea3c0`: `web/src/components/HexMap.tsx` |

## 3. Themes and skins

Two independent switches on `<html>`, both set before the app loads (`web/index.html`):

- **Theme** — `dataset.theme = localStorage.getItem('tellumen.theme') || 'dark';` → when nothing is stored the theme is **dark**. The stylesheet holds the light values in `:root` and the dark values in `[data-theme="dark"]`; the sidebar has a light / dark toggle.
- **Skin** — `dataset.skin = localStorage.getItem('tellumen.skin') || 'terminal';` → when nothing is stored the skin is **terminal**. Skins are in `web/src/skins.css`:

| Skin | Default | Rules |
|---|---|---|
| `luxe` |  | empty (no rules) |
| `terminal` | default | 13 rules |
| `vibrant` |  | empty (no rules) |

## 4. Colour tokens

Custom properties in `web/src/index.css`: the Tailwind `@theme` block (the base values utilities are generated from), `:root` (light) and `[data-theme="dark"]`. Components read them as `var(--token)`.

### Surface, text and status (`--color-*`)

| Token | Light | Dark | @theme | Note |
|---|---|---|---|---|
| `--color-bg` | #eef2f8 | #0a0f1c | #0a0f1c |  |
| `--color-bg-2` | #ffffff | #0e1728 | #0c1424 |  |
| `--color-panel` | #ffffff | #15213a | #111a2c |  |
| `--color-panel-2` | #f2f5fb | #1d2c48 | #16223a |  |
| `--color-line` | #dbe2ee | #2b3a54 | #1e2a40 |  |
| `--color-line-2` | #c6d1e1 | #384b6d | #2a3a56 |  |
| `--color-ink` | #111c2e | #eef3fb | #e8eef7 |  |
| `--color-mute` | #33425b | #adb9cd | #94a3b8 |  |
| `--color-faint` | #4f5f79 | #8492a8 | #64748b |  |
| `--color-sky` | #0369a1 | #8ad8ff | #7dd3fc |  |
| `--color-blue` | #0284c7 | #38bdf8 | #38bdf8 |  |
| `--color-blued` | #0c4a6e | #1560c4 | #1560c4 |  |
| `--color-good` | #15803d | #34d399 | #34d399 |  |
| `--color-warn` | #b45309 | #f59e0b | #f59e0b |  |
| `--color-bad` | #e11d48 | #fb7185 | #fb7185 |  |
| `--color-slate` | #44546c | #8290a8 | #8290a8 |  |
| `--color-halo` | #d6e4f5 | #0e1a30 |  |  |
| `--color-on-accent` | #ffffff | #08111f |  |  |

### Wordmark (`--brand-*`)

| Token | Light | Dark | @theme | Note |
|---|---|---|---|---|
| `--brand-tel` | #1d1d1f | #eaf6ff |  |  |
| `--brand-lumen` | #0071e3 | #8fd0ff |  |  |

### Operational-loop stages (`--stage-*`)

| Token | Light | Dark | @theme | Note |
|---|---|---|---|---|
| `--stage-sense` | #2b6cb0 | #6ab0f0 |  |  |
| `--stage-assess` | #5b52c9 | #9a91ef |  |  |
| `--stage-decide` | #b06a12 | #e0a24a |  |  |
| `--stage-disclose` | #0f7a5f | #3fbf97 |  |  |
| `--stage-operate` | #5a6a80 | #8290a8 |  |  |
| `--stage-setup` | #6a7990 | #8492a8 |  |  |

### Scenario ramp (charts) (`--scn-*`)

| Token | Light | Dark | @theme | Note |
|---|---|---|---|---|
| `--scn-baseline` | #2a78d6 | #3987e5 |  | Today |
| `--scn-orderly` | #12938a | #1fa595 |  | Orderly 1.5°C |
| `--scn-disorderly` | #d97e0a | #cf7d12 |  | Disorderly 2°C |
| `--scn-hot` | #d1355a | #d43d5c |  | Hot-house 3.5°C |

### Charts (`--chart-*`)

| Token | Light | Dark | @theme | Note |
|---|---|---|---|---|
| `--chart-seq` | #256abf | #3987e5 |  | single-hue sequential (hazard small-multiples) |
| `--chart-grid` | #e6ebf3 | #223049 |  |  |

### Contrast (computed)

WCAG 2.x contrast ratio of each text and status colour on the page ground and on a panel. *AA, normal text* needs at least 4.5 : 1; 3 : 1 suffices for large text.

| Theme | Text | On | Ratio | AA, normal text |
|---|---|---|---|---|
| light | `--color-ink` #111c2e | `--color-bg` #eef2f8 | 15.20 : 1 | yes |
| light | `--color-ink` #111c2e | `--color-panel` #ffffff | 17.08 : 1 | yes |
| light | `--color-mute` #33425b | `--color-bg` #eef2f8 | 9.02 : 1 | yes |
| light | `--color-mute` #33425b | `--color-panel` #ffffff | 10.14 : 1 | yes |
| light | `--color-faint` #4f5f79 | `--color-bg` #eef2f8 | 5.76 : 1 | yes |
| light | `--color-faint` #4f5f79 | `--color-panel` #ffffff | 6.47 : 1 | yes |
| light | `--color-good` #15803d | `--color-bg` #eef2f8 | 4.46 : 1 | large text only |
| light | `--color-good` #15803d | `--color-panel` #ffffff | 5.02 : 1 | yes |
| light | `--color-warn` #b45309 | `--color-bg` #eef2f8 | 4.47 : 1 | large text only |
| light | `--color-warn` #b45309 | `--color-panel` #ffffff | 5.02 : 1 | yes |
| light | `--color-bad` #e11d48 | `--color-bg` #eef2f8 | 4.18 : 1 | large text only |
| light | `--color-bad` #e11d48 | `--color-panel` #ffffff | 4.70 : 1 | yes |
| dark | `--color-ink` #eef3fb | `--color-bg` #0a0f1c | 17.17 : 1 | yes |
| dark | `--color-ink` #eef3fb | `--color-panel` #15213a | 14.38 : 1 | yes |
| dark | `--color-mute` #adb9cd | `--color-bg` #0a0f1c | 9.65 : 1 | yes |
| dark | `--color-mute` #adb9cd | `--color-panel` #15213a | 8.09 : 1 | yes |
| dark | `--color-faint` #8492a8 | `--color-bg` #0a0f1c | 6.06 : 1 | yes |
| dark | `--color-faint` #8492a8 | `--color-panel` #15213a | 5.08 : 1 | yes |
| dark | `--color-good` #34d399 | `--color-bg` #0a0f1c | 9.95 : 1 | yes |
| dark | `--color-good` #34d399 | `--color-panel` #15213a | 8.34 : 1 | yes |
| dark | `--color-warn` #f59e0b | `--color-bg` #0a0f1c | 8.91 : 1 | yes |
| dark | `--color-warn` #f59e0b | `--color-panel` #15213a | 7.46 : 1 | yes |
| dark | `--color-bad` #fb7185 | `--color-bg` #0a0f1c | 7.11 : 1 | yes |
| dark | `--color-bad` #fb7185 | `--color-panel` #15213a | 5.95 : 1 | yes |

## 5. Typography

| Token | Stack |
|---|---|
| `--font-display` | "Fraunces", Georgia, "Times New Roman", serif |
| `--font-sans` | "DM Sans", ui-sans-serif, system-ui, -apple-system, sans-serif |
| `--font-mono` | "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace |

Loaded from Google Fonts in `web/index.html`: `DM Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700`; `Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600`; `JetBrains Mono:wght@400;500`. The classes `.display` and `.mono` apply the display and mono stacks; the sans stack is the body default.

## 6. Shape, depth and motion

Defaults in `web/src/skins.css` `:root` (any skin may override):

| Token | Value | Note |
|---|---|---|
| `--radius` | `14px` |  |
| `--radius-lg` | `18px` |  |
| `--dur-1` | `.14s` |  |
| `--dur-2` | `.28s` |  |
| `--dur-3` | `.5s` |  |
| `--ease` | `cubic-bezier(.22,.61,.36,1)` | ease-out, gentle |
| `--ease-spring` | `cubic-bezier(.34,1.56,.64,1)` |  |
| `--elev-1` | `0 1px 2px rgba(8,15,30,.06)` |  |
| `--elev-2` | `0 6px 20px -10px rgba(8,15,30,.18)` |  |
| `--elev-3` | `0 18px 50px -18px rgba(8,15,30,.30)` |  |
| `--app-bg` | `var(--color-bg)` |  |
| `--surface` | `var(--color-panel)` |  |
| `--surface-top` | `transparent` | faint top-edge highlight on cards |
| `--accent-glow` | `transparent` | accent halo colour (transparent = off) |

Animations (`@keyframes`): `drift`, `fadeup`, `sheen`, `toastIn`. `prefers-reduced-motion: reduce` is handled in 3 places.

## 7. Shared components

The page kit and overlay primitives other screens build from (103 component files are in `web/src/components/`; the ones below are the shared kit). *Notes* is the comment above each in the code.

| Component | File | Props | Notes |
|---|---|---|---|
| `CountUp` | `ui.tsx` | value, format, duration, className | Count-up number — the KPI/stat "hooked" micro-moment. Animates from 0 to the value on mount/change, respects prefers-reduced-motion (jumps straight to the value), and renders through a formatter so it works for euros, percentages, and plain counts. Skin-agnostic; the motion reads on every skin. |
| `CountUpText` | `ui.tsx` | children, className, duration | Count-up for an ALREADY-formatted KPI string ("€648.1m", "US$1.20bn", "CHF 950k", "−€4.1m", "70%", "1,240"). Parses the single leading number — any non-digit prefix (a multi-letter currency symbol, the '−' sign) and the suffix are kept verbatim — animates it, and re-assembles with the original prefix/suffix/precision — so any KPI grid gets the count-up moment with no numeric plumbing. Falls back to the plain string for anything it can't cleanly parse (fractions like "129/145", ranges, status text), so it's always safe to drop in. |
| `ExportButton` | `ui.tsx` | onExport, label, className | The one consistent "export what I'm looking at" control — wired to lib/export downloadCsv on every view, so extract-to-your-own-tool is a standard affordance across all sectors, not an ad-hoc per-page button. |
| `Card` | `ui.tsx` | className, children, style, onClick, lift | `lift` opts a card into the hover-lift micro-interaction (used for clickable/drillable cards). The transform lives only during :hover (see skins.css) so it never leaves a retained transform that would trap fixed drawers. |
| `Eyebrow` | `ui.tsx` | children | The page's flow-stage hue tints the eyebrow (Shell sets --stage per route), so a page's header echoes its nav stage. Falls back to the neutral blue where --stage isn't set (e.g. login, standalone screens). |
| `PageHeader` | `ui.tsx` | eyebrow, title, lead, about, actions, children | The "great page" kit Standard page header — stage-coloured eyebrow, a large balanced title and at most one short line under it; the UI standard (2026-10-16) keeps explanations off the main screen: a `lead` longer than one short line (12 words), and any `about` sections, open from "About this page" in the details pop-up. Actions (filters/export/toggles) sit right. |
| `HeroMetric` | `ui.tsx` | value, label, tone, sub, className | A big headline metric — the "lead with the answer" hero number, count-up animated. Pass a preformatted string ("€648.1m", "70%") or a raw number. Optional tone colour and a small sub-line. |
| `HeroStrip` | `ui.tsx` | children, className, style | A hero summary strip — a row of HeroMetrics on one elevated card, evenly divided. The "answer first" band that leads most pages. Children are HeroMetric (or anything); they lay out as equal columns on ≥sm. |
| `PlainLead` | `ui.tsx` | children, className | A one-line plain-language explainer under a section head — the "what this is / how to read it" line that keeps a data-dense surface legible. Kept deliberately short. |
| `HeroBanner` | `ui.tsx` | eyebrow, title, lead, stat, className | The RICH hero — the "cockpit" banner (generalised from the filing cockpit): a gradient card with ambient stage-coloured glows, a narrative headline on the left, and a grid of icon'd status tiles (count-up) on the right. This is what makes a page feel designed rather than a plain white stat row — use it as the lead on operational pages. `title` should be a short narrative line ("1 filing needs you", "Your book vs a warming world"); `stat` tiles carry the numbers. The glows read the page's --stage hue automatically. |
| `Lens` | `ui.tsx` | kind, className |  |
| `SectionHead` | `ui.tsx` | icon, hint, children, className | The one readable section/card heading used across the platform — a blue icon + a bold ~16px title, with an optional muted descriptor after a "·". Replaces the old tiny 10.5px mono-uppercase header bars, which were hard to read and identify. Chart axis/column micro-labels stay small — those are captions. |
| `StatCard` | `ui.tsx` | label, value, sub, accent, title |  |
| `StatGrid` | `ui.tsx` | items, cols, className |  |
| `Stat` | `ui.tsx` | big, label, tone |  |
| `StatusPill` | `ui.tsx` | status |  |
| `Button` | `ui.tsx` | children, onClick, variant, disabled, className |  |
| `CloseButton` | `Dialog.tsx` | onClick, size, icon, label, className, look | The one labelled close control for every overlay. `icon="back"` is the ‹ used by resizable side drawers; `look` replaces the default faint-glyph styling for a page with its own close design (the round buttons on the globe). |
| `Dialog` | `Dialog.tsx` | title, onClose, children, className, bare, overlayClassName, backdropClassName |  |
| `Drawer` | `Drawer.tsx` | label, onClose, children, className, style, resize, placement, overlayClassName, backdropClassName | The one side drawer — Dialog's sibling for panels that slide in from the right edge. Same behaviour: Escape closes it, a click on the scrim closes it, it is announced as a modal dialog named by `label`, focus moves into it on open and returns on close. The page keeps its own header and places a (labelled) CloseButton in it. `className` / `style` style the panel (width, padding, scrolling); `resize` adds the drag handle on the left edge (from useResizableWidth). `placement="left"` slides in from the left edge (the app menu on small screens). `placement="full"` is the full-screen takeover variant (the filing view): it covers the page, so there is no scrim to click — Escape or the close button dismiss it. |
| `Toaster` | `Toaster.tsx` |  |  |
| `BrandMark` | `BrandMark.tsx` | size | The Tellumen mark (docs/BRAND.md §4): a hexagon — the H3 cell the engine tessellates the Earth into — holding a rising lumen. Bold stroke + bright core so it reads at small nav sizes; self-contained colours so it works on light or dark. Never recolour, rotate or stretch it; minimum 20 px. public/favicon.svg carries the same geometry. Gradient ids are per instance: the shell renders the mark more than once, and a url(#id) that resolves into a hidden copy (the sidebar below md, the small-screen header above it) paints nothing. |
| `Wordmark` | `BrandMark.tsx` | className | The wordmark (docs/BRAND.md §3): one word, with "lumen" lit — Sky on dark, Signal Blue on light. The colours are the --brand-* tokens in index.css, which follow the theme; size and layout come from the caller. |

Helpers: `pressable` in `web/src/lib/pressable.ts` — “Makes a clickable element that is not a &lt;button&gt; — a card, a stat tile, a table row, a map shape — reachable with Tab and operable with Enter / Space, so everything a mouse can open a keyboard can open too (and an overlay opened from it has somewhere to return focus). Spread it in place of onClick: `<div {...pressable(open)}>`. With no handler it returns nothing, so a conditionally clickable element stays inert. `row`: a table row keeps its row semantics (no role="button"); `expanded`: the element toggles a disclosure; `label`: an accessible name where the element has no readable text (an SVG shape).”; `web/src/lib/toast.ts` exports `ToastKind`, `ToastItem`, `dismiss`, `subscribe`, `toast`.

## 8. Global classes

Top-level class rules in `web/src/index.css` with the comment above each:

| Class | Comment |
|---|---|
| `.mono` | utility bits |
| `.display` |  |
| `.public-page` | Public (signed-out) pages: themed halo, content centred but never clipped when the window is short. |
| `.data-table` | Data tables (supervisory workspace and beyond): headers and cells vertically centred, headers set as small caps with one baseline, text columns left, numeric columns right (via .num), consistent padding. |
| `.card` |  |
| `.hairline` |  |
| `.glow` |  |
| `.react-flow__attribution` | React Flow theme overrides |
| `.react-flow__edge-path` |  |
| `.react-flow__node` |  |
| `.fadeup` |  |
| `.toast-in` |  |
| `.drift` |  |

## 9. UI libraries

From `web/package.json` (versions as declared; resolved versions are in [TECHNICAL_REQUIREMENTS.md](TECHNICAL_REQUIREMENTS.md) §3):

| Package | Declared |
|---|---|
| `@tailwindcss/vite` | ^4.3.3 |
| `@xyflow/react` | ^12.11.2 |
| `clsx` | ^2.1.1 |
| `framer-motion` | ^12.42.2 |
| `h3-js` | ^4.5.0 |
| `leaflet` | ^1.9.4 |
| `lucide-react` | ^1.27.0 |
| `maplibre-gl` | ^6.0.0 |
| `react-leaflet` | ^5.0.0 |
| `recharts` | ^3.10.1 |
| `tailwindcss` | ^4.3.3 |
