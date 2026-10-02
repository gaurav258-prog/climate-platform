"""Bidirectional data lineage — from a reported filing cell all the way down to the satellite/agency feed,
and back up from a granular golden-source cell to every filing that reuses it.

Almost nobody in physical-climate RegTech can show a filed number's line all the way back to the source and
forward to every reuse. This makes that line explicit, over the SAME frozen snapshot the filing was built on.

FORWARD  (a reported cell → its provenance):
    filing cell (e.g. "Flood: €324m exposed")
      → the assets that contribute it (from the frozen snapshot)
        → each asset's H3 cell
          → the canonical_scores row backing it (risk_score, model_version, data_vintage, fingerprint, CI, SHAP)
            → the source feed(s) that hazard is derived from (Copernicus/NASA/USGS…) + their live freshness

REVERSE  (a granular cell → everything that reuses it):
    an H3 cell → every located holding of this org sitting on it (across verticals)
      → the framework each feeds → the live filing that consumes it

The chain pivots on `h3_cell`; there is no score→asset or score→feed FK, so the score→source hop uses the
hazard→feed registry (services.data.feeds.HAZARD_FEEDS). Honesty: a hop is shown only where it really exists —
a missing golden-source row is `null`, never invented; a model-version drift between the filed number and the
current golden source is surfaced, not hidden.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.data.feeds import feeds_for_hazard
from services.governance.filings import get_filing
from services.governance.money_format import presentation_of

# vertical → the live framework whose filing prints that vertical's hazard cells (banking: Pillar 3 ESG Template 5 — the
# EU Taxonomy Art. 8 report prints none, E95)
_VERTICAL_FRAMEWORK = {"banking": "bank_p3esg", "assetmgmt": "sfdr_pai",
                       "realestate": "reit_taxonomy", "insurance": "insurer_solvency"}

# spatial-lineage config per framework: the entity list in the frozen payload + its id/name/value keys (the retired
# reit_tcfd / insurer_climate / assetmgmt_tcfd stay, so their filings remain traceable as frozen).
# Every located book (bank/reit/insurer) shares the same {h3_cell, hazards[]} entity shape, so one trace
# serves them all — including the two KPI-derived reports (reit_taxonomy/insurer_solvency), which carry the
# same shape alongside their own calc. SFDR/agri hold issuers/plots, not geolocated assets, so they use a
# genuinely different (not missing) lineage mechanism — see _ALT_LINEAGE below.
_LIST_CFG = {
    "bank_tcfd":       {"list": "assets",     "id": "asset_id",    "name": "asset_name",    "value": "value_eur"},
    "bank_p3esg":      {"list": "assets",     "id": "asset_id",    "name": "asset_name",    "value": "value_eur"},
    "reit_tcfd":       {"list": "properties", "id": "property_id", "name": "property_name", "value": "property_value_eur"},
    "insurer_climate": {"list": "policies",   "id": "policy_id",   "name": "policy_name",   "value": "sum_insured_eur"},
    # Found while extending lineage coverage (2026-09-23): assetmgmt_tcfd's frozen snapshot carries the same
    # {h3_cell, hazards[]} per-holding shape as the other located books — it had simply never been added.
    "assetmgmt_tcfd":  {"list": "holdings",   "id": "holding_id",  "name": "holding_name",  "value": "position_value_eur"},
    # Fixed foundationally 2026-09-23 (see report_snapshots._reit_taxonomy/_insurer_solvency): these two now
    # carry the full per-asset list + by_hazard alongside their KPI calc, so they trace directly — no longer
    # routed through the sibling-filing workaround in _ALT_LINEAGE below.
    "reit_taxonomy":    {"list": "properties", "id": "property_id", "name": "property_name", "value": "property_value_eur"},
    "insurer_solvency": {"list": "policies",   "id": "policy_id",   "name": "policy_name",   "value": "sum_insured_eur"},
    "insurer_orsa_climate": {"list": "policies", "id": "policy_id", "name": "policy_name", "value": "sum_insured_eur"},
    "insurer_recovery_stress": {"list": "policies", "id": "policy_id", "name": "policy_name", "value": "sum_insured_eur"},
}

# The frameworks NOT in _LIST_CFG genuinely have a DIFFERENT, real lineage mechanism rather than none —
# checked directly (2026-09-23, an independent architecture review had flagged this as unverified, not
# confirmed either way) rather than assumed:
#   - sfdr_pai (asset manager): per-issuer drill-down, GET /v1/issuers/{issuer_id} — "full facility
#     footprint + physical + transition detail" for any holding.
#   - esrs_pack: per site, in the frozen statement itself.
#   - csrd_e1 (retired): per-plot drill-down, GET /v1/supply/plot/{plot_id} — "projection +
#     provenance" for any sourcing plot; own-site lineage is the E1 report's own material-hazard rows.
# (reit_taxonomy / insurer_solvency used to be routed through a "trace the sibling filing" workaround here —
# fixed foundationally instead: they're in _LIST_CFG above now, since the data they need was always computed,
# just discarded before freezing. See report_snapshots._reit_taxonomy/_insurer_solvency.)
# a report traced spatially only in the filings that froze hazard cells — its current shape prints none (E95, E97)
_NO_HAZARD_CELLS = {
    "bank_tcfd": "Per exposure: the frozen loan book lists every exposure with the facts the EU Taxonomy Art. 8 templates "
                 "read (counterparty, instrument, Taxonomy status, objective, gross carrying amount); the templates print "
                 "no hazard cell, so there is no spatial trace. (A filing of the earlier report shape traces its hazard "
                 "cells as frozen.)",
    "bank_p3esg": "Template 5 prints the gross carrying amount sensitive to chronic / acute events per sector and "
                  "geography row, not a value per hazard: trace a Template 5 cell (row × column × geography) to the "
                  "exposures it sums and the hazards that make them sensitive — GET /v1/filings/{filing_id}/lineage/t5 "
                  "(E105). (A filing of the earlier report shape traces its hazard cells as frozen.)",
}
_ALT_LINEAGE = {
    "sfdr_pai": "Per-issuer drill-down: GET /v1/issuers/{issuer_id} (full facility footprint + physical + "
                "transition detail for any holding) — not a spatial cell trace, since funds hold issuers, "
                "not geolocated assets.",
    "csrd_e1": "Per-plot drill-down: GET /v1/supply/plot/{plot_id} (projection + provenance) for upstream "
               "sourcing; own-site exposure is in this filing's own material-hazard rows directly.",
    "esrs_pack": "Per site: the frozen statement lists every site in scope with its weight, carrying amount and "
                 "net revenue, and per horizon its hazards, materiality, water-stress and sensitive-area readings; "
                 "each figure names its concept and lane (computed / stated / derived).",
    "sfdr_precontractual": "Item by item: every item of the frozen template carries its source (computed from the "
                           "fund / the manager's answer / printed wording); per holding, GET /v1/issuers/{issuer_id}.",
    "sfdr_periodic": "Item by item: every item of the frozen template carries its source; the frozen holdings (each "
                     "position date of the reference period, with the investee's own Taxonomy KPIs) are in the "
                     "filing; per holding, GET /v1/issuers/{issuer_id}.",
    "eudr_dds": "Per shipment: the frozen statement holds its plots (geolocation, country, the satellite reading of "
                "each), the supplier, the legality evidence and the risk assessment it was prepared from; per plot, "
                "GET /v1/supply/plot/{plot_id}; the shipment, GET /v1/eudr/movements/{movement_id}/statement.",
}


def _granular_row(session: Session, h3_cell: str, hazard: str, scenario: str, horizon: str) -> dict | None:
    """The current standing golden-source row backing a (cell, hazard) at the filing's basis."""
    r = session.execute(text("""
        SELECT risk_score, risk_bucket, model_version, model_id::text AS model_id, data_vintage, scored_at,
               regulatory_fingerprint, score_ci_lower, score_ci_upper, shap_factors, score_lane
        FROM canonical_scores
        WHERE h3_cell = :c AND hazard_type = :h AND scenario = :sc AND time_horizon = :hz
          AND valid_to IS NULL AND score_lane = 'standing'
        ORDER BY scored_at DESC LIMIT 1
    """), {"c": h3_cell, "h": hazard, "sc": scenario, "hz": horizon}).mappings().first()
    if not r:
        return None
    fp = r["regulatory_fingerprint"]
    return {
        "risk_score": float(r["risk_score"]) if r["risk_score"] is not None else None,
        "risk_bucket": r["risk_bucket"], "model_version": r["model_version"], "model_id": r["model_id"],
        "data_vintage": r["data_vintage"].isoformat() if r["data_vintage"] else None,
        "scored_at": r["scored_at"].isoformat() if r["scored_at"] else None,
        "fingerprint": (fp[:16] if fp else None),
        "ci_lower": float(r["score_ci_lower"]) if r["score_ci_lower"] is not None else None,
        "ci_upper": float(r["score_ci_upper"]) if r["score_ci_upper"] is not None else None,
        "shap_factors": r["shap_factors"], "score_lane": r["score_lane"],
    }


