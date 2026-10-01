"""Key Regulatory Indicator (KRI) dashboard — the regulator's-eye consolidated risk view.

One place for the headline physical-risk indicators of the book: how much value sits at or above the stated at-risk level, the
share of the book, coverage, financed emissions and taxonomy eligibility, plus the same figures over the
org's filed history so a trend is visible. Current figures come from the live engine (the same source the
disclosure uses); the history comes from the immutable filed snapshots, so the trend is auditable.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

# The money KRIs that are amounts PER YEAR (flows): a screen in another currency translates them at the average rate,
# every other money KRI (values, exposures, capital) at the closing rate — multi-currency decision 3.
FLOW_KRIS = frozenset({"eal", "expected_loss", "fs.net_revenue", "e1.physrisk.revenue.amount"})


def _money_text(session: Session, org_id: str, v: float) -> str:
    """An engine (EUR) amount written into a hint, in the organisation's currency (closing rate)."""
    from services.governance.display_currency import balance, view
    return balance(v, view(session, org_id))


def _amount(v):
    """A KRI money value as computed — a gap stays None (shown as not computed), never 0."""
    return None if v is None else round(v)


def _millions(v) -> str:
    return "—" if v is None else f"{round(v / 1e6, 1)}m"


def _kpi(key, label, value, fmt, tone=None, hint=None, integrated=False, integrated_note=None):
    # `integrated` = a regulator datapoint whose value comes from OUTSIDE this engine (e.g. GHG from the
    # customer's carbon tool, or Taxonomy alignment flags) — shown honestly rather than fabricated or blanked.
    # `kind` makes the data provenance explicit for the dashboard's computed-vs-integrated legend/filter.
    # It mirrors the canonical datapoint catalog's `coverage_source(lane)`: our engine + processed uploads
    # (compute/granular) → "computed"; a pre-calculated value the customer/vendor brings in (provided) →
    # "integrated". This is the SAME `integrated` flag that already drove the honest "—" rendering, now
    # surfaced as a first-class classification so every KRI is labelled ours-vs-brought-in.
    return {"key": key, "label": label, "value": value, "fmt": fmt, "tone": tone, "hint": hint,
            "integrated": integrated, "integrated_note": integrated_note,
            "kind": "integrated" if integrated else "computed",
            **({"flow": key in FLOW_KRIS} if fmt == "eur" else {})}


# the frameworks with a KRI builder, and their short picker labels (one org-type can report several)
# (each set is anchored on its governed report — the bank's in services.governance.kri_bank, the REIT / insurer /
# asset-manager sets in services.governance.kri_sectors)
_KRI_LABELS = {"bank_tcfd": "EU Taxonomy Art. 8", "bank_p3esg": "Pillar 3 ESG", "sfdr_pai": "SFDR PAI",
               "reit_taxonomy": "EU Taxonomy · property", "insurer_solvency": "Solvency II · nat-cat",
               "esrs_pack": "ESRS E1·E3·E4"}


def kri_frameworks(org_type: str | None) -> list[dict]:
    """The KRI frameworks an org-type can report on — the picker options on the KRI dashboard."""
    from services.governance.filings import available_frameworks
    return [{"framework": f["framework"], "label": _KRI_LABELS[f["framework"]]}
            for f in available_frameworks(org_type or "") if f["framework"] in _KRI_LABELS]


