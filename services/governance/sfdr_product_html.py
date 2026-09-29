"""A fund's SFDR template as the document annexed to its prospectus (Annex II / III) or annual report (Annex IV / V):
every printed item in the template's order, answered — rendered to self-contained HTML from the built items
(services.governance.sfdr_product.build). The red instructions are for the preparer and are not printed; an item
without an answer is marked, so a draft can never pass for a finished document.
"""
from __future__ import annotations

import re
from html import escape

_BLANK = re.compile(r"_{2,}\s*%?")
_PLACE = re.compile(r"\bx%", re.I)
_CSS = """body{font-family:Calibri,Arial,sans-serif;max-width:860px;margin:32px auto;color:#1d2a24;line-height:1.45}
h1{font-size:22px;color:#2f7d57}h2{font-size:17px;color:#2f7d57;margin-top:26px}.q{font-weight:700;margin-top:14px}
.a{margin:4px 0 0 16px}.c{margin:3px 0 0 16px}.def{font-size:12px;color:#51605a;border-left:3px solid #cfe3d8;padding:4px 10px;margin:8px 0}
.miss{color:#b3261e;font-style:italic}table{border-collapse:collapse;margin:8px 0}td,th{border:1px solid #cfd8d3;padding:4px 8px;font-size:13px}
.meta{font-size:12px;color:#51605a}"""


def _fill(label: str, v) -> str:
    """The printed label with its blank completed ('___%' → '12.5%')."""
    if isinstance(v, dict) and v.get("percent") is not None:
        return _BLANK.sub(f"{v['percent']:g}%", label, count=1)
    if isinstance(v, dict) and v.get("text"):
        return _BLANK.sub(escape(v["text"]), label, count=1)
    return label


def _chart(i: dict, items: list[dict]) -> str:
    v = i.get("value") or {}
    labels = {c["id"]: c["label"] for c in items if c.get("parent") == i["id"]}
    if "graph" in v:                                  # computed Taxonomy graphs (periodic): one row per KPI basis
        rows = "".join(f"<tr><td>{b}</td><td>{g['fossil_gas'] if g['fossil_gas'] is not None else '—'}%</td>"
                       f"<td>{g['nuclear'] if g['nuclear'] is not None else '—'}%</td>"
                       f"<td>{g['aligned_other'] if g['aligned_other'] is not None else '—'}%</td>"
                       f"<td>{g['not_aligned'] if g['not_aligned'] is not None else '—'}%</td></tr>"
                       for b, g in v["graph"].items())
        share = f"<p class='meta'>This graph represents {v['share_of_total']}% of the total investments.</p>" if v.get("share_of_total") is not None else ""
        return (f"<p class='q'>{escape(i['label'])}</p><table><tr><th></th><th>Taxonomy-aligned: Fossil gas</th>"
                f"<th>Taxonomy-aligned: Nuclear</th><th>Taxonomy-aligned (no gas and nuclear)</th><th>Non Taxonomy-aligned</th></tr>"
                f"{rows}</table>{share}")
    if "values" in v:
        return (f"<p class='q'>{escape(i['label'] or 'Asset allocation')}</p><ul>"
                + "".join(f"<li>{escape(labels.get(k, k))}: {n:g}%</li>" for k, n in v["values"].items()) + "</ul>")
    return f"<p class='q'>{escape(i['label'] or 'Chart')}</p><p class='a miss'>[not yet answered]</p>"


def render(title: str, citation: str, fund: dict, items: list[dict], period: str | None = None) -> str:
    out = [f"<!doctype html><html><head><meta charset='utf-8'><title>{escape(fund['name'])} — {escape(title[:80])}</title>"
           f"<style>{_CSS}</style></head><body>", f"<p class='meta'>{escape(title)}<br>{escape(citation)}"
           + (f"<br>Reference period ending {escape(period)}" if period else "") + "</p>"]
    for i in items:
        k, v, lbl = i["kind"], i.get("value"), i.get("label") or ""
        miss = i.get("status") == "missing"
        if k == "heading":
            out.append(f"<h2>{escape(lbl)}</h2>")
        elif k == "field":
            out.append(f"<p><b>{escape(lbl)}</b> " + (escape(v["text"]) if v and v.get("text") else "<span class='miss'>[not yet answered]</span>") + "</p>")
        elif k == "question":
            out.append(f"<p class='q'>{escape(lbl)}</p>")
            if v and v.get("text"):
                out.append(f"<p class='a'>{escape(v['text'])}</p>")
            elif isinstance(v, dict) and v.get("percent") is not None:
                out.append(f"<p class='a'>{v['percent']:g}%</p>")
            elif isinstance(v, dict) and "sectors" in v:
                out.append("<ul class='a'>" + "".join(f"<li>{escape(s['sector'])}: {s['pct']}%</li>" for s in v["sectors"]) + "</ul>"
                           + (f"<p class='a'>Investments in the fossil fuel sector: {v['fossil_fuel_pct']}%</p>" if v.get("fossil_fuel_pct") is not None else ""))
            elif miss:
                out.append("<p class='a miss'>[not yet answered]</p>")
        elif k == "choice":
            ticked = bool(v and v.get("ticked"))
            out.append(f"<p class='c'>{'☒' if ticked else '☐'} {_fill(escape(lbl), v)}</p>")
        elif k == "chart":
            out.append(_chart(i, items))
        elif k == "table":
            cols = [c for c in items if c.get("parent") == i["id"] and c["kind"] == "table_column"]
            rows = (v or {}).get("rows") or []
            out.append("<table><tr>" + "".join(f"<th>{escape(c['label'])}</th>" for c in cols) + "</tr>"
                       + "".join("<tr>" + "".join(f"<td>{escape(str(r.get(c['id']) if r.get(c['id']) is not None else ''))}</td>"
                                                   for c in cols) + "</tr>" for r in rows) + "</table>")
        elif k == "definition":
            out.append(f"<div class='def'>{escape(lbl)}</div>")
        elif k == "text" and lbl:
            chart = next((c for c in items if c["id"] == i.get("parent") and c["kind"] == "chart"), None)
            if chart and chart.get("value") and _PLACE.search(lbl):
                continue                              # a print mark its chart fills ('This graph represents x% …')
            out.append(f"<p>{escape(lbl)}</p>")
    out.append("</body></html>")
    return "\n".join(out)
