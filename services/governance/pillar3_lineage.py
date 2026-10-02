"""Lineage of Pillar 3 Template 5 — each printed cell (row × column, per geography) traced to the exposures it sums,
from the frozen filing (E105).

A Pillar 3 filing (E97) freezes its banking book per exposure, the specification it was prepared under and the stated
at-risk level; its Template 5 is a pure function of the three (pillar3_grids.template5). So a cell is traced by
re-reading exactly that: the row's population (pillar3_grids.row_population, the filter the grid uses), the geography
(column a), and each exposure's contribution to the column (pillar3_grids.t5_contribution). The trace states the cell
as printed and the sum of its contributors, and they must agree (`ties`).

Each contributor carries the hazards that make it sensitive — every climate hazard at its location scoring at or
above the stated level, chronic or acute (pillar3_templates) — with the score frozen for it, the golden-source row
standing today for that cell and hazard (filing_lineage._granular_row; a newer model version is flagged as drift, never
hidden) and the feeds the hazard is derived from.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.governance.filings import get_filing
from services.governance.money_format import presentation_of

ALL = "ALL"
_NOT_SUMMED = ("a",)          # column a is the geography itself


def _frozen(session: Session, org_id: str, filing_id: str) -> tuple[dict, dict]:
    filing = get_filing(session, org_id, filing_id, with_payload=True)
    if not filing:
        raise ValueError("filing not found")
    return filing, (filing.get("snapshot") or {}).get("payload") or {}


def _unsupported(filing: dict, payload: dict) -> str | None:
    """Why this filing has no Template 5 trace (None when it has one)."""
    from services.governance.filing_annex import _p3_spec
    from services.governance.pillar3_report import is_earlier_shape
    from services.governance.pillar3_templates import stated_level
    if filing["framework"] != "bank_p3esg":
        return "Template 5 lineage is for Pillar 3 ESG filings."
    if is_earlier_shape(payload):
        return "A filing of the earlier report shape traces its hazard cells as frozen (by hazard)."
    if not payload.get("assets"):
        return "This filing froze no per-exposure book."
    if stated_level(payload) is None:
        return "Template 5 was not computed: the at-risk level (method.at_risk_level) was not stated when it was frozen."
    spec = _p3_spec(payload)
    if not spec or not any(t["id"] == "T5" for t in spec["templates"]):
        return "The version this filing was prepared under has no Template 5."
    return None


def t5_view(session: Session, org_id: str, filing_id: str) -> dict:
    """The frozen Template 5 grid — the trace's entry points: its rows, its summed columns, its geographies and every
    cell's printed value."""
    import services.regspec as R
    from services.governance.filing_annex import _p3_spec
    from services.governance.pillar3_grids import template5
    from services.governance.pillar3_templates import stated_level
    filing, payload = _frozen(session, org_id, filing_id)
    why = _unsupported(filing, payload)
    if why:
        return {"supported": False, "framework": filing["framework"], "message": why}
    spec, level = _p3_spec(payload), stated_level(payload)
    t = R.template(spec, "T5")
    g = template5(spec, payload["assets"], level)
    cells = {ALL: {r["id"]: r["values"] for r in g["rows"]},
             **{geo["geography"]: {r["id"]: r["values"] for r in geo["rows"]} for geo in g["geographies"]}}
    return {"supported": True, "filing_id": filing_id, "title": t["title"], "spec": spec["version"],
            "at_risk_level": level, "currency": presentation_of(payload),
            "rows": [{"id": r["id"], "label": r["label"]} for r in t["rows"]],
            "columns": [{"id": c["id"], "label": c["label"]} for c in t["columns"] if c["id"] not in _NOT_SUMMED],
            "geographies": [{"code": ALL, "label": "All geographies"}]
                           + [{"code": geo["geography"], "label": geo["label"]} for geo in g["geographies"]],
            "cells": cells}