def kri(session: Session, org_id: str, framework: str, entity_id: str | None = None) -> dict:
    """entity_id: the undertaking an ESRS KRI set is for (services.governance.kri_esrs.undertaking); other sets are the
    organisation's book."""
    if framework == "bank_tcfd":                       # anchored on the report each set belongs to (kri_bank, E95)
        from services.governance.kri_bank import taxonomy_kri
        result = taxonomy_kri(session, org_id)
    elif framework == "bank_p3esg":
        from services.governance.kri_bank import pillar3_kri
        result = pillar3_kri(session, org_id)
    elif framework == "sfdr_pai":
        from services.governance.kri_sectors import holdings_kpis, sfdr_kri
        result = sfdr_kri(session, org_id)
        held, by_hazard = holdings_kpis(session, org_id)          # the holdings book's KRIs: live only
        result["kpis"] = result["kpis"] + held
        result["by_hazard"] = result.get("by_hazard") or by_hazard
    elif framework == "reit_taxonomy":
        from services.governance.kri_sectors import reit_kri
        result = reit_kri(session, org_id)
    elif framework == "insurer_solvency":
        from services.governance.kri_sectors import insurer_kri
        result = insurer_kri(session, org_id)
    elif framework == "esrs_pack":
        from services.governance import kri_esrs
        result = kri_esrs.build(session, org_id, entity_id)
    else:
        return {"framework": framework, "supported": False,
                "message": "No KRI dashboard for this framework yet."}
    # grade every KPI against the org's appetite bands → green / amber / red (a monitored control, not a number)
    if result.get("supported") and result.get("kpis"):
        from services.governance import kri_regmap, kri_thresholds
        kri_thresholds.apply(session, org_id, result["framework"], result["kpis"])
        result["breaches"] = sum(1 for k in result["kpis"] if k.get("breached"))
        # regulator framing: name the supervisor/disclosure, tag each KRI with the datapoint it feeds, and
        # summarise submission-readiness (which core datapoints the regulator expects are covered)
        result["regulator"] = kri_regmap.regulator(result["framework"])
        result["readiness"] = kri_regmap.annotate(result["framework"], result["kpis"])
        # Fixed 2026-09-24 (platform-wide E2E audit finding #5, confirmed independently across bank,
        # insurer, agri and asset-manager KRI): the KPI cards above are live-recomputed from the CURRENT
        # book/basis on every call, not read from the last filed snapshot — only `history` reads frozen
        # data (this module's own docstring already disclosed the design in code, but nothing on the
        # dashboard itself said so). A viewer could read a live number as "what we told the regulator" when
        # it may have moved since. Surface it explicitly rather than silently — never hide the distinction.
        hist = result.get("history") or []
        result["basis"] = {
            "kpis": "live",
            "note": "These figures reflect the current book and reporting basis, recomputed live — not "
                    "necessarily the number last filed with the regulator. See the trend/history for what "
                    "was actually filed.",
            "last_filed": ({"period_label": hist[-1]["label"], "filing_id": hist[-1]["filing_id"]}
                           if hist else None),
        }
    return result


def _by_hazard(snap: dict) -> list[dict]:
    return sorted([{"hazard": h, "value": b.get("exposed_value_eur", 0), "score": b.get("max_score", 0)}
                   for h, b in (snap.get("by_hazard") or {}).items() if (b.get("exposed_value_eur") or 0) > 0],
                  key=lambda x: -x["value"])


# noun per framework for the hazard drill
_NOUN = {"bank_tcfd": "assets", "bank_p3esg": "assets", "reit_taxonomy": "properties", "insurer_solvency": "policies",
         "sfdr_pai": "holdings"}


def _live_snapshot(session: Session, org_id: str, framework: str, scenario: str, horizon: str) -> dict:
    if framework in ("bank_tcfd", "bank_p3esg"):
        from api.routers.bank import build_disclosure_snapshot
    elif framework == "reit_taxonomy":
        from api.routers.realestate import build_disclosure_snapshot
    elif framework == "insurer_solvency":
        from api.routers.insurance import build_disclosure_snapshot
    elif framework == "sfdr_pai":                       # the holdings book behind the asset manager's live KRIs
        from api.routers.assetmgmt import build_disclosure_snapshot
    else:
        return {}
    return build_disclosure_snapshot(session, org_id, scenario, horizon)


