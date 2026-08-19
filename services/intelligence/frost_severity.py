"""Regional frost-severity indicator — a SEPARATE frost hazard signal for the KRI layer.

Reads the precomputed climatology (scripts/build_frost_severity.py → data/frost_severity/<region>.json)
and surfaces it for an org's frost-exposed sourcing regions. Deliberately standalone: it is a regional
HAZARD-severity number (what fraction of the belt froze), NOT the per-plot score and NOT a calibrated
euro — the coffee € stays held. Only orgs that actually source the region's commodity/country see it.
"""
from __future__ import annotations

import json
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

_DIR = "data/frost_severity"
_REGIONS = ("brazil_coffee",)   # regions with a computed frost-severity climatology


def _load(region_key: str) -> dict | None:
    path = os.path.join(_DIR, f"{region_key}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def org_frost_severity(session: Session, org_id: str) -> list[dict]:
    """Frost-severity records for the frost-exposed regions THIS org actually sources from.

    Empty when the org sources nothing from a region we hold frost data for — the indicator is
    shown only where it is real, never fabricated as N/A noise elsewhere."""
    out: list[dict] = []
    for region_key in _REGIONS:
        rec = _load(region_key)
        if not rec:
            continue
        n = session.execute(text(
            "SELECT count(*) FROM sc_sourcing_plots p JOIN sc_commodities c ON c.commodity_id = p.commodity_id "
            "WHERE p.org_id = CAST(:o AS uuid) AND c.name = :cm AND p.country = :ct"),
            {"o": org_id, "cm": rec["commodity"], "ct": rec["country"]}).scalar()
        if n and n > 0:
            out.append(rec)
    return out
