"""Every located asset of ONE organization, across all six sector tables, with its headline score at a horizon.

The sector modules each keep their own book (bank_assets, insurance_policies, assetmgmt_holdings,
realestate_properties, sc_company_sites, sc_sourcing_plots) and each has a physical-risk view. This is the one
cross-sector reader the regulator portal and the map layers use; it is org-type agnostic (a bank simply has empty
rows in the other five tables). Headline = max hazard score at (scenario, horizon), the same rule the sector pages use.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional

from sqlalchemy import text

from core.hazard_relevance import is_headline_eligible

# The four financial verticals live on the shared `entities` table and are read through the SAME portfolio engine
# the sector pages use (horizon interpolation, scenario-flat fallback, headline rule, buckets) — so a supervisor's
# number for an entity equals the number that entity sees on its own page.
_ENGINE_VERTICALS = {"banking": "financed asset", "insurance": "insured location", "assetmgmt": "holding", "realestate": "property"}

# Agriculture keeps its own tables (sites + sourcing plots) and physical-risk views.
_AGRI_SOURCES = [
    ("site", """        SELECT s.site_id AS id, s.name, s.latitude AS lat, s.longitude AS lon, s.country AS region,
               s.annual_value_eur AS value_eur, v.hazard_type AS hazard, v.physical_risk_score AS score, v.model_version
        FROM sc_company_sites s JOIN v_sc_site_physical_risk v ON v.site_id = s.site_id
        WHERE s.org_id = :o AND v.scenario = :sc AND v.time_horizon = :h"""),
    ("plot", """        SELECT p.plot_id AS id, COALESCE(p.plot_name, co.name) AS name, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.country, p.region) AS region, p.annual_spend_eur AS value_eur, v.hazard_type AS hazard,
               v.physical_risk_score AS score, v.model_version
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id
        WHERE p.org_id = :o AND v.scenario = :sc AND v.time_horizon = :h"""),
]


# Version-keyed memo: the population views (benchmark, analytics, evidence packs) read every entity's asset points
# on each request, and each read runs the engine over the whole book. The result changes only when the book or
# the standing scores change, so it is memoised on a data version — the newest score time plus the newest book
# row for the org — never on a clock. Bounded, process-local, thread-safe; a versioned key can never serve stale data.
_MEMO: "OrderedDict[tuple, list[dict]]" = OrderedDict()
_MEMO_LOCK = threading.Lock()
_MEMO_MAX = 512


def _data_version(session, org_id: str) -> tuple:
    """The newest current score on any of the org's cells, plus the org's book rows — an index probe per cell, and
    unaffected by scoring elsewhere on the platform."""
    return tuple(session.execute(text("""
        SELECT (SELECT max(cs.scored_at) FROM (
                    SELECT h3_cell FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND h3_cell IS NOT NULL
                    UNION SELECT h3_cell FROM sc_company_sites WHERE org_id = CAST(:o AS uuid)
                    UNION SELECT h3_cell FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid)) c
                JOIN LATERAL (SELECT scored_at FROM canonical_scores cs WHERE cs.h3_cell = c.h3_cell AND cs.valid_to IS NULL ORDER BY scored_at DESC LIMIT 1) cs ON TRUE),
               (SELECT count(*) || ':' || COALESCE(max(updated_at)::text, '') FROM portfolio_entities WHERE org_id = CAST(:o AS uuid)),
               (SELECT count(*) || ':' || COALESCE(max(created_at)::text, '') FROM sc_company_sites WHERE org_id = CAST(:o AS uuid)),
               (SELECT count(*) || ':' || COALESCE(max(created_at)::text, '') FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid))
    """), {"o": org_id}).first())


def org_asset_points(session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                     source: str = "own", subject_org_id: Optional[str] = None) -> list[dict]:
    """[{id, name, kind, lat, lon, region, value_eur, score, hazard}] — one row per asset of the org across every
    sector table; headline = the sector engine's headline (worst standing hazard over the scales that apply to the
    asset class, nowcasts excluded). Unlocated assets are included (lat/lon None) so value-based metrics match the
    entity's own book; maps skip them. Memoised on the data version (see _MEMO)."""
    key = (org_id, scenario, horizon, source, subject_org_id, _data_version(session, org_id))
    with _MEMO_LOCK:
        hit = _MEMO.get(key)
        if hit is not None:
            _MEMO.move_to_end(key)
            return [dict(r) for r in hit]
    rows = _org_asset_points(session, org_id, scenario, horizon, source, subject_org_id)
    with _MEMO_LOCK:
        _MEMO[key] = [dict(r) for r in rows]
        while len(_MEMO) > _MEMO_MAX:
            _MEMO.popitem(last=False)
    return rows