def kri_hazard(session: Session, org_id: str, framework: str, hazard: str, entity_id: str | None = None) -> dict:
    """The entities contributing a hazard's exposure (live) — the drill under a KRI by-hazard bar."""
    from services.governance.filing_lineage import _LIST_CFG
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    cfg = _LIST_CFG.get("assetmgmt_tcfd" if framework == "sfdr_pai" else framework)   # sfdr_pai: its holdings book
    if cfg:
        snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"])
        from services.governance.pillar3_templates import hazard_hit, stated_level
        level = stated_level(snap)
        if level is None:
            return {"supported": True, "hazard": hazard, "noun": _NOUN.get(framework, "items"), "entities": [],
                    "gap": "not stated: method.at_risk_level"}
        ents = []
        for e in snap.get(cfg["list"], []):
            hz = next((h for h in e.get("hazards", []) if h.get("hazard") == hazard and hazard_hit(h, level)), None)
            if hz:
                ents.append({"name": e.get(cfg["name"]), "value": e.get(cfg["value"]),
                             "h3_cell": e.get("h3_cell"), "country": e.get("country"), "score": hz.get("score")})
        ents.sort(key=lambda x: -(x["value"] or 0))
        return {"supported": True, "hazard": hazard, "noun": _NOUN.get(framework, "items"), "entities": ents[:100]}
    if framework == "esrs_pack":
        from services.governance import kri_esrs
        return {"supported": True, "hazard": hazard, "noun": "own sites (short term, carrying amount)",
                "entities": kri_esrs.hazard_sites(session, org_id, hazard, entity_id)[:100]}
    return {"supported": False, "hazard": hazard, "entities": []}


# ── KRI drill-down: the underlying data + methodology + trend + composition behind one KRI ──────────────
# Exposure KRIs decompose by hazard; the rest by their own natural breakdown (emissions by scope, coverage
# scored/unscored, taxonomy eligible/not). Everything here is derived from the SAME live snapshot the KRI
# tile is computed from — no separate or fabricated data.
_EXPOSURE_KEYS = {"total_value", "value_at_risk", "pct_at_risk", "sum_insured", "eal", "value_exposed",
                  "e1.physrisk.assets.amount", "e1.physrisk.assets.pct"}           # the ESRS ones: kri_esrs.EXPOSURE
_HIST_FIELD = {"total_value": "total_value", "value_at_risk": "value_at_risk", "pct_at_risk": "pct_at_risk"}


def _esrs_hist(key: str) -> str | None:
    from services.governance.kri_esrs import HISTORY
    return HISTORY.get(key)


def _esrs_methodology(key: str) -> str | None:
    from services.governance.kri_esrs import methodology
    return methodology(key)
# forward-looking + physical-split KRIs also earn the "explore forward in Analytics" action
_FORWARD_KEYS = {"forward_share", "acute_share", "chronic_share"}

