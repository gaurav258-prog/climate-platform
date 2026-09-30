"""The ESRS statement (E1, E3, E4) of one undertaking or group for one financial year: the figures the platform computes,
the ratios it derives, and the facts it supplies in support of the undertaking's own figures — from the book as it
stood at the period end. Only what a text or arithmetic establishes; anything else is a named gap.

  scope      ESRS 1 §62: the same reporting undertaking as the financial statements — for a parent preparing
             consolidated statements, the group. Subsidiaries in full; associates and joint ventures (equity method, or a
             joint venture proportionally consolidated) are value chain, not own operations (2023 ESRS 1 §67; 2026 ESRS 1
             §69-70); a joint operation's share as recognised in the financial statements is own operations (2026 ESRS 1
             AR 36). A proportionally consolidated entity whose arrangement is not stated is a gap. The undertaking's
             CSRD role (services.governance.csrd_roles) says whether it reports individually or for the group.
  book       sites held at the period end; finance's year-end values (carrying amount, the part addressed by
             adaptation, the year's net revenue — site_period_values)
  hazards    EU Taxonomy Appendix A climate hazards (acute / chronic) whose scale may set a building's level, under the
             high-emissions scenario, over the ESRS 1 §77 / §79 horizons; material at or above the level the
             undertaking states (esrs.method.physical_risk_level — no default); scores standing when the statement is
             prepared (information about conditions existing at period end, ESRS 1 §93)
  computed   E1 assets and net revenue at material physical risk (amount, share of the attested totals, acute /
             chronic, addressed by adaptation)
  derived    the ratios the application requirements define, in the unit they name (GHG and energy intensity per
             monetary unit of net revenue — the currency the undertaking states it in; water intensity per million EUR)
  support    for the undertaking's own figures: sites inside a listed biodiversity-sensitive area (E4 §35 counts those it
             negatively affects — its determination); sites in areas of (high) water stress by the governing version's
             definition (WRI Aqueduct), criterion by criterion
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

_REF_DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "esrs"
HORIZONS = ("short", "medium", "long")


@lru_cache(maxsize=4)
def _ref(name: str) -> dict:
    return json.loads((_REF_DIR / name).read_text())


def reference() -> dict:
    return _ref("physical_risk_assessment.json")


@lru_cache(maxsize=1)
def climate_nature() -> dict[str, str]:
    """hazard type → 'acute' | 'chronic' for the EU Taxonomy Appendix A hazards; anything else is not a climate hazard."""
    from core.hazard_taxonomy import EU_TAXONOMY
    return {ht.value: h.nature for h in EU_TAXONOMY for ht in h.internal}


def horizons(period_end: date) -> dict[str, tuple[str, str] | None]:
    """short / medium / long → (scenario, projected horizon) as of the end of the reporting period (ESRS 1 §77/§79):
    medium = a projection year in (end, end + 5 years]; long = a projection year after end + 5 years. None when no
    projection year falls inside the interval — the figure is then a gap, never a neighbouring year."""
    ref = reference()
    sc, end = ref["scenario"]["id"], period_end.year
    cut = end + ref["horizons"]["years_medium"]
    years = sorted(int(h) for h in ref["horizons"]["projected"])
    medium = next((y for y in reversed(years) if end < y <= cut), None)
    long_ = next((y for y in years if y > cut), None)
    return {"short": ("baseline", "current"), "medium": (sc, str(medium)) if medium else None,
            "long": (sc, str(long_)) if long_ else None}


# ───────────────────────────── scope and book as at the period end ─────────────────────────────

def scope(session: Session, org_id: str, entity_id: str | None, period_end: date) -> dict:
    from services.governance.csrd_roles import live_role
    role = live_role(session, org_id, entity_id, period_end)
    if entity_id is None:
        return {"entity_id": None, "role": role, "weights": None, "gaps": [], "basis": "the organisation as the undertaking"}
    if not (role and role["role"] == "consolidated"):
        return {"entity_id": entity_id, "role": role, "weights": {entity_id: 1.0}, "gaps": [],
                "basis": "the undertaking's own sites"}
    rows = session.execute(text("""
        SELECT entity_id::text, parent_entity_id::text, name, ownership_pct::float, consolidation_method, joint_arrangement
        FROM reporting_entities WHERE org_id = CAST(:o AS uuid)
    """), {"o": org_id}).all()
    parent = {r[0]: r[1] for r in rows}
    factor, gaps, basis = {}, [], {}
    for eid, _, name, pct, method, ja in rows:
        if method == "full" or method is None:
            factor[eid] = 1.0
        elif method == "equity":
            factor[eid], basis[name] = 0.0, "value chain (equity method)"
        elif ja == "joint_venture":
            factor[eid], basis[name] = 0.0, "value chain (joint venture)"
        elif ja == "joint_operation":
            factor[eid], basis[name] = (pct or 0) / 100.0, f"joint operation, {pct:g} % recognised"
        else:
            factor[eid] = None
            gaps.append(f"{name} is proportionally consolidated: state whether it is a joint operation or a joint venture")
    weights = {}
    for eid in parent:
        w, cur, hops, unknown = 1.0, eid, 0, False
        while cur != entity_id and parent.get(cur) is not None and hops < 64:
            if factor[cur] is None:
                unknown = True
                break
            w *= factor[cur]
            cur, hops = parent[cur], hops + 1
        if cur == entity_id and not unknown and w > 0:
            weights[eid] = w
    return {"entity_id": entity_id, "role": role, "weights": weights, "gaps": gaps, "treatment": basis,
            "basis": "the group (ESRS 1 §62): subsidiaries in full, joint operations at the share recognised, associates "
                     "and joint ventures as value chain"}


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

def assess(session: Session, sites: list[dict], period_end: date, level: float | None) -> dict:
    """Each site's material climate hazards per horizon, from the calibrated scores standing now (frozen with the filing)."""
    hz = horizons(period_end)
    live = {h: v for h, v in hz.items() if v}
    cells = sorted({s["h3_cell"] for s in sites if s["h3_cell"]})
    nature = climate_nature()
    rows = session.execute(text("""
        SELECT h3_cell, hazard_type, scenario, time_horizon, CAST(risk_score AS FLOAT) AS score, model_version
        FROM canonical_scores
        WHERE valid_to IS NULL AND h3_cell = ANY(CAST(:c AS text[]))
          AND (scenario, time_horizon) IN (SELECT * FROM unnest(CAST(:sc AS text[]), CAST(:th AS text[])))
          AND hazard_headline_eligible(hazard_type, 'buildings', model_version)
    """), {"c": cells, "sc": [v[0] for v in live.values()], "th": [v[1] for v in live.values()]}).mappings().all()
    by = {}
    for r in rows:
        if r["hazard_type"] in nature:                 # a climate hazard (not seismic, volcanic …)
            by.setdefault((r["h3_cell"], r["scenario"], r["time_horizon"]), []).append(r)
    out, versions = {}, set()
    for s in sites:
        per = {}
        now = {r["hazard_type"] for r in by.get((s["h3_cell"], *hz["short"]), [])} if hz.get("short") else set()
        for h in HORIZONS:
            if hz[h] is None or level is None:
                per[h] = {"scored": None, "material": None, "acute": None, "chronic": None, "unprojected": []}
                continue
            got = by.get((s["h3_cell"], *hz[h]), [])
            versions |= {f"{r['hazard_type']}:{r['model_version']}" for r in got}
            mat = sorted({r["hazard_type"] for r in got if r["score"] >= level})
            # a hazard scored at the site today but not projected for this horizon: its future level is not known —
            # the horizon cannot be read as 'not material' for it
            per[h] = {"scored": bool(got), "material": mat, "acute": any(nature[m] == "acute" for m in mat),
                      "chronic": any(nature[m] == "chronic" for m in mat),
                      "unprojected": sorted(now - {r["hazard_type"] for r in got})}
        out[s["site_id"]] = per
    return {"by_site": out, "horizons": {h: ({"scenario": v[0], "horizon": v[1]} if v else None) for h, v in hz.items()},
            "model_versions": sorted(versions), "level": level}


