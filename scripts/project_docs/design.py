"""docs/DESIGN_BRIEF.md — first the presentation standard every screen must meet (data/reference/ui_standard.json,
governing), then the visual system as the web app's code defines it: themes and skins, colour, type, shape and
motion tokens, the shared components, and where the brand's own assets (docs/BRAND.md) appear in the product. The brand
book is linked, never restated or extended; contrast ratios are computed (WCAG 2.x relative luminance)."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

from scripts.project_docs.source import (
    ROOT,
    banner,
    css_block,
    css_vars,
    exported_functions,
    prose,
    read,
    table,
)

CSS, SKINS, HTML = "web/src/index.css", "web/src/skins.css", "web/index.html"
STANDARD = "data/reference/ui_standard.json"
KIT = ["web/src/components/ui.tsx", "web/src/components/Dialog.tsx", "web/src/components/Drawer.tsx",
       "web/src/components/Toaster.tsx", "web/src/components/BrandMark.tsx"]
FAMILIES = [("--color-", "Surface, text and status"), ("--brand-", "Wordmark"), ("--stage-", "Operational-loop stages"),
            ("--scn-", "Scenario ramp (charts)"), ("--chart-", "Charts")]


def luminance(hex_colour: str) -> float:
    """WCAG 2.x relative luminance of #rrggbb."""
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hex(v: str | None) -> str | None:
    return v.lower() if v and re.fullmatch(r"#[0-9a-fA-F]{6}", v) else None


def brand_palette(brand_md: str) -> list[tuple[str, list[str], str]]:
    """(name, hex values, role) from the table in docs/BRAND.md §5."""
    sec = re.search(r"^## 5\. Palette\n(.*?)(?=^## )", brand_md, re.M | re.S).group(1)
    rows = []
    for line in sec.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        hexes = re.findall(r"#[0-9a-fA-F]{6}", line)
        if len(cells) == 3 and hexes:
            rows.append((cells[0], [h.lower() for h in hexes], cells[2]))
    return rows


def _where(hex_colour: str, files: dict[str, str]) -> list[str]:
    return sorted(f for f, text in files.items() if hex_colour in text.lower())


def _class_rules(css: str) -> list[list[str]]:
    """Top-level `.class { … }` rules of a stylesheet with the comment that precedes them, if any."""
    lines = css.splitlines()
    out, seen = [], set()
    for k, line in enumerate(lines):
        m = re.match(r"^\.([\w-]+)\s*\{", line)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        block, j = [], k - 1
        if j >= 0 and lines[j].rstrip().endswith("*/"):
            while j >= 0:
                block.insert(0, lines[j])
                if "/*" in lines[j]:
                    break
                j -= 1
        text = " ".join(" ".join(block).replace("/*", " ").replace("*/", " ").split())
        out.append([f"`.{m.group(1)}`", text])
    return out


def ui_standard(std: dict) -> list[str]:
    """Section 1: the presentation standard, as recorded in data/reference/ui_standard.json."""
    out = ["## 1. The standard every screen must meet (governing)", "",
           f"Stated by the {std['stated_by']} on {std['date']}; it applies to {std['applies_to']}. Recorded in "
           f"`{STANDARD}` ({std['recorded_from']}).", ""]
    for k, r in enumerate(std["rules"], 1):
        out.append(f"{k}. **{r['title']}.** {r['rule']}")
        if r.get("not_on_screen"):
            out.append("   Never on screen: " + "; ".join(r["not_on_screen"]) + ".")
        if r.get("examples"):
            out.append("   For example: " + ", ".join(r["examples"]) + ".")
    out += ["", "The drill-down pop-ups are the shared `Dialog` and `Drawer` (section 7); the visual building blocks in "
            "use today are listed in sections 7 and 9."]
    if std.get("known_breaches"):
        out += ["", "Known to break it today: " + "; ".join(f"`{b['route']}` — {b['note']}" for b in std["known_breaches"])
                + "."]
    return out + [""]