# Plain-language, factual "how it's computed" per KRI. Where a key is absent the UI falls back to the tile's
# own hint. Written to be honest about calibration gates and integrated (client-provided) datapoints.
_METHODOLOGY = {
    "total_value": "Total euro exposure of the book in scope for this filing, summed from your uploaded book.",
    "value_at_risk": "Value of the book whose headline hazard score is at or above the institution's stated level of material physical risk (method.at_risk_level), in euro. A gap until that level is stated.",
    "pct_at_risk": "Value at risk as a share of total book value.",
    "acute_share": "Share of the book in the top two bands (High + Very High) whose driver is an ACUTE, event-driven peril — flood, storm, wildfire, frost, acute heat. This is the sudden-loss / provisioning lens of Pillar 3 Template 5; an exposure can also count as chronic.",
    "chronic_share": "Share of the book in the top two bands whose driver is a CHRONIC, gradual peril — drought, chronic heat, coastal/sea-level, water stress. This is the long-run repricing lens of Template 5; the acute and chronic shares overlap where an exposure faces both.",
    "forward_share": "Projected share of the book crossing the stated at-risk level at the furthest modelled horizon under a warming pathway (per your reporting-settings scenario, or Disorderly 2°C). The forward early-warning to compare against today's point-in-time share.",
    "sector_concentration": "Share of the book in the EBA high-climate-impact sectors (NACE sections A–H and L), with the single most-concentrated sector called out. Concentration in these sectors is the axis Pillar 3 Templates 1 & 5 are organised around and a standard prudential concentration control.",
    "p3_alignment": "Pillar 3 Template 3 / EU CRFR4 (pending adoption) — the gross-weighted distance of the book's counterparty CO₂-intensity to the IEA Net-Zero-by-2050 2030 pathway per sector: 100×((current intensity − IEA 2030 target)/IEA 2030 target). Tellumen holds the IEA benchmark and does the calculation; the counterparty physical intensity (gCO₂/kWh, tCO₂/t…) is a vendor/counterparty feed, so this reads '—' until that feed is provided. A TCFD-not-required, Pillar-3-specific indicator.",
    "p3_top20": "Pillar 3 Template 4 (in force under ITS 2024/3172; removed by the EBA final draft EBA/ITS/2026/02 once adopted) — share of the book lent to the world's 20 most carbon-intensive companies (the Carbon Majors list), matched by counterparty identity. Policy action against top emitters can deteriorate their creditworthiness, so this is a concentrated transition-credit indicator prescribed by Pillar 3 (not TCFD).",
    "coverage": "Share of the book carrying a physical-risk score on the golden source. Unscored exposure is excluded from the risk figures, never assumed safe.",
    "fin_emissions": "PCAF-attributed financed emissions (Scope 1–3, tCO₂e): counterparty emissions (reported, or a "
                     "NACE-intensity estimate where a counterparty figure is missing), weighted per loan by the "
                     "PCAF attribution factor (outstanding loan balance ÷ counterparty EVIC, capped at 100%). "
                     "Counterparty EVIC is a required loan-tape field for new uploads; a loan on record without "
                     "it contributes nothing to this figure and is counted separately, never folded in unweighted.",
    "taxonomy": "EU Taxonomy Article 8 eligible share — the portion of the book in Taxonomy-eligible activities (the GAR numerator's eligibility leg), from your book's activity classification.",
    "gar": "The Green Asset Ratio needs the Taxonomy-ALIGNED share (substantial contribution + DNSH + minimum safeguards) that you determine per exposure. Only eligibility is computed here; alignment is your input, so this reads '—' until provided.",
    "noi_impact": "Physical-risk drag on net operating income — the modelled climate insurance premium as a share of NOI.",
    "sum_insured": "Total sum insured across the underwriting book in scope.",
    "eal": "Expected annual loss — probability-weighted scenario loss across the book, from the CLIMADA-style mean-damage-ratio × per-peril occurrence frequency.",
    "loss_ratio": "Modelled claims-vs-premiums (NatCat loss ratio) implied by the current hazard exposure of the book.",
    "pai_emissions": "SFDR PAI 1 — total financed GHG emissions (Scope 1–3, tCO₂e) across the fund's value-weighted holdings.",
    "carbon_footprint": "SFDR PAI 2 — financed emissions per €M invested.",
    "waci": "SFDR PAI 3 — weighted-average carbon intensity (tCO₂e per €M investee revenue).",
    "fossil_fuel": "SFDR PAI 4 — share of fund value in companies active in the fossil-fuel sector.",
    "non_renewable": "SFDR PAI 5 — share of non-renewable energy consumption / production.",
}


def _filed_value(h: dict, kri_key: str, hf: str | None):
    """A KRI's value in one filed period: the legacy history slot, or the figure the anchor report printed."""
    if hf and h.get(hf) is not None:
        return h.get(hf)
    return next((f["value"] for f in h.get("figures") or [] if f["key"] == kri_key), None)


def kri_detail(session: Session, org_id: str, framework: str, kri_key: str, entity_id: str | None = None) -> dict:
    """The drill behind one KRI tile: the tile itself (value, appetite, provenance, regulator datapoint),
    a plain-language methodology, its trend across filed history where tracked, and its composition
    (by-hazard / by-scope / scored-unscored / eligible-not) — all from the same live snapshot."""
    result = kri(session, org_id, framework, entity_id)
    if not result.get("supported"):
        return {"supported": False, "message": result.get("message", "unsupported")}
    kpi = next((k for k in result.get("kpis", []) if k["key"] == kri_key), None)
    if not kpi:
        return {"supported": False, "message": "unknown KRI"}
    hf = _HIST_FIELD.get(kri_key) or (_esrs_hist(kri_key) if framework == "esrs_pack" else None)
    trend = [{"label": h["label"], "value": _filed_value(h, kri_key, hf), "filing_id": h.get("filing_id")}
             for h in (result.get("history") or []) if _filed_value(h, kri_key, hf) is not None]
    if kpi.get("live_only"):                          # no governed report prints it: no filed trend (E87)
        trend = []
    return {
        "supported": True, "framework": framework, "kpi": kpi,
        "regulator": result.get("regulator"),
        "methodology": _METHODOLOGY.get(kri_key) or (_esrs_methodology(kri_key) if framework == "esrs_pack" else None),
        "trend": {"points": trend, "fmt": kpi.get("fmt"), "flow": bool(kpi.get("flow"))},
        "projection": _kri_projection(session, org_id, framework, kri_key, kpi),
        "composition": _kri_composition(session, org_id, framework, kri_key, result),
        "drivers": _kri_drivers(session, org_id, framework, kri_key),
        "actions": {
            "analytics": (kri_key in _EXPOSURE_KEYS or kri_key in _FORWARD_KEYS) and framework in ("bank_tcfd", "bank_p3esg", "reit_taxonomy"),
            "provide": kpi.get("kind") == "integrated",
        },
    }


