"""Protected-area overlap — ESRS E4 biodiversity: which of an org's own sites and sourcing plots sit in (or
within the loaded buffer of) a Natura 2000 protected area. Answered by a simple indexed membership test of
each asset's H3 cell against the precomputed `protected_h3_cell` lookup (built offline from the EEA GeoPackage
by scripts/ingest_natura2000.py) — no PostGIS at runtime. Free-gov data, computed by Tellumen.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def protected_area_exposure(session: Session, org_id: str, dataset: str = "natura2000") -> dict:
    sites = session.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE pc.h3_cell IS NOT NULL) AS in_protected,
               COALESCE(SUM(s.annual_value_eur) FILTER (WHERE pc.h3_cell IS NOT NULL), 0) AS value_in
        FROM sc_company_sites s
        LEFT JOIN protected_h3_cell pc ON pc.h3_cell = s.h3_cell AND pc.dataset = :d
        WHERE s.org_id = :o
    """), {"o": org_id, "d": dataset}).mappings().first()
    plots = session.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE pc.h3_cell IS NOT NULL) AS in_protected,
               COALESCE(SUM(p.annual_spend_eur) FILTER (WHERE pc.h3_cell IS NOT NULL), 0) AS spend_in
        FROM sc_sourcing_plots p
        LEFT JOIN protected_h3_cell pc ON pc.h3_cell = p.h3_cell AND pc.dataset = :d
        WHERE p.org_id = :o
    """), {"o": org_id, "d": dataset}).mappings().first()
    loaded = session.execute(text("SELECT COUNT(*) FROM protected_h3_cell WHERE dataset = :d"),
                             {"d": dataset}).scalar() or 0
    return {
        "dataset": dataset, "cells_loaded": int(loaded),
        "sites": {"total": int(sites["total"]), "in_protected": int(sites["in_protected"]),
                  "value_in_eur": float(sites["value_in"])},
        "plots": {"total": int(plots["total"]), "in_protected": int(plots["in_protected"]),
                  "spend_in_eur": float(plots["spend_in"])},
    }