def cell_lineage(session: Session, org_id: str, filing_id: str, hazard: str) -> dict:
    """FORWARD trace: a hazard cell within a filing → contributing assets → golden-source rows → source feeds.
    Reads the FROZEN snapshot so the trace matches exactly what was filed."""
    filing = get_filing(session, org_id, filing_id, with_payload=True)
    if not filing:
        raise ValueError("filing not found")
    framework = filing["framework"]
    snap = filing.get("snapshot") or {}
    payload = snap.get("payload") or {}
    basis = snap.get("reporting_basis") or {}
    scenario = basis.get("scenario", "baseline")
    horizon = basis.get("horizon", "current")

    cfg = _LIST_CFG.get(framework)
    if not cfg or "by_hazard" not in payload:
        return {"supported": False, "framework": framework,
                "message": _ALT_LINEAGE.get(framework) or _NO_HAZARD_CELLS.get(framework,
                    "Spatial lineage is available for the located-book filings (loan book, property book, "
                    "underwriting book).")}

    cell = (payload.get("by_hazard") or {}).get(hazard)
    if cell is None:
        raise ValueError(f"hazard '{hazard}' is not a reported cell in this filing")

    # the contributors are the ones the filed cell was computed from, on the definition in force when it was frozen:
    # today's — at or above the stated level, on a hazard that applies to the asset (portfolio_engine.exposure_by_hazard);
    # a filing frozen before the stated method — the High / Very-high bands, before the relevance registry existed
    from services.governance.pillar3_templates import LEGACY_LEVEL, hazard_hit, stated_level
    legacy = "method" not in payload
    level = stated_level(payload)

    def counted(h: dict) -> bool:
        if legacy:
            return h.get("score") is not None and float(h["score"]) >= LEGACY_LEVEL
        return level is not None and hazard_hit(h, level)

    contributors = []
    for a in payload.get(cfg["list"]) or []:
        hz = next((h for h in a.get("hazards", []) if h.get("hazard") == hazard and counted(h)), None)
        if not hz:
            continue
        g = _granular_row(session, a.get("h3_cell"), hazard, scenario, horizon)
        filed_mv = hz.get("model_version")
        contributors.append({
            "asset_id": a.get(cfg["id"]), "asset_name": a.get(cfg["name"]),
            "value_eur": a.get(cfg["value"]), "h3_cell": a.get("h3_cell"), "country": a.get("country"),
            "filed": {"score": hz.get("score"), "bucket": hz.get("bucket"),
                      "model_version": filed_mv, "scored_at": hz.get("scored_at")},
            "granular": g,
            "drift": bool(g and filed_mv and g.get("model_version") and g["model_version"] != filed_mv),
        })
    contributors.sort(key=lambda c: (c["value_eur"] or 0), reverse=True)

    return {
        "supported": True, "filing_id": filing_id, "framework": framework, "hazard": hazard,
        "basis": {"scenario": scenario, "horizon": horizon}, "currency": presentation_of(payload),
        "cell": {"exposed_value_eur": cell.get("exposed_value_eur"), "n_exposed": cell.get("n_exposed"),
                 "max_score": cell.get("max_score")},
        "contributors": contributors,
        "sources": feeds_for_hazard(session, hazard),
        "drift_count": sum(1 for c in contributors if c["drift"]),
    }