# ───────────────────────────── the figures ─────────────────────────────

def _share(num, den):
    return round(100 * num / den, 4) if num is not None and den else None


def compute(session: Session, org_id: str, *, entity_id: str | None, period_end: date, esrs_version: str) -> dict:
    from services.governance.provided_data import ESRS, attested_values
    provided = {v["concept"]: v for v in attested_values(session, org_id, ESRS, period_end, reporting_entity_id=entity_id)
                if not v.get("member")}
    lv = provided.get("esrs.method.physical_risk_level")
    level = float(lv["value"]) if lv else None
    sc = scope(session, org_id, entity_id, period_end)
    sites = sites_at(session, org_id, sc, period_end)
    risk = assess(session, sites, period_end, level)
    hz = risk["horizons"]

    def eur(key):
        v = provided.get(key)
        return None if v is None else (v["value_eur"] if v.get("currency") else v["value"])

    base_gaps = list(sc["gaps"])
    if level is None:
        base_gaps.append("the undertaking has not stated the level at which a physical climate risk is material "
                         "(esrs.method.physical_risk_level)")
    base_gaps += [f"no carrying amount at {period_end} for {s['name']}" for s in sites if s["carrying"] is None]
    concepts: dict = {}

    def unprojected(h):
        """'<hazard> at <site>' for each hazard scored today that the horizon's projection does not score."""
        return [f"{z} at {s['name']}" for s in sites for z in risk["by_site"][s["site_id"]][h].get("unprojected") or []]

    def horizon_values(fn):
        return {h: (fn(h) if hz[h] is not None and level is not None and not unprojected(h) else None) for h in HORIZONS}

    def at(h):
        return [s for s in sites if risk["by_site"][s["site_id"]][h]["material"]]

    def amt(h, key="carrying", flag=None):
        return round(sum(s["weight"] * (s[key] or 0) for s in at(h) if flag is None or risk["by_site"][s["site_id"]][h][flag]), 2)

    def put(key, values, extra_gaps=()):
        gaps = base_gaps + [g for g in extra_gaps if g]
        missing_h = [h for h in HORIZONS if hz[h] is None]
        if missing_h:
            gaps = gaps + [f"no projection year inside the {', '.join(missing_h)}-term interval"]
        gaps += [f"{h} term: no {hz[h]['scenario']} projection for {', '.join(unprojected(h))}" for h in HORIZONS
                 if hz[h] is not None and level is not None and unprojected(h)]
        concepts[key] = {"value": values.get("short"), "by_horizon": values, "status": "gap" if gaps else "computed",
                         **({"gap": "; ".join(gaps)} if gaps else {})}
    put("e1.physrisk.assets.amount", horizon_values(amt))
    put("e1.physrisk.assets.acute", horizon_values(lambda h: amt(h, flag="acute")))
    put("e1.physrisk.assets.chronic", horizon_values(lambda h: amt(h, flag="chronic")))
    put("e1.physrisk.assets.pct", horizon_values(lambda h: _share(amt(h), eur("fs.total_assets"))),
        [None if eur("fs.total_assets") else "total assets (balance sheet) not attested"])
    unstated = lambda h: [s["name"] for s in at(h) if s["adapted"] is None]          # noqa: E731
    adapted = horizon_values(lambda h: None if unstated(h) else _share(amt(h, "adapted"), amt(h)) if at(h) else 0.0)
    put("e1.physrisk.assets.addressed_pct", adapted,
        [f"the carrying amount addressed by adaptation is not stated for {', '.join(unstated('short'))}"
         if level is not None and unstated("short") else None])
    concepts["e1.physrisk.assets.addressed_pct.v2026"] = {**concepts["e1.physrisk.assets.addressed_pct"],
                                                          "value": adapted.get("short")}      # at the reporting date
    no_rev = [s["name"] for s in (at("short") if level is not None else []) if s["revenue"] is None]
    put("e1.physrisk.revenue.amount", horizon_values(lambda h: amt(h, "revenue")),
        [f"net revenue not stated for {', '.join(no_rev)}" if no_rev else None])
    put("e1.physrisk.revenue.pct", horizon_values(lambda h: _share(amt(h, "revenue"), eur("fs.net_revenue"))),
        [None if eur("fs.net_revenue") else "net revenue (financial statements) not attested"])
    concepts.update(_derived(provided))
    return {"period_end": period_end.isoformat(), "esrs_version": esrs_version, "scope": sc, "concepts": concepts,
            "assessment": {**risk, "unscored_sites": [s["name"] for s in sites if level is not None and not any(
                risk["by_site"][s["site_id"]][h]["scored"] for h in HORIZONS if hz[h])],
                "reference": {k: reference()[k] for k in ("scenario", "horizons", "climate_hazards", "hazard_vintage")},
                "information_after_period_end": "ESRS 1 §93"},
            "support": {"biodiversity_sensitive": _sensitive(session, sites, esrs_version),
                        "water_stress": _water(session, sites, esrs_version)},
            "sites": [{**{k: s[k] for k in ("site_id", "name", "entity_id", "weight", "carrying", "adapted", "revenue",
                                           "area_ha", "held_from", "held_until")}, "risk": risk["by_site"][s["site_id"]]}
                      for s in sites]}


