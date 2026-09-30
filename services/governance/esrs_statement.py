"""The ESRS statement (E1, E3, E4) of one undertaking or group for one financial year: the figures the platform computes
and the ratios it derives, from the book as it stood at the period end — never from today's book.

  scope      the reporting undertaking's own sites (Art. 19a), or the group's (Art. 29a): the same undertakings as its
             financial statements — subsidiaries in full, joint operations at their share, associates and joint ventures
             outside own operations (value chain) — by the undertaking's stated CSRD role (services.governance.csrd_roles)
  book       the sites held at the period end (held_from ≤ end < held_until), finance's year-end values for them
             (carrying amount, the part addressed by adaptation, the year's net revenue — site_period_values)
  hazards    each site on the EU Taxonomy climate hazards (acute / chronic), short, medium and long term under the
             high-emissions scenario, material at or above the undertaking's materiality level
             (data/reference/esrs/physical_risk_assessment.json: every choice quoted)
  computed   E1 assets and net revenue at material physical risk (amount, share, acute / chronic, addressed by
             adaptation); E4 own sites in or near biodiversity-sensitive areas (number, area)
  derived    the ratios the application requirements define from the undertaking's attested figures
Every figure says what it rests on; a figure that cannot be computed is a gap with its reason, never a zero.
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

_REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "esrs" / "physical_risk_assessment.json"
HORIZONS = ("short", "medium", "long")


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(_REF.read_text())


@lru_cache(maxsize=1)
def climate_nature() -> dict[str, str]:
    """hazard type → 'acute' | 'chronic' for the EU Taxonomy Appendix A hazards; anything else is not a climate hazard."""
    from core.hazard_taxonomy import EU_TAXONOMY
    return {ht.value: h.nature for h in EU_TAXONOMY for ht in h.internal}


def horizons(period_end: date) -> dict[str, tuple[str, str]]:
    """short / medium / long → (scenario, projected horizon), as of the end of the reporting period (ESRS 1 §77/§79)."""
    ref = reference()
    sc, cut = ref["scenario"]["id"], period_end.year + ref["horizons"]["years_medium"]
    years = [int(h) for h in ref["horizons"]["projected"]]
    within = [y for y in years if y <= cut]
    medium = max(within) if within else min(years)
    long_ = next((y for y in years if y > cut and y != medium), years[-1])
    return {"short": ("baseline", "current"), "medium": (sc, str(medium)), "long": (sc, str(long_))}


# ───────────────────────────── scope and book as at the period end ─────────────────────────────

def scope(session: Session, org_id: str, entity_id: str | None, period_end: date) -> dict:
    from services.governance.csrd_roles import live_role
    from services.governance.entities import ownership_weights, subtree_ids
    role = live_role(session, org_id, entity_id, period_end)
    if entity_id is None:
        return {"entity_id": None, "role": role, "weights": None, "basis": "the organisation as the undertaking"}
    if role and role["role"] == "consolidated":
        ids = subtree_ids(session, org_id, entity_id)
        w = ownership_weights(session, org_id, root_entity_id=entity_id, regime="esrs_financial_statements")
        return {"entity_id": entity_id, "role": role, "weights": {e: w.get(e, 1.0) for e in ids if w.get(e, 1.0) > 0},
                "basis": "the group: subsidiaries in full, joint operations at their share, associates and joint "
                         "ventures outside own operations (value chain)"}
    return {"entity_id": entity_id, "role": role, "weights": {entity_id: 1.0}, "basis": "the undertaking's own sites"}


def sites_at(session: Session, org_id: str, sc: dict, period_end: date) -> list[dict]:
    rows = session.execute(text("""
        SELECT s.site_id::text AS site_id, s.name, s.entity_id::text AS entity_id, s.h3_cell, s.latitude, s.longitude,
               CAST(s.area_ha AS FLOAT) AS area_ha, s.held_from, s.held_until,
               MAX(v.amount_eur) FILTER (WHERE v.measure = 'carrying_amount') AS carrying,
               MAX(v.amount_eur) FILTER (WHERE v.measure = 'carrying_amount_adapted') AS adapted,
               MAX(v.amount_eur) FILTER (WHERE v.measure = 'net_revenue') AS revenue
        FROM sc_company_sites s
        LEFT JOIN v_site_period_values_live v ON v.site_id = s.site_id AND v.period_end = CAST(:pe AS date)
        WHERE s.org_id = CAST(:o AS uuid)
          AND (s.held_from IS NULL OR s.held_from <= CAST(:pe AS date))
          AND (s.held_until IS NULL OR s.held_until > CAST(:pe AS date))
        GROUP BY s.site_id
    """), {"o": org_id, "pe": period_end}).mappings().all()
    w = sc["weights"]
    out = []
    for r in rows:
        if w is not None and r["entity_id"] not in w:
            continue
        d = {k: (float(r[k]) if r[k] is not None else None) for k in ("carrying", "adapted", "revenue")}
        out.append({**dict(r), **d, "weight": 1.0 if w is None else w[r["entity_id"]],
                    "held_from": r["held_from"] and r["held_from"].isoformat(),
                    "held_until": r["held_until"] and r["held_until"].isoformat()})
    return out


# ───────────────────────────── hazards ─────────────────────────────

def assess(session: Session, sites: list[dict], period_end: date, threshold: float) -> dict:
    """Each site's material climate hazards per horizon, from the calibrated scores standing now (frozen with the filing)."""
    hz = horizons(period_end)
    cells = sorted({s["h3_cell"] for s in sites if s["h3_cell"]})
    nature = climate_nature()
    rows = session.execute(text("""
        SELECT h3_cell, hazard_type, scenario, time_horizon, CAST(risk_score AS FLOAT) AS score, model_version
        FROM canonical_scores
        WHERE valid_to IS NULL AND h3_cell = ANY(CAST(:c AS text[]))
          AND (scenario, time_horizon) IN (SELECT * FROM unnest(CAST(:sc AS text[]), CAST(:th AS text[])))
          AND hazard_headline_eligible(hazard_type, 'buildings', model_version)
    """), {"c": cells, "sc": [v[0] for v in hz.values()], "th": [v[1] for v in hz.values()]}).mappings().all()
    by = {}
    for r in rows:
        if r["hazard_type"] not in nature:
            continue                                                       # not a climate hazard (seismic, volcanic …)
        by.setdefault((r["h3_cell"], r["scenario"], r["time_horizon"]), []).append(r)
    out, versions = {}, set()
    for s in sites:
        per = {}
        for h, (sc_, th) in hz.items():
            got = by.get((s["h3_cell"], sc_, th), [])
            versions |= {f"{r['hazard_type']}:{r['model_version']}" for r in got}
            mat = sorted({r["hazard_type"] for r in got if r["score"] >= threshold})
            per[h] = {"scored": bool(got), "material": mat, "acute": any(nature[m] == "acute" for m in mat),
                      "chronic": any(nature[m] == "chronic" for m in mat)}
        out[s["site_id"]] = per
    return {"by_site": out, "horizons": {h: {"scenario": v[0], "horizon": v[1]} for h, v in hz.items()},
            "model_versions": sorted(versions), "threshold": threshold}


