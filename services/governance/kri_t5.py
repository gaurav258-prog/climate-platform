"""Pillar 3 Template 5 KRIs, one per printed row and column (E98).

Template 5 prints physical-risk exposure per NACE sector / collateral row and per geography, on the gross carrying
amount, and no book total — so the book-level physical-risk KRIs are live only (kri_bank). These KRIs carry what the
template does print: per row of the whole-book instance (the annex's 'All geographies' section), the gross carrying
amount of the exposures sensitive to chronic events only (column h), to acute events only (column i) and to both
(column j). Each is read the same way live and filed:

  filed   the Template 5 grid of each bank_p3esg filing, rebuilt from what it froze — its per-exposure book, the
          specification it was prepared under, its stated at-risk level (filing_annex renders the same grid)
  live    the same grid over today's book, on the version governing the reporting period and today's stated level

Key 't5.<row id>.<column>'. A filed figure counts for a KRI only where the filing's row carries the same label as the
live row (a version that renumbers rows does not mix them), and only for a filing presented in the currency the live
book is in (EUR) — figures in two currencies are not one trend. The KRIs carry group 't5_row' and their row, so the
page shows them in a row picker rather than as 39 tiles.
"""
from __future__ import annotations

GROUP = "t5_row"
COLUMNS = (("h", "chronic only"), ("i", "acute only"), ("j", "chronic and acute"))
_BOOK_CCY = "EUR"


def key(row_id: str, col: str) -> str:
    return f"t5.{row_id}.{col}"


def grid(payload: dict | None, spec: dict | None = None) -> dict | None:
    """The whole-book Template 5 instance a payload yields — the 'All geographies' section of its annex. None where the
    spec has no Template 5, the payload froze no per-exposure book, or the at-risk level is not stated."""
    from services.governance.filing_annex import _p3_spec
    from services.governance.pillar3_grids import build
    from services.governance.pillar3_templates import stated_level
    p = payload or {}
    spec = spec or _p3_spec(p)
    assets, level = p.get("assets") or [], stated_level(p)
    if not spec or not assets or level is None or not any(t["id"] == "T5" for t in spec["templates"]):
        return None
    return build(spec, "T5", assets, level)


def _rows(spec: dict | None) -> list[dict]:
    t5 = next((t for t in (spec or {}).get("templates") or [] if t["id"] == "T5"), None)
    return t5["rows"] if t5 else []


def _value(g: dict | None, row_id: str, col: str):
    row = next((r for r in (g or {}).get("rows") or [] if r["id"] == row_id), None)
    v = None if row is None else (row.get("values") or {}).get(col)
    return None if v is None else round(v)


def kpis(spec: dict | None, live: dict | None, gap: str | None) -> list[dict]:
    """A KRI per row and column of the governing version's Template 5, valued on today's book."""
    from services.governance.kri import _kpi
    out = []
    for r in _rows(spec):
        for col, what in COLUMNS:
            k = _kpi(key(r["id"], col), f"{r['label']} — sensitive, {what}", _value(live, r["id"], col), "eur",
                     tone="#fb7185",
                     hint=(f"Template 5, row {r['id']}, column {col}: gross carrying amount of the row's exposures sensitive to "
                           f"{what.replace('only', 'events only').replace('chronic and acute', 'both chronic and acute events')} "
                           "at or above your stated at-risk level — all geographies, over today's book"
                           + (f" · {gap}" if gap else "")))
            k.update(group=GROUP, row={"id": r["id"], "label": r["label"]}, column=col,
                     filed_basis=f"Pillar 3 ESG filing — Template 5, row {r['id']} ({r['label']}), column {col}, all geographies",
                     live_only=False, reg=f"Template 5, row {r['id']}, column {col} — sensitive, {what}", reg_tier="support")
            out.append(k)
    return out


def figures(payload: dict, live_spec: dict | None) -> list[dict]:
    """A filing's printed Template 5 cells, for the KRIs whose live row they are (same row id and label)."""
    from services.governance.filing_annex import _p3_spec
    from services.governance.money_format import presentation_of
    if presentation_of(payload) != _BOOK_CCY:
        return []
    spec = _p3_spec(payload)
    g = grid(payload, spec)
    if g is None:
        return []
    live = {r["id"]: r["label"] for r in _rows(live_spec)}
    return [{"key": key(r["id"], col), "label": f"{r['label']} — {what}", "fmt": "eur", "group": GROUP,
             "value": _value(g, r["id"], col)}
            for r in _rows(spec) if live.get(r["id"]) == r["label"] for col, what in COLUMNS]