# Physical/forward KRIs get a forward trajectory chart (value across horizons under a warming pathway, with
# an act-vs-inaction band and the appetite thresholds) — the "when do we cross appetite" decision view.
_PROJECTION_KEYS = {"value_at_risk", "pct_at_risk", "forward_share"}


def _kri_projection(session: Session, org_id: str, framework: str, kri_key: str, kpi: dict) -> dict | None:
    if kri_key not in _PROJECTION_KEYS or framework not in ("bank_tcfd", "bank_p3esg", "reit_taxonomy"):
        return None
    try:
        from services.governance.reporting_settings import get_settings
        from services.intelligence.forward_risk import forward_risk
        from services.money.params import for_org
        vert = {"reit_taxonomy": "realestate"}.get(framework, "banking")
        s = get_settings(session, org_id)
        scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
        fr = forward_risk(session, org_id, vert, scen, for_org(session, org_id))
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
        return {"points": pts, "unit": "pct" if is_pct else "eur",
                "warn": kpi.get("amber"), "breach": kpi.get("red"),
                "scenario": scen.replace("_", " "),
                "note": "Central estimate of value at or above the stated at-risk level across horizons under " + scen.replace("_", " ")
                        + "; the shaded band is the CMIP6/AR6 climate-model uncertainty range (lower–upper "
                        + "confidence bound of the hazard scores), not a best/worst policy case."}
    except Exception:  # noqa: BLE001 — a missing projection must not break the drawer
        return None


# KRIs whose most-granular drill is the individual exposures (assets) behind the number.
_DRIVER_KEYS = {"total_value", "value_at_risk", "pct_at_risk", "acute_share", "chronic_share",
                "forward_share", "sector_concentration", "fin_emissions"}


def _kri_drivers(session: Session, org_id: str, framework: str, kri_key: str,
                 seg_type: str | None = None, seg_value: str | None = None) -> dict | None:
    """The most granular view: the individual exposures (assets) behind a KRI, largest-contribution first —
    the actual names a risk officer acts on, each carrying its asset id so the row opens the asset detail.
    Without a segment, the filter follows the KRI. With a segment (from a click on a composition bar) the
    filter narrows to that slice: seg_type 'scope' (emissions Scope 1/2/3), 'hazard' (at or above the stated level on one peril),
    or 'sector' (one NACE section). Only for bank/REIT books; never fabricated."""
    if framework not in ("bank_tcfd", "bank_p3esg", "reit_taxonomy"):
        return None
    if not seg_type and kri_key not in _DRIVER_KEYS:
        return None
    from services.governance.pillar3_templates import (
        HIGH_CLIMATE_NACE,
        _asset_hits,
        _section,
        hazard_hit,
        stated_level,
    )
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"])
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
        def keep(a):
            return (a.get(f"ghg{seg_value}") or 0) > 0
        def weight(a):
            return a.get(f"ghg{seg_value}") or 0
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
            # per-asset PCAF-attributed emissions -- an asset with no EVIC has no attributed value (0, excluded
            # below), the same rule the pooled figure uses; never mixes an unattributed asset into this drill.
            from services.scoring.pcaf import attribution_factor
            af = attribution_factor(a.get("outstanding_loan_balance_eur"), a.get("evic_eur"))
            return af * sum((a.get(f"ghg{i}") or 0) for i in (1, 2, 3)) if af is not None else 0.0
        weight = _pcaf_weight if kri_key == "fin_emissions" else _val
        unit = "num" if kri_key == "fin_emissions" else "eur"

    rows = [a for a in assets if keep(a) and weight(a) > 0]
    rows.sort(key=weight, reverse=True)
    items = [{
        "id": a.get("asset_id") or a.get("property_id"),
        "name": a.get("asset_name") or a.get("property_name") or a.get("asset_id") or a.get("property_id"), "sector": a.get("sector"),
        "country": a.get("country"), "nace": a.get("nace_code"),
        "value": round(weight(a)), "hazard": a.get("headline_hazard"),
        "bucket": a.get("headline_bucket"), "score": a.get("headline_score"),
    } for a in rows[:8]]
    return {"unit": unit, "total_count": len(rows), "items": items} if items else None


