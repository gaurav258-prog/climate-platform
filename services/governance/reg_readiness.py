"""Data-readiness — for each field an upcoming change will require, do we already hold it in the client's book?

Turns the abstract "data to provide" checklist into a live gap report: for every field with a known checker,
run a real query over the client's own data and report have / partial / needed. Fields we don't yet track are
honestly 'needed' (you'll supply them) — never guessed as held. Sector-scoped; unknown keys default to needed.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def _plot_cov(session: Session, org_id: str, cond: str) -> tuple[int, int]:
    r = session.execute(text(f"""
        SELECT count(*) AS t, count(*) FILTER (WHERE {cond}) AS h
        FROM sc_sourcing_plots WHERE org_id = :o
    """), {"o": org_id}).mappings().first()
    return int(r["h"] or 0), int(r["t"] or 0)


def _commodity_hs(session: Session, org_id: str) -> tuple[int, int]:
    # commodities this org actually sources (via its plots) that are EUDR-covered, with an HS code on file
    r = session.execute(text("""
        SELECT count(*) AS t, count(*) FILTER (WHERE co.hs_code IS NOT NULL AND co.hs_code <> '') AS h
        FROM (SELECT DISTINCT commodity_id FROM sc_sourcing_plots WHERE org_id = :o) p
        JOIN sc_commodities co ON co.commodity_id = p.commodity_id AND co.eudr_covered
    """), {"o": org_id}).mappings().first()
    return int(r["h"] or 0), int(r["t"] or 0)


# field key -> a checker returning (held, total) over the client's own data. Keys with no checker are 'needed'.
_CHECKERS = {
    "eudr_geoloc": lambda s, o: _plot_cov(s, o, "plot_geometry IS NOT NULL OR (latitude IS NOT NULL AND longitude IS NOT NULL)"),
    "eudr_country": lambda s, o: _plot_cov(s, o, "country IS NOT NULL AND country <> ''"),
    "eudr_legality": lambda s, o: _plot_cov(s, o, "eudr_evidence IS NOT NULL"),
    "eudr_supplier": lambda s, o: _plot_cov(s, o, "supplier_id IS NOT NULL"),
    "eudr_commodity_hs": _commodity_hs,
}


def field_readiness(session: Session, org_id: str, key: str | None) -> dict:
    """{status: have|partial|needed, detail: 'h/t' or None} for one required field, from the client's own data."""
    checker = _CHECKERS.get(key or "")
    if checker is None:
        return {"status": "needed", "detail": None}
    try:
        held, total = checker(session, org_id)
    except Exception:
        return {"status": "needed", "detail": None}
    if total == 0:
        return {"status": "needed", "detail": "none on file"}
    if held >= total:
        return {"status": "have", "detail": f"{held}/{total}"}
    if held > 0:
        return {"status": "partial", "detail": f"{held}/{total}"}
    return {"status": "needed", "detail": f"0/{total}"}