def render() -> str:
    css, skins, html = read(CSS), read(SKINS), read(HTML)
    base = {k: (v, n) for k, v, n in css_vars(css_block(css, "@theme"))}
    light = {k: (v, n) for k, v, n in css_vars(css_block(css, ":root"))}
    dark = {k: (v, n) for k, v, n in css_vars(css_block(css, '[data-theme="dark"]'))}
    package = json.loads(read("web/package.json"))
    web_files = {str(p.relative_to(ROOT)): p.read_text(encoding="utf-8", errors="ignore")
                 for pattern in ("web/src/**/*.css", "web/src/**/*.tsx", "web/src/**/*.ts", "web/public/*.svg",
                                 "web/index.html") for p in sorted(ROOT.glob(pattern))}

    theme_line = re.search(r"dataset\.theme = [^\n]*", html).group(0).strip()
    skin_line = re.search(r"dataset\.skin = [^\n]*", html).group(0).strip()
    default_theme = re.search(r"\|\|\s*'(\w+)'", theme_line).group(1)
    default_skin = re.search(r"\|\|\s*'(\w+)'", skin_line).group(1)
    skin_names = sorted(set(re.findall(r'\[data-skin="(\w+)"\]', skins)))
    empty = {n for n in skin_names if re.search(rf'\[data-skin="{n}"\]\s*\{{\s*/\*[^*]*\*/\s*\}}', skins)}

    out = ["# Design brief — Tellumen climate platform", "",
           banner("`data/reference/ui_standard.json`, `web/src/index.css`, `web/src/skins.css`, `web/index.html`, the "
                  "shared components (`web/src/components/ui.tsx`, `Dialog.tsx`, `Drawer.tsx`, `Toaster.tsx`, "
                  "`BrandMark.tsx`) and the palette table of `docs/BRAND.md`"), "",
           "Section 1 is the standard every screen must meet — it governs. Sections 2–9 describe the visual system as "
           "the web app's code defines it today; where today's UI differs from section 1, section 1 is the target. "
           "The brand itself — name, mark, palette and usage rules — is [BRAND.md](BRAND.md); it is linked here, not "
           "restated or extended. Screens and navigation are in [APP_FLOW.md](APP_FLOW.md).", ""]
    out += ui_standard(json.loads(read(STANDARD)))

    # 1 · brand in the product
    mark = next(e for e in exported_functions(read("web/src/components/BrandMark.tsx")) if e["name"] == "BrandMark")
    word = next(e for e in exported_functions(read("web/src/components/BrandMark.tsx")) if e["name"] == "Wordmark")
    mark_colours = sorted(set(h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}", read("web/src/components/BrandMark.tsx"))))
    pal = []
    for name, hexes, role in brand_palette(read("docs/BRAND.md")):
        pal.append([name, " / ".join(f"`{h}`" for h in hexes), role,
                    "; ".join(f"`{h}`: " + (", ".join(f"`{f}`" for f in _where(h, web_files)) or "not used")
                              for h in hexes)])
    out += ["## 2. The brand in the product", "",
            f"- **Mark** — `BrandMark` in `web/src/components/BrandMark.tsx` (props: {', '.join(mark['params'])}). "
            f"Its comment: “{prose(mark['comment'])}” Colours in its SVG: {', '.join(f'`{h}`' for h in mark_colours)}.",
            f"- **Wordmark** — `Wordmark` in the same file (props: {', '.join(word['params'])}). Its comment: "
            f"“{prose(word['comment'])}” Colours: `--brand-tel` {light['--brand-tel'][0]} / {dark['--brand-tel'][0]} and "
            f"`--brand-lumen` {light['--brand-lumen'][0]} / {dark['--brand-lumen'][0]} (light / dark).",
            "- **Favicon** — `web/public/favicon.svg`, linked from `web/index.html`." if (ROOT / "web/public/favicon.svg").exists()
            else "- **Favicon** — none in `web/public/`.", "",
            "The palette of [BRAND.md](BRAND.md) §5 and where each colour appears in the web app's files "
            "(`web/src`, `web/public`, `web/index.html`):", "",
            table(["Brand colour", "Hex", "Role (BRAND.md)", "Found in"], pal), ""]

    # 2 · themes and skins
    skin_rows = [[f"`{n}`", "default" if n == default_skin else "",
                  "empty (no rules)" if n in empty else f"{len(re.findall(rf'\[data-skin=\"{n}\"\]', skins))} rules"]
                 for n in skin_names]
    out += ["## 3. Themes and skins", "",
            f"Two independent switches on `<html>`, both set before the app loads (`{HTML}`):", "",
            f"- **Theme** — `{theme_line}` → when nothing is stored the theme is **{default_theme}**. The stylesheet "
            f"holds the light values in `:root` and the dark values in `[data-theme=\"dark\"]`; the sidebar has a "
            "light / dark toggle.",
            f"- **Skin** — `{skin_line}` → when nothing is stored the skin is **{default_skin}**. Skins are in `{SKINS}`:",
            "", table(["Skin", "Default", "Rules"], skin_rows), ""]

    # 3 · colour tokens
    out += ["## 4. Colour tokens", "",
            f"Custom properties in `{CSS}`: the Tailwind `@theme` block (the base values utilities are generated from), "
            "`:root` (light) and `[data-theme=\"dark\"]`. Components read them as `var(--token)`.", ""]
    names = list(dict.fromkeys([*base, *light, *dark]))
    for prefix, title in FAMILIES:
        fam = [n for n in names if n.startswith(prefix)]
        if fam:
            out += [f"### {title} (`{prefix}*`)", "", table(["Token", "Light", "Dark", "@theme", "Note"], [
                [f"`{n}`", light.get(n, ("",))[0], dark.get(n, ("",))[0], base.get(n, ("",))[0],
                 light.get(n, ("", ""))[1] or dark.get(n, ("", ""))[1] or base.get(n, ("", ""))[1]] for n in fam]), ""]
    rows = []
    for theme, vals in (("light", light), ("dark", dark)):
        for fg in ("--color-ink", "--color-mute", "--color-faint", "--color-good", "--color-warn", "--color-bad"):
            for bg in ("--color-bg", "--color-panel"):
                a, b = _hex(vals.get(fg, ("",))[0]), _hex(vals.get(bg, ("",))[0])
                if a and b:
                    r = contrast(a, b)
                    rows.append([theme, f"`{fg}` {a}", f"`{bg}` {b}", f"{r:.2f} : 1",
                                 "yes" if r >= 4.5 else "large text only" if r >= 3 else "no"])
    out += ["### Contrast (computed)", "",
            "WCAG 2.x contrast ratio of each text and status colour on the page ground and on a panel. *AA, normal "
            "text* needs at least 4.5 : 1; 3 : 1 suffices for large text.", "",
            table(["Theme", "Text", "On", "Ratio", "AA, normal text"], rows), ""]

    # 4 · typography
    fonts_url = next((u for u in re.findall(r'href="([^"]+)"', html) if "fonts.googleapis.com/css" in u), "")
    families = [f.replace("+", " ") for f in parse_qs(urlparse(fonts_url).query).get("family", [])]
    out += ["## 5. Typography", "",
            table(["Token", "Stack"], [[f"`{n}`", v] for n, (v, _) in base.items() if n.startswith("--font-")]), "",
            "Loaded from Google Fonts in `web/index.html`: " + "; ".join(f"`{f}`" for f in families) + ". The classes "
            "`.display` and `.mono` apply the display and mono stacks; the sans stack is the body default.", ""]

    # 5 · shape, depth and motion
    skin_root = css_vars(css_block(skins, ":root"))
    keyframes = sorted(set(re.findall(r"@keyframes\s+([\w-]+)", css + skins)))
    reduced = len(re.findall(r"prefers-reduced-motion:\s*reduce", css + skins))
    out += ["## 6. Shape, depth and motion", "",
            f"Defaults in `{SKINS}` `:root` (any skin may override):", "",
            table(["Token", "Value", "Note"], [[f"`{n}`", f"`{v}`", c] for n, v, c in skin_root]), "",
            f"Animations (`@keyframes`): {', '.join(f'`{k}`' for k in keyframes)}. `prefers-reduced-motion: reduce` "
            f"is handled in {reduced} places.", ""]

    # 6 · shared components
    kit_rows = []
    for f in KIT:
        for e in exported_functions(read(f)):
            kit_rows.append([f"`{e['name']}`", f"`{f.rsplit('/', 1)[1]}`", ", ".join(e["params"]), e["comment"]])
    pressable = next(e for e in exported_functions(read("web/src/lib/pressable.ts")))
    toast = re.findall(r"^export (?:const|function|type|interface) (\w+)", read("web/src/lib/toast.ts"), re.M)
    n_components = len(list((ROOT / "web/src/components").rglob("*.tsx")))
    out += ["## 7. Shared components", "",
            f"The page kit and overlay primitives other screens build from ({n_components} component files are in "
            "`web/src/components/`; the ones below are the shared kit). *Notes* is the comment above each in the "
            "code.", "", table(["Component", "File", "Props", "Notes"], kit_rows), "",
            f"Helpers: `pressable` in `web/src/lib/pressable.ts` — “{prose(pressable['comment'])}”; `web/src/lib/toast.ts` "
            f"exports {', '.join(f'`{t}`' for t in toast)}.", ""]

    # 7 · global classes, 8 · libraries
    out += ["## 8. Global classes", "", f"Top-level class rules in `{CSS}` with the comment above each:", "",
            table(["Class", "Comment"], _class_rules(css)), "",
            "## 9. UI libraries", "", "From `web/package.json` (versions as declared; resolved versions are in "
            "[TECHNICAL_REQUIREMENTS.md](TECHNICAL_REQUIREMENTS.md) §3):", "",
            table(["Package", "Declared"], [[f"`{k}`", v] for k, v in sorted({**package["dependencies"],
                                                                                **package["devDependencies"]}.items())
                                             if k in ("tailwindcss", "@tailwindcss/vite", "lucide-react", "recharts",
                                                      "maplibre-gl", "leaflet", "react-leaflet", "@xyflow/react",
                                                      "framer-motion", "h3-js", "clsx")]), ""]
    return "\n".join(out).rstrip() + "\n"
