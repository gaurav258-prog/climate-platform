"""The drill behind one KRI (kri.kri_detail): its forward projection, the exposures that drive it and its composition —
each read from the same live book the KRI tile is computed from, so a drill sums to the figure it explains (E79,
E339). On a filer's scope (services.governance.kri_scope) that is the filer's book: the scoped snapshot, and for the
figures read off the stored book (the forward projection) each asset's share of it (Scope.shares) (E351).
"""
from __future__ import annotations

from sqlalchemy.orm import Session


def _forward(session: Session, org_id: str, vertical: str, scen: str, scope=None) -> dict:
    """The forward projection of the book the KRIs are on: the whole book, or the filer's (each asset at its share)."""
    from services.intelligence.forward_risk import forward_risk
    from services.money.params import for_org
    return forward_risk(session, org_id, vertical, scen, for_org(session, org_id),
                        shares=scope.shares(session, org_id) if scope is not None else None)


# Physical/forward KRIs get a forward trajectory chart (value across horizons under a warming pathway, with
# an act-vs-inaction band and the appetite thresholds) — the "when do we cross appetite" decision view.
_PROJECTION_KEYS = {"value_at_risk", "pct_at_risk", "forward_share"}


def _kri_projection(session: Session, org_id: str, framework: str, kri_key: str, kpi: dict, scope=None) -> dict | None:
    from services.governance.kri import _amount, msg
    if kri_key not in _PROJECTION_KEYS or framework not in ("bank_tcfd", "bank_p3esg", "reit_taxonomy"):
        return None
    try:
        from services.governance.reporting_settings import get_settings
        vert = {"reit_taxonomy": "realestate"}.get(framework, "banking")
        s = get_settings(session, org_id)
        scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
        fr = _forward(session, org_id, vert, scen, scope)
        book = fr.get("book_eur") or 0
        is_pct = kri_key in ("pct_at_risk", "forward_share")
        pts = []
        for t in fr.get("trajectory") or []:
            band = t.get("at_risk_band_eur") or [t.get("at_risk_eur"), t.get("at_risk_eur")]
            to = (lambda v: round(100 * v / book, 1) if book else 0) if is_pct else (lambda v: round(v))
            pts.append({"horizon": t.get("horizon"),
                        "value": t.get("at_risk_pct") if is_pct else _amount(t.get("at_risk_eur")),
                        "lo": to(band[0]), "hi": to(band[1])})
        if len(pts) < 2:
            return None
        from core import messages
        name = messages.name("scenario", scen)
        return {"points": pts, "unit": "pct" if is_pct else "eur",
                "warn": kpi.get("amber"), "breach": kpi.get("red"),
                "scenario": scen, "scenario_name": name, "message": msg("kri.projection.basis", scenario=name)}
    except Exception:  # noqa: BLE001 — a missing projection must not break the drawer
        return None


# KRIs whose most-granular drill is the individual exposures (assets) behind the number.
_DRIVER_KEYS = {"total_value", "value_at_risk", "pct_at_risk", "acute_share", "chronic_share",
                "forward_share", "sector_concentration", "fin_emissions"}


