"""Protected-area overlap — ESRS E4 biodiversity: which of an org's own sites and sourcing plots sit in (or
within the loaded buffer of) a Natura 2000 protected area. Answered by a simple indexed membership test of
each asset's H3 cell against the precomputed `protected_h3_cell` lookup (built offline from the EEA GeoPackage
by scripts/ingest_natura2000.py) — no PostGIS at runtime. Free-gov data, computed by Tellumen.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def protected_area_exposure(session: Session, org_id: str) -> dict:
    """Sites/plots in or near a protected area — across EVERY loaded dataset (Natura 2000 EU · WDPA global ·
    WD-OECM · KBA). EXISTS de-dups an asset that falls in more than one dataset's cells, so counts never
    double. As new datasets land, non-EU assets light up automatically — no code change."""
    sites = session.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM protected_h3_cell pc WHERE pc.h3_cell = s.h3_cell)) AS in_protected,
               COALESCE(SUM(s.annual_value_eur) FILTER (WHERE EXISTS (SELECT 1 FROM protected_h3_cell pc WHERE pc.h3_cell = s.h3_cell)), 0) AS value_in
        FROM sc_company_sites s WHERE s.org_id = :o
    """), {"o": org_id}).mappings().first()
    plots = session.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM protected_h3_cell pc WHERE pc.h3_cell = p.h3_cell)) AS in_protected,
               COALESCE(SUM(p.annual_spend_eur) FILTER (WHERE EXISTS (SELECT 1 FROM protected_h3_cell pc WHERE pc.h3_cell = p.h3_cell)), 0) AS spend_in
        FROM sc_sourcing_plots p WHERE p.org_id = :o
    """), {"o": org_id}).mappings().first()
    ds = session.execute(text("SELECT dataset, COUNT(*) n FROM protected_h3_cell GROUP BY dataset")).mappings().all()
    return {
        "datasets": {d["dataset"]: int(d["n"]) for d in ds}, "cells_loaded": sum(int(d["n"]) for d in ds),
        "sites": {"total": int(sites["total"]), "in_protected": int(sites["in_protected"]),
                  "value_in_eur": float(sites["value_in"])},
        "plots": {"total": int(plots["total"]), "in_protected": int(plots["in_protected"]),
                  "spend_in_eur": float(plots["spend_in"])},
    }