def _kri_composition(session: Session, org_id: str, framework: str, kri_key: str, result: dict) -> dict | None:
    """The real breakdown behind a KRI — never fabricated; returns None when no honest decomposition exists."""
    if kri_key in _EXPOSURE_KEYS and result.get("by_hazard"):
        return {"type": "hazard", "unit": "eur",
                "items": [{"label": h["hazard"], "value": h["value"], "score": h.get("score")}
                          for h in result["by_hazard"]]}
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"])
    if not snap:
        return None
    if kri_key == "fin_emissions":
        em = snap.get("financed_emissions_tco2e", {}) or {}
        # the scopes stated; a scope nobody states is left out, never drawn as 0 (E76)
        items = [{"label": f"Scope {i}", "value": round(em[f"scope{i}"])} for i in (1, 2, 3) if em.get(f"scope{i}") is not None]
        return {"type": "scope", "unit": "num", "items": items} if items else None
    if kri_key == "coverage":
        r = snap.get("rollup", {}) or {}
        n, sc = r.get("n_assets") or 0, r.get("n_scored") or 0
        return {"type": "coverage", "unit": "num",
                "items": [{"label": "Scored", "value": sc}, {"label": "Not yet scored", "value": max(0, n - sc)}]} if n else None
    if kri_key == "taxonomy" and framework != "reit_taxonomy":   # the REIT figure is turnover-based, not this value split
        tax = snap.get("taxonomy", {}) or {}
        elig = (tax.get("eligible") or {}).get("value_eur", 0) or 0
        total = sum((v or {}).get("value_eur", 0) or 0 for v in tax.values())
        return {"type": "taxonomy", "unit": "eur",
                "items": [{"label": "Eligible", "value": round(elig)}, {"label": "Not eligible", "value": round(max(0, total - elig))}]} if total else None
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
        items = sorted(({"label": k, "value": round(v)} for k, v in by_h.items()), key=lambda x: -x["value"])
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
            ({"label": f"{sec} · {NACE_SECTIONS.get(sec, 'Unclassified')}"[:34], "value": round(val)}
             for sec, val in cs["by_sector"].items() if sec in HIGH_CLIMATE_NACE),
            key=lambda x: -x["value"])
        return {"type": "sector", "unit": "eur", "items": items} if items else None
    # forward share — the projected at-risk trajectory across horizons under the warming pathway
    if kri_key == "forward_share":
        try:
            from services.intelligence.forward_risk import forward_risk
            from services.money.params import for_org
            scen = s["scenario"] if s.get("scenario") and s["scenario"] != "baseline" else "disorderly_2c"
            traj = forward_risk(session, org_id, "banking", scen, for_org(session, org_id)).get("trajectory") or []
            items = [{"label": t.get("horizon"), "value": t.get("at_risk_pct") or 0} for t in traj]
            return {"type": "horizon", "unit": "pct", "items": items} if len(items) >= 2 else None
        except Exception:  # noqa: BLE001
            return None
    return None


def _snapshot_history(session: Session, org_id: str, framework: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT rs.version, rs.reporting_basis, rs.payload, rf.period_label, rf.filing_id::text AS filing_id
        FROM report_snapshots rs
        JOIN regulatory_filing rf ON rf.snapshot_id = rs.snapshot_id
        WHERE rs.org_id = :o AND rs.report_type = :fw
        ORDER BY rf.period_end, rs.version
    """), {"o": org_id, "fw": framework}).mappings().all()
    out = []
    for r in rows:
        p = r["payload"]
        if isinstance(p, str):
            p = json.loads(p)
        out.append({"label": f'{r["period_label"]} v{r["version"]}', "payload": p, "filing_id": r["filing_id"]})
    return out