def _kri_drivers(session: Session, org_id: str, framework: str, kri_key: str,
                 seg_type: str | None = None, seg_value: str | None = None, scope=None) -> dict | None:
    """The most granular view: the individual exposures (assets) behind a KRI, largest-contribution first —
    the actual names a risk officer acts on, each carrying its asset id so the row opens the asset detail.
    Without a segment, the filter follows the KRI. With a segment (from a click on a composition bar) the
    filter narrows to that slice: seg_type 'scope' (emissions Scope 1/2/3), 'hazard' (at or above the stated level on one peril),
    or 'sector' (one NACE section). Only for bank/REIT books; never fabricated."""
    if framework not in ("bank_tcfd", "bank_p3esg", "reit_taxonomy"):
        return None
    if not seg_type and kri_key not in _DRIVER_KEYS:
        return None
    from services.governance.kri import _live_snapshot
    from services.governance.pillar3_templates import (
        HIGH_CLIMATE_NACE,
        _asset_hits,
        _section,
        hazard_hit,
        stated_level,
    )
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"], scope)
    assets = (snap or {}).get("assets") or (snap or {}).get("properties") or []
    if not assets:
        return None
    level = stated_level(snap)
    needs_level = seg_type == "hazard" or (not seg_type and kri_key in ("value_at_risk", "pct_at_risk", "forward_share",
                                                                       "acute_share", "chronic_share"))
    if needs_level and level is None:
        return None                                   # 'at risk' is the stated level; not stated → no drill (the KRI names the gap)
    vkey = "value_eur" if framework != "reit_taxonomy" else "property_value_eur"
    def _val(a):
        return a.get(vkey) or 0
    def high(a):
        return a.get("headline_score") is not None and a["headline_score"] >= level

    if seg_type == "scope" and seg_value in ("1", "2", "3"):
        # the loans behind one scope's bar: each by its part of that scope's financed figure — the attributed emissions
        # the bar sums (services.scoring.pcaf.asset_financed), mortgages included
        from services.scoring.pcaf import asset_financed
        def weight(a):
            return asset_financed(a)[f"scope{seg_value}"] or 0.0
        def keep(a):
            return weight(a) > 0
        unit = "num"
    elif seg_type == "hazard" and seg_value:
        def keep(a):
            return any(h.get("hazard") == seg_value and hazard_hit(h, level) for h in (a.get("hazards") or []))
        weight, unit = _val, "eur"
    elif seg_type == "sector" and seg_value:
        def keep(a):
            return _section(a.get("nace_code")) == seg_value
        weight, unit = _val, "eur"
    else:                                             # KRI-scoped default
        def keep(a):
            if kri_key in ("value_at_risk", "pct_at_risk", "forward_share"):
                return high(a)
            if kri_key == "acute_share":
                return _asset_hits(a, level)[1]
            if kri_key == "chronic_share":
                return _asset_hits(a, level)[0]
            if kri_key == "sector_concentration":
                return _section(a.get("nace_code")) in HIGH_CLIMATE_NACE
            return True                               # total_value / fin_emissions → whole book
        def _pcaf_weight(a):
            # each loan's part of the KRI's figure, by the rules the figure sums (services.scoring.pcaf.asset_financed):
            # a company stating all three scopes, a mortgage's scope 1 and 2 — 0 (excluded below) where it is not counted
            from services.scoring.pcaf import asset_financed
            return asset_financed(a)["total"] or 0.0
        weight = _pcaf_weight if kri_key == "fin_emissions" else _val
        unit = "num" if kri_key == "fin_emissions" else "eur"

    rows = [a for a in assets if keep(a) and weight(a) > 0]
    rows.sort(key=weight, reverse=True)
    from services.governance.pillar3_templates import NACE_SECTIONS
    items = [{
        "id": a.get("asset_id") or a.get("property_id"),
        "name": a.get("asset_name") or a.get("property_name") or a.get("asset_id") or a.get("property_id"), "sector": a.get("sector"),
        "country": a.get("country"), "nace": a.get("nace_code"),
        "sector_name": NACE_SECTIONS.get(_section(a.get("nace_code"))) if a.get("nace_code") else None,
        "value": round(weight(a)), "hazard": a.get("headline_hazard"),
        "bucket": a.get("headline_bucket"), "score": a.get("headline_score"),
    } for a in rows[:8]]
    return {"unit": unit, "total_count": len(rows), "items": items} if items else None


