"""CRCS · per-org change impact — for a regulatory change, what it means for THIS client.

Two customer-facing dimensions (never Tellumen's internal effort): the DEADLINE (days until it takes effect,
banded by urgency) and the SCOPE (how many of the client's own records fall under the affected framework). Read
live from the client's book. Combined with the field-level data-readiness, this is the "what does this change
mean for me, and how ready am I" pillar of the Continuous Regulatory Compliance System.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


def _scope(session: Session, org_id: str, framework: str | None) -> dict | None:
    """How many of the client's own records fall under the framework the change touches."""
    if not framework:
        return None
    try:
        if framework == "eudr_dds":
            n = session.execute(text("""
                SELECT count(*) FROM sc_sourcing_plots p
                JOIN sc_commodities c ON c.commodity_id = p.commodity_id AND c.eudr_covered
                WHERE p.org_id = :o"""), {"o": org_id}).scalar()
            return {"n": int(n or 0), "label": "EUDR-covered plots"}
        if framework in ("csrd_e1", "esrs_pack"):
            sites = session.execute(text("SELECT count(*) FROM sc_company_sites WHERE org_id=:o"), {"o": org_id}).scalar()
            plots = session.execute(text("SELECT count(*) FROM sc_sourcing_plots WHERE org_id=:o"), {"o": org_id}).scalar()
            return {"n": int(sites or 0) + int(plots or 0), "label": "sites & sourcing plots"}
        if framework in ("bank_p3esg", "bank_tcfd", "sfdr_pai", "assetmgmt_tcfd", "reit_tcfd", "insurer_climate"):
            n = session.execute(text("SELECT count(*) FROM portfolio_entities WHERE org_id=:o"), {"o": org_id}).scalar()
            return {"n": int(n or 0), "label": "exposures / holdings"}
    except Exception:
        return None
    return None


def change_impact(session: Session, org_id: str, framework: str | None, effective_date: str | None) -> dict | None:
    """Deadline urgency + record scope for one change, from the client's own data."""
    out: dict = {}
    if effective_date:
        try:
            days = (date.fromisoformat(effective_date) - date.today()).days
            # a past effective date means the rule is already IN FORCE — not a missed deadline
            band = "in_force" if days < 0 else "critical" if days <= 90 else "soon" if days <= 365 else "planned"
            out["deadline"] = {"date": effective_date, "days": days, "band": band}
        except Exception:
            pass
    sc = _scope(session, org_id, framework)
    if sc:
        out["scope"] = sc
    return out or None