def _protected(session: Session, sites: list[dict]) -> dict:
    from services.reference.protected_layers import current_loads
    cells = [s["h3_cell"] for s in sites if s["h3_cell"]]
    hit = {r[0]: float(r[1]) for r in session.execute(text("""
        SELECT h3_cell, MIN(within_km) FROM v_protected_h3_current WHERE h3_cell = ANY(CAST(:c AS text[])) GROUP BY h3_cell
    """), {"c": cells}).all()}
    return {"cells": hit, "loads": current_loads(session)}


# ───────────────────────────── the figures ─────────────────────────────

def _share(num, den):
    return round(100 * num / den, 2) if num is not None and den else None


def compute(session: Session, org_id: str, *, entity_id: str | None, period_end: date, threshold: float) -> dict:
    from services.governance.provided_data import ESRS, attested_values
    sc = scope(session, org_id, entity_id, period_end)
    sites = sites_at(session, org_id, sc, period_end)
    risk = assess(session, sites, period_end, threshold)
    prot = _protected(session, sites)
    provided = {v["concept"]: v for v in attested_values(session, org_id, ESRS, period_end, reporting_entity_id=entity_id)
                if not v.get("member")}

    def eur(key):                        # an attested amount in EUR (or a quantity as stated)
        v = provided.get(key)
        return None if v is None else (v["value_eur"] if v.get("currency") else v["value"])

    gaps = [f"no carrying amount at {period_end} for {s['name']}" for s in sites if s["carrying"] is None]
    concepts: dict = {}
    phys = {k: {} for k in ("amount", "acute", "chronic", "pct", "addressed_pct", "revenue", "revenue_pct")}
    for h in HORIZONS:
        at = [s for s in sites if risk["by_site"][s["site_id"]][h]["material"]]
        amt = sum(s["weight"] * (s["carrying"] or 0) for s in at)
        phys["amount"][h] = round(amt, 2)
        phys["acute"][h] = round(sum(s["weight"] * (s["carrying"] or 0) for s in at if risk["by_site"][s["site_id"]][h]["acute"]), 2)
        phys["chronic"][h] = round(sum(s["weight"] * (s["carrying"] or 0) for s in at if risk["by_site"][s["site_id"]][h]["chronic"]), 2)
        phys["pct"][h] = _share(amt, eur("fs.total_assets"))
        unstated = [s for s in at if s["adapted"] is None]
        phys["addressed_pct"][h] = (_share(sum(s["weight"] * s["adapted"] for s in at), amt)
                                    if at and not unstated else (0.0 if not at else None))
        rev = sum(s["weight"] * (s["revenue"] or 0) for s in at)
        phys["revenue"][h] = round(rev, 2)
        phys["revenue_pct"][h] = _share(rev, eur("fs.net_revenue"))
    unscored = [s["name"] for s in sites if not any(risk["by_site"][s["site_id"]][h]["scored"] for h in HORIZONS)]
    at_short = [s for s in sites if risk["by_site"][s["site_id"]]["short"]["material"]]

    def put(key, by_h, gap=None):
        concepts[key] = {"value": by_h.get("short"), "by_horizon": by_h, "status": "gap" if gap else "computed",
                         **({"gap": gap} if gap else {})}
    put("e1.physrisk.assets.amount", phys["amount"], "; ".join(gaps) or None)
    put("e1.physrisk.assets.acute", phys["acute"], "; ".join(gaps) or None)
    put("e1.physrisk.assets.chronic", phys["chronic"], "; ".join(gaps) or None)
    put("e1.physrisk.assets.pct", phys["pct"], None if eur("fs.total_assets") else "total assets (balance sheet) not attested")
    put("e1.physrisk.assets.addressed_pct", phys["addressed_pct"],
        None if all(s["adapted"] is not None for s in at_short) else
        f"the carrying amount addressed by adaptation is not stated for {sum(1 for s in at_short if s['adapted'] is None)} site(s) at material risk")
    put("e1.physrisk.revenue.amount", phys["revenue"],
        None if all(s["revenue"] is not None for s in at_short) else "net revenue not stated for a site at material risk")
    put("e1.physrisk.revenue.pct", phys["revenue_pct"], None if eur("fs.net_revenue") else "net revenue (financial statements) not attested")

    sensitive = [s for s in sites if s["h3_cell"] in prot["cells"]]
    concepts["e4.sites.sensitive.count"] = {"value": len(sensitive), "status": "computed"}
    no_area = [s["name"] for s in sensitive if s["area_ha"] is None]
    concepts["e4.sites.sensitive.area_ha"] = {"value": round(sum(s["area_ha"] or 0 for s in sensitive), 4),
                                              "status": "gap" if no_area else "computed",
                                              **({"gap": "area not stated for " + ", ".join(no_area)} if no_area else {})}
    concepts.update(_derived(eur))
    return {"period_end": period_end.isoformat(), "scope": {k: v for k, v in sc.items()}, "concepts": concepts,
            "assessment": {**risk, "unscored_sites": unscored, "protected_loads": prot["loads"],
                           "reference": {k: reference()[k] for k in ("scenario", "horizons", "climate_hazards", "hazard_vintage")}},
            "sites": [{**{k: s[k] for k in ("site_id", "name", "entity_id", "weight", "carrying", "adapted", "revenue",
                                           "area_ha", "held_from", "held_until")},
                       "risk": risk["by_site"][s["site_id"]], "in_or_near_protected": s["h3_cell"] in prot["cells"]}
                      for s in sites]}