def _sensitive(session: Session, sites: list[dict], esrs_version: str) -> dict:
    """Sites located inside a loaded layer that is one of the kinds ESRS lists (never 'near': no measure in the text)."""
    ref = _ref("biodiversity_sensitive.json")
    edition = ref["versions"][esrs_version]
    listed = [d for d, x in ref["datasets"].items() if x["listed"]]
    from services.reference.protected_layers import current_loads
    loads = [x for x in current_loads(session) if x["dataset"] in listed]
    inside = {r[0]: r[1] for r in session.execute(text("""
        SELECT h3_cell, array_agg(DISTINCT dataset) FROM v_protected_h3_current
        WHERE h3_cell = ANY(CAST(:c AS text[])) AND within_km = 0 AND dataset = ANY(CAST(:d AS text[])) GROUP BY h3_cell
    """), {"c": [s["h3_cell"] for s in sites if s["h3_cell"]], "d": listed}).all()}
    kinds_loaded = {ref["datasets"][x["dataset"]]["kind"] for x in loads}
    return {"definition": {k: ref[edition][k] for k in ("quote", "ref")},
            "not_assessed": [k for k in ref[edition]["kinds"] if k not in kinds_loaded],
            "loads": loads, "measure": "the site's grid cell (H3 resolution 8) lies inside a listed area",
            "sites": [{"site_id": s["site_id"], "name": s["name"], "area_ha": s["area_ha"], "in": inside.get(s["h3_cell"])}
                      for s in sites if s["h3_cell"] in inside]}