def _org_asset_points(session, org_id: str, scenario: str, horizon: str, source: str, subject_org_id: Optional[str]) -> list[dict]:
    from services.portfolio_engine import fetch_entities_with_risk
    out: list[dict] = []
    present = {r[0] for r in session.execute(text("""SELECT DISTINCT vertical FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND source = :src
                                                    AND (CAST(:subj AS uuid) IS NULL OR subject_org_id = CAST(:subj AS uuid))"""),
                                             {"o": org_id, "src": source, "subj": subject_org_id}).fetchall()}
    for vertical, label in _ENGINE_VERTICALS.items():
        if vertical not in present:      # an empty vertical is not queried: the engine run is per book, not per catalogue
            continue
        for r in fetch_entities_with_risk(session, org_id, vertical, scenario, horizon, source=source, subject_org_id=subject_org_id):
            out.append({"id": f"{vertical}:{r['entity_id']}", "name": r.get("entity_name") or r.get("name") or label, "kind": label,
                        "lat": (float(r["lat"]) if r.get("lat") is not None else None),
                        "lon": (float(r["lon"]) if r.get("lon") is not None else None),
                        "region": r.get("region") or r.get("country"),
                        "value_eur": float(r.get("primary_value_eur") or 0),
                        "score": (float(r["headline_score"]) if r.get("headline_score") is not None else None),
                        "hazard": r.get("headline_hazard"), "nace_code": r.get("nace_code"), "country": r.get("country"),
                        "external_ref": r.get("external_ref"), "region_name": r.get("region"),
                        "location_precision": r.get("location_precision") or ("point" if r.get("lat") is not None else "unlocated")})
    if source != "own":
        return out          # shadow books exist for the engine verticals only
    by_id: dict[str, dict] = {}
    agri_rows = [(kind, session.execute(text(sql), {"o": org_id, "sc": scenario, "h": horizon}).mappings().all())
                 for kind, sql in _AGRI_SOURCES]
    if not any(rows for _, rows in agri_rows) and (scenario, horizon) != ("baseline", "current"):
        # agri views carry anchor horizons only; a supervisor asking for an off-anchor basis gets today's standing
        # scores, labelled as such — never an empty book passed off as "no exposure"
        agri_rows = [(kind, session.execute(text(sql), {"o": org_id, "sc": "baseline", "h": "current"}).mappings().all())
                     for kind, sql in _AGRI_SOURCES]
        basis = "baseline/current (no scores at the requested basis)"
    else:
        basis = None
    for kind, rows in agri_rows:
        for r in rows:
            key = f"{kind}:{r['id']}"
            a = by_id.setdefault(key, {"id": key, "name": r["name"], "kind": kind,
                                       "lat": (float(r["lat"]) if r["lat"] is not None else None),
                                       "lon": (float(r["lon"]) if r["lon"] is not None else None),
                                       "region": r["region"], "value_eur": float(r["value_eur"] or 0), "score": None, "hazard": None,
                                       **({"basis_note": basis} if basis else {})})
            sc = float(r["score"]) if r["score"] is not None else None
            # an operational site is a built asset; a sourcing plot is agriculture — each reads its own relevance
            if not is_headline_eligible(r["hazard"], "agriculture" if kind == "plot" else "buildings", r["model_version"]):
                continue
            if sc is not None and (a["score"] is None or sc > a["score"]):
                a["score"], a["hazard"] = sc, r["hazard"]
    return out + list(by_id.values())