def reported_hazards(session: Session, org_id: str, filing_id: str) -> list[dict]:
    """The hazard cells a filing reports — the entry points for a forward trace (a located book that froze them)."""
    return hazards_view(session, org_id, filing_id)["hazards"]


def hazards_view(session: Session, org_id: str, filing_id: str) -> dict:
    """reported_hazards plus the currency the filing's amounts are in (its frozen presentation currency)."""
    filing = get_filing(session, org_id, filing_id, with_payload=True)
    if not filing:
        raise ValueError("filing not found")
    payload = (filing.get("snapshot") or {}).get("payload") or {}
    byh = payload.get("by_hazard") or {}
    out = [{"hazard": h, "exposed_value_eur": b.get("exposed_value_eur"),
            "n_exposed": b.get("n_exposed"), "max_score": b.get("max_score")}
           for h, b in byh.items()]
    out.sort(key=lambda x: (x["exposed_value_eur"] or 0), reverse=True)
    return {"hazards": out, "currency": presentation_of(payload)}


def cell_upstream(session: Session, org_id: str, h3_cell: str) -> dict:
    """REVERSE trace: a granular H3 cell → every located holding of this org on it → the framework/filing
    that reuses it. Tenant-scoped (only this org's book)."""
    entities = session.execute(text("""
        SELECT entity_id::text AS entity_id, entity_name, vertical, primary_value_eur
        FROM portfolio_entities
        WHERE org_id = :o AND h3_cell = :c
        ORDER BY primary_value_eur DESC NULLS LAST
    """), {"o": org_id, "c": h3_cell}).mappings().all()

    hazards_here = session.execute(text("""
        SELECT DISTINCT hazard_type FROM canonical_scores
        WHERE h3_cell = :c AND valid_to IS NULL AND score_lane = 'standing'
        ORDER BY hazard_type
    """), {"c": h3_cell}).scalars().all()

    # group by vertical → framework → the live filing (if any) that consumes it
    groups: dict[str, dict] = {}
    for e in entities:
        v = e["vertical"]
        g = groups.setdefault(v, {"vertical": v, "framework": _VERTICAL_FRAMEWORK.get(v),
                                  "n": 0, "value_eur": 0.0, "entities": []})
        g["n"] += 1
        g["value_eur"] += float(e["primary_value_eur"] or 0)
        g["entities"].append({"entity_id": e["entity_id"], "name": e["entity_name"],
                              "value_eur": float(e["primary_value_eur"]) if e["primary_value_eur"] is not None else None})
    for g in groups.values():
        g["value_eur"] = round(g["value_eur"])
        fw = g["framework"]
        if fw:
            f = session.execute(text("""
                SELECT filing_id::text AS filing_id, status FROM regulatory_filing
                WHERE org_id = :o AND framework = :fk AND status NOT IN ('superseded', 'withdrawn')
                ORDER BY created_at DESC LIMIT 1
            """), {"o": org_id, "fk": fw}).mappings().first()
            g["filing"] = {"filing_id": f["filing_id"], "status": f["status"]} if f else None
        else:
            g["filing"] = None

    return {"h3_cell": h3_cell, "hazards_scored_here": list(hazards_here),
            "used_by": sorted(groups.values(), key=lambda x: -x["value_eur"])}