def _water(session: Session, sites: list[dict], esrs_version: str) -> dict:
    from services.reference.aqueduct import classify, definitions
    edition = definitions()["versions"][esrs_version]
    return {"definition": {k: definitions()[edition][k] for k in ("term", "quote", "ref")},
            "sites": [{"site_id": s["site_id"], "name": s["name"],
                       **classify(session, s["latitude"], s["longitude"], esrs_version)} for s in sites]}


def _derived(provided: dict) -> dict:
    """The ratios the application requirements define, in the unit they name, from attested figures."""
    def v(key, eur=False):
        x = provided.get(key)
        return None if x is None else (x["value_eur"] if eur and x.get("currency") else x["value"])

    def ccy(key):
        return (provided.get(key) or {}).get("currency")

    def ratio(key, num, den, scale=1.0, unit=None, den_eur=False, num_eur=False):
        n, d = v(num, num_eur), v(den, den_eur)
        if n is None or not d:
            return {key: {"value": None, "status": "gap", "gap": f"needs {num} and {den}"}}
        return {key: {"value": round(n / d * scale, 10), "status": "derived", "unit": unit}}
    out = {}
    # shares of attested totals: numerator and denominator in EUR (each converted by its own period rule)
    out.update(ratio("e1.transrisk.assets.pct", "e1.transrisk.assets.amount", "fs.total_assets", 100, "percent", True, True))
    out.update(ratio("e1.transrisk.revenue.pct", "e1.transrisk.revenue.amount", "fs.net_revenue", 100, "percent", True, True))
    # 'MWh/Monetary unit', 'tCO2eq/Monetary unit' (2023 E1 AR 38, AR 53): per unit of the currency net revenue is stated in
    out.update(ratio("e1.energy.intensity_high_impact", "fs.energy_high_impact", "fs.net_revenue_high_impact", 1,
                     f"MWh/{ccy('fs.net_revenue_high_impact') or 'monetary unit'}"))
    loc = ratio("x", "e1.ghg.total.location", "fs.net_revenue")["x"]
    mkt = ratio("x", "e1.ghg.total.market", "fs.net_revenue")["x"]
    out["e1.ghg.intensity_net_revenue"] = (
        {"value": {"location": loc["value"], "market": mkt["value"]}, "status": "derived",
         "unit": f"tCO2eq/{ccy('fs.net_revenue') or 'monetary unit'}"}
        if loc["value"] is not None and mkt["value"] is not None
        else {"value": None, "status": "gap", "gap": "needs total GHG (location- and market-based) and net revenue"})
    # 'm3 per million EUR net revenue' (2023 E3 §29)
    out.update(ratio("e3.water.intensity", "e3.water.consumption", "fs.net_revenue", 1e6, "m3/EURm", den_eur=True))
    return out