def _kri_composition(session: Session, org_id: str, framework: str, kri_key: str, result: dict, scope=None) -> dict | None:
    """The real breakdown behind a KRI — never fabricated; returns None when no honest decomposition exists."""
    from services.governance.kri import _EXPOSURE_KEYS, _hazard_name, _live_snapshot
    if kri_key in _EXPOSURE_KEYS and result.get("by_hazard"):
        return {"type": "hazard", "unit": "eur",
                "items": [{"key": h["hazard"], "label": _hazard_name(h["hazard"]), "value": h["value"], "score": h.get("score")}
                          for h in result["by_hazard"]]}
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"], scope)
    if not snap:
        return None
    if kri_key == "fin_emissions":
        em = snap.get("financed_emissions_tco2e", {}) or {}
        # the scopes stated; a scope nobody states is left out, never drawn as 0 (E76)
        items = [{"key": str(i), "label": f"Scope {i}", "value": round(em[f"scope{i}"])} for i in (1, 2, 3) if em.get(f"scope{i}") is not None]
        return {"type": "scope", "unit": "num", "items": items} if items else None
    if kri_key == "coverage":
        r = snap.get("rollup", {}) or {}
        n, sc = r.get("n_assets") or 0, r.get("n_scored") or 0
        return {"type": "coverage", "unit": "num",
                "items": [{"key": "scored", "label": "Scored", "value": sc},
                          {"key": "unscored", "label": "Not yet scored", "value": max(0, n - sc)}]} if n else None
    if kri_key == "taxonomy" and framework != "reit_taxonomy":   # the REIT figure is turnover-based, not this value split
        tax = snap.get("taxonomy", {}) or {}
        elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
        total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
        return {"type": "taxonomy", "unit": "eur",
                "items": [{"key": "eligible", "label": "Eligible", "value": round(elig)},
                          {"key": "not_eligible", "label": "Not eligible", "value": round(max(0, total - elig))}]} if total else None
    # acute / chronic peril exposure — the value-weighted hazard breakdown WITHIN that peril category
    if kri_key in ("acute_share", "chronic_share"):
        from services.governance.pillar3_templates import (
            ACUTE_HAZARDS,
            CHRONIC_HAZARDS,
            hazard_hit,
            stated_level,
        )
        level = stated_level(snap)
        if level is None:
            return None
        cats = ACUTE_HAZARDS if kri_key == "acute_share" else CHRONIC_HAZARDS
        by_h: dict[str, float] = {}
        for a in snap.get("assets") or []:
            v = a.get("value_eur") or 0
            if not v:
                continue
            for h in a.get("hazards") or []:
                if h.get("hazard") in cats and hazard_hit(h, level):
                    by_h[h["hazard"]] = by_h.get(h["hazard"], 0.0) + v
        items = sorted(({"key": k, "label": _hazard_name(k), "value": round(v)} for k, v in by_h.items()), key=lambda x: -x["value"])
        return {"type": "hazard", "unit": "eur", "items": items} if items else None
    # climate-sector concentration — value by NACE section (the concentration axis of Templates 1 & 5)
    if kri_key == "sector_concentration":
        from services.governance.pillar3_templates import (
            HIGH_CLIMATE_NACE,
            NACE_SECTIONS,
            concentration_split,
        )
        cs = concentration_split(snap.get("assets") or [], None)
        items = sorted(
            ({"key": sec, "label": NACE_SECTIONS.get(sec, "Unclassified"), "value": round(val)}
             for sec, val in cs["by_sector"].items() if sec in HIGH_CLIMATE_NACE),
            key=lambda x: -x["value"])
        return {"type": "sector", "unit": "eur", "items": items} if items else None
    # forward share — the projected at-risk trajectory across horizons under the warming pathway
    if kri_key == "forward_share":
        try:
            scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
            traj = _forward(session, org_id, "banking", scen, scope).get("trajectory") or []
            items = [{"key": t.get("horizon"), "label": "Today" if t.get("horizon") == "current" else t.get("horizon"),
                      "value": t.get("at_risk_pct") or 0} for t in traj]
            return {"type": "horizon", "unit": "pct", "items": items} if len(items) >= 2 else None
        except Exception:  # noqa: BLE001
            return None
    return None


