"""SFDR pre-contractual disclosure — the actual document, ready to annex to a fund's prospectus.

Built directly against the OFFICIAL RTS Annex II/III template (Commission Delegated Regulation (EU)
2022/1288, fetched via scripts/fetch_eu_regulation.sh 32022R1288 — the template is embedded as scanned
images in the Official Journal document; read directly, not from a secondary summary), NOT against any one
fund's own prospectus layout or house style. That is the point: a fund's prospectus is the document THIS
annex gets attached to, not something this module reads or depends on — the same renderer works for every
fund, Article 8 or 9, because the RTS template itself is universal across the whole market. Swapping which
fund's data flows in never touches this file.

Faithful to the real template's own convention: the official form uses red italic bracketed instructions
("[complete]", "[include a description of...]") wherever a field is unfilled, and plain black text wherever
it's filled in. This renderer does exactly that — a `not_available`/`not_applicable` section prints its
`input_required` text in the same red-italic-bracket convention; a `declared`/`computed` section prints its
real value in plain text. Never a fabricated placeholder passed off as real data.
"""
from __future__ import annotations

from html import escape as _esc


def _render_any(v) -> str:
    """Recursively render a plain value / dict / list of the shapes build_precontractual() produces, so a
    nested structure (e.g. a dict whose value is itself a list of dicts) never falls through to a raw
    Python repr."""
    if v in (None, "", [], {}):
        return ""
    if isinstance(v, dict):
        parts = [f"<b>{_esc(str(k).replace('_', ' '))}:</b> "
                 + ("<br/>" if isinstance(x, list) else "") + _render_any(x)
                 for k, x in v.items() if x not in (None, "", [], {})]
        return "<br/>".join(parts)
    if isinstance(v, list):
        return "<br/>".join(_render_any(x) for x in v if x not in (None, "", [], {}))
    return _esc(str(v))


def _val_html(section: dict) -> str:
    """Render one section's value the way the official form does: filled in plain text, or the red italic
    '[complete: ...]' instruction the real template prints for an unanswered field."""
    status = section["status"]
    value = section["value"]
    if status in ("declared", "computed") and value not in (None, "", [], {}):
        rendered = _render_any(value)
        return rendered if rendered else _placeholder(section)
    if status == "not_applicable":
        return f'<span class="np">{_esc(str(value)) if value else "Not applicable to this product."}</span>'
    return _placeholder(section)


def _placeholder(section: dict) -> str:
    req = section.get("input_required") or "to be completed by the manager"
    return f'<span class="ph">[complete: {_esc(req)}]</span>'


_CSS = """
@page { size: A4; margin: 20mm 16mm; }
body { font-family: 'Calibri', Arial, sans-serif; font-size: 10.5pt; color: #1a1a1a; line-height: 1.4; }
h1 { font-size: 13pt; text-align: center; color: #1a5632; margin: 0 0 4mm; }
h2 { font-size: 11.5pt; color: #1a5632; border-bottom: 1px solid #1a5632; padding-bottom: 2px; margin-top: 8mm; }
.hdr { display: flex; justify-content: space-between; font-weight: 600; margin-bottom: 4mm; }
.tickbox { background: #fbe8d3; border: 1px solid #e0c9a6; padding: 3mm 4mm; margin: 3mm 0; }
.tickbox .yn { font-weight: 700; }
table.dnsh { background: #fbe8d3; border: 1px solid #e0c9a6; padding: 3mm; margin: 3mm 0; width: 100%; border-collapse: collapse; }
table.dnsh td { padding: 2mm; }
.q { font-weight: 600; margin-top: 5mm; }
.a { margin: 1.5mm 0 0 4mm; }
.ph { color: #b23b3b; font-style: italic; }
.np { color: #6b6b6b; font-style: italic; }
.note { color: #6b6b6b; font-size: 8.5pt; margin-top: 1mm; margin-left: 4mm; }
.foot { margin-top: 10mm; font-size: 8pt; color: #6b6b6b; border-top: 1px solid #ccc; padding-top: 2mm; }
"""


def precontractual_annex_html(built: dict) -> str:
    """Render build_precontractual()'s output as the actual Annex II/III document — same renderer for
    every fund and every manager; nothing here is specific to any one fund's own prospectus design."""
    if built.get("error"):
        return f"<html><body><p>{_esc(built['error'])}</p></body></html>"

    entity = built["entity"]
    is_art9 = entity["sfdr_classification"] == "article_9"
    title = "Annex III" if is_art9 else "Annex II"
    headline = "Sustainable investment objective" if is_art9 else "Environmental and/or social characteristics"
    sections = built["sections"]
    by_field = {s["field"]: s for s in sections}

    # The Yes/No tick-box at the top of the real template — derived from the same data the JSON sections
    # already carry (the "Does this financial product have a sustainable investment objective?" section).
    tick = by_field.get("Does this financial product have a sustainable investment objective?")
    tick_html = _esc(tick["value"]) if tick and tick["value"] else "[tick and fill in as relevant]"

    rows = []
    seen = {"Product name", "Legal entity identifier",
            "Does this financial product have a sustainable investment objective?"}
    for s in sections:
        if s["field"] in seen:
            continue
        seen.add(s["field"])
        rows.append(f'''
        <div class="q">{_esc(s["field"])}</div>
        <div class="a">{_val_html(s)}</div>
        {f'<div class="note">{_esc(s["note"])}</div>' if s.get("note") else ""}''')

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>{_esc(title)} — {_esc(entity['fund_name'])}</title>
<style>{_CSS}</style></head>
<body>
<h1>{_esc(title)} — Template pre-contractual disclosure<br/>
<span style="font-size:9.5pt;font-weight:400">{_esc(built['regulatory_basis'])}</span></h1>
<div class="hdr">
  <div>Product name: {_esc(entity['fund_name'])}</div>
  <div>Legal entity identifier: {_esc(entity.get('fund_lei') or '[complete]')}</div>
</div>
<h2>{_esc(headline)}</h2>
<div class="tickbox">
  <div class="yn">Does this financial product have a sustainable investment objective?</div>
  <div>{tick_html}</div>
</div>
{"".join(rows)}
<div class="foot">
  Manager: {_esc(entity['manager'])} ({_esc(entity.get('manager_lei') or 'LEI not set')}) ·
  Generated {_esc(built['provenance']['generated_at'])} by Tellumen from {built['coverage_summary']['fields']} template
  fields ({built['coverage_summary']['computed']} computed, {built['coverage_summary']['declared']} declared by the
  manager, {built['coverage_summary']['not_available']} still required) · Rendered against the official RTS
  Annex II/III template structure (Commission Delegated Regulation (EU) 2022/1288) — not a prospectus-specific
  layout. Fields shown in red brackets are not yet declared and must be completed before this is annexed to the
  prospectus.
</div>
</body></html>"""