def _derived(eur) -> dict:
    """The ratios the application requirements define, from the undertaking's attested figures (data/reference/esrs/
    concepts.json 'from'); amounts in EUR."""
    def ratio(key, num, den, scale=1.0, unit=None):
        n, d = eur(num), eur(den)
        if n is None or not d:
            return {key: {"value": None, "status": "gap", "gap": f"needs {num} and {den}"}}
        return {key: {"value": round(n / d * scale, 6), "status": "derived", "unit": unit}}
    out = {}
    out.update(ratio("e1.transrisk.assets.pct", "e1.transrisk.assets.amount", "fs.total_assets", 100, "percent"))
    out.update(ratio("e1.transrisk.revenue.pct", "e1.transrisk.revenue.amount", "fs.net_revenue", 100, "percent"))
    out.update(ratio("e1.energy.intensity_high_impact", "fs.energy_high_impact", "fs.net_revenue_high_impact", 1, "MWh/EUR"))
    out.update(ratio("e3.water.intensity", "e3.water.consumption", "fs.net_revenue", 1e6, "m3/EURm"))
    loc, mkt = ratio("x", "e1.ghg.total.location", "fs.net_revenue")["x"], ratio("x", "e1.ghg.total.market", "fs.net_revenue")["x"]
    out["e1.ghg.intensity_net_revenue"] = ({"value": {"location": loc["value"], "market": mkt["value"]}, "status": "derived",
                                            "unit": "tCO2eq/EUR"} if loc["value"] is not None and mkt["value"] is not None
                                           else {"value": None, "status": "gap",
                                                 "gap": "needs total GHG (location- and market-based) and net revenue"})
    return out