def t5_cell_lineage(session: Session, org_id: str, filing_id: str, row: str, column: str, geography: str = ALL) -> dict:
    """FORWARD trace of one Template 5 cell: the exposures it sums, each with its contribution and the hazards that make
    it sensitive, down to the golden-source row and the source feeds."""
    import services.regspec as R
    from services.data.feeds import feeds_for_hazard
    from services.governance.filing_annex import _p3_spec
    from services.governance.filing_lineage import _granular_row
    from services.governance.pillar3_grids import (
        build,
        geographies,
        row_population,
        t5_contribution,
    )
    from services.governance.pillar3_templates import (
        ACUTE_HAZARDS,
        CHRONIC_HAZARDS,
        hazard_hit,
        stated_level,
    )
    filing, payload = _frozen(session, org_id, filing_id)
    why = _unsupported(filing, payload)
    if why:
        return {"supported": False, "message": why}
    spec, level, assets = _p3_spec(payload), stated_level(payload), payload["assets"]
    t = R.template(spec, "T5")
    col = next((c for c in t["columns"] if c["id"] == column), None)
    if col is None or column in _NOT_SUMMED:
        raise ValueError(f"Template 5 has no summed column '{column}'")
    if geography != ALL:
        geo = next((x for x in geographies(assets) if x[0] == geography), None)
        if geo is None:
            raise ValueError(f"'{geography}' is not a geography of this filing's Template 5")
        geo_label, scope = geo[1], geo[2]
    else:
        geo_label, scope = "All geographies", assets
    pop = row_population(spec, "T5", row, scope)          # raises for a row the template does not have
    printed = next(r for r in build(spec, "T5", scope, level)["rows"] if r["id"] == row)["values"].get(column)

    basis = (filing.get("snapshot") or {}).get("reporting_basis") or {}
    scenario, horizon = basis.get("scenario", "baseline"), basis.get("horizon", "current")
    contributors, hazards_seen = [], set()
    for a in pop:
        c = t5_contribution(a, column, level)
        if c is None:
            continue
        hits = []
        for h in a.get("hazards") or []:
            if not hazard_hit(h, level) or h.get("hazard") not in CHRONIC_HAZARDS | ACUTE_HAZARDS:
                continue
            hz = h["hazard"]
            hazards_seen.add(hz)
            gr = _granular_row(session, a.get("h3_cell"), hz, scenario, horizon) if a.get("h3_cell") else None
            filed_mv = h.get("model_version")
            hits.append({"hazard": hz, "category": "chronic" if hz in CHRONIC_HAZARDS else "acute",
                         "filed": {"score": h.get("score"), "bucket": h.get("bucket"), "model_version": filed_mv},
                         "granular": gr,
                         "drift": bool(gr and filed_mv and gr.get("model_version") and gr["model_version"] != filed_mv)})
        contributors.append({"asset_id": a.get("asset_id"), "asset_name": a.get("asset_name"), "country": a.get("country"),
                             "h3_cell": a.get("h3_cell"), "nace_code": a.get("nace_code"),
                             "gross_carrying_amount_eur": a.get("outstanding_loan_balance_eur"),
                             **c, "residual_maturity_years": a.get("residual_maturity_years"),
                             "ifrs9_stage": a.get("ifrs9_stage"), "hazards": hits})
    if column == "g":
        w = sum(x["weight"] for x in contributors)
        derived = round(sum(x["weight"] * x["maturity"] for x in contributors) / w, 1) if w else None
    else:
        derived = sum(x["amount"] for x in contributors) if contributors else 0.0
    contributors.sort(key=lambda x: -(x.get("amount") or x.get("weight") or 0))
    ties = (printed is None and not contributors) or (printed is not None and derived is not None
                                                      and abs(float(printed) - float(derived)) <= 0.5)
    return {"supported": True, "filing_id": filing_id, "template": "T5", "spec": spec["version"],
            "row": next({"id": r["id"], "label": r["label"]} for r in t["rows"] if r["id"] == row),
            "column": {"id": col["id"], "label": col["label"]}, "geography": {"code": geography, "label": geo_label},
            "at_risk_level": level, "currency": presentation_of(payload),
            "basis": {"scenario": scenario, "horizon": horizon},
            "cell": {"printed": printed, "from_contributors": derived, "ties": ties,
                     "kind": "weighted_average" if column == "g" else "sum"},
            "n_in_row": len(pop), "contributors": contributors,
            "drift_count": sum(1 for x in contributors for h in x["hazards"] if h["drift"]),
            "sources": {hz: feeds_for_hazard(session, hz) for hz in sorted(hazards_seen)}}
