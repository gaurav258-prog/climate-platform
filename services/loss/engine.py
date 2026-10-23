"""The loss engine (E171): one recorded loss run per organisation, book, scenario and horizon — every asset and peril
walked through the same decision tree, each result a figure with its range and standing, or the named gap that
stopped it.

  1  method adopted?      the institution's adopted curve family for the peril (calc settings loss_curve_family_*) → gap;
                          first, because a run reads the hazard only for a peril with adopted curves (E324)
  2  intensity here?      the layer's samples at the asset (services.loss.intensity) — none, or outside coverage → gap
  3  use known?           the stated occupancy, else the declared crosswalk (services.loss.registry.occupancy_of) → gap
  4  curve here?          the adopted family's curve for that use in the asset's country → gap
  5  value stated?        the asset's value (portfolio_entities.primary_value_eur) → gap
  6  figure               per return period: value × the cell's flooded share × the damage ratio at the cell's flooded
                          depth (flood), or value × the damage ratio at the point's wind (storm); central from the curve,
                          low and high from the curve's band; expected annual loss = the area under the loss–exceedance
                          curve from the most frequent return period the layer holds to the rarest, the rarest loss held
                          beyond it (more frequent events are not in the maps and are not counted — stated in the run)
  7  standing             the family's held-out test under data/reference/loss_protocol.json: passed → published,
                          failed → held (shown, never used), no test where the asset is → untested
  8  defences (flood)     the published protection standard at the location (services.loss.protection; the product
                          owner's decisions of 2026-10-16): the defended figure beside the undefended one — damage from
                          floods more frequent than the design level set to 0 — or, off the protection map, the
                          undefended figure labelled 'protection unknown'
Which flood map serves an asset: a layer registered to replace the global maps (the JRC European maps, nine return
periods) serves an asset in its coverage countries once its check let it into use; elsewhere, and where it does not
reach the location, the global maps.
The book's exceedance curve adds only published figures, on the basis the institution states (loss_flood_dependence);
with none, the curve is a named gap.

The issuer-sites book (the holdings look-through, the product owner's decisions of 2026-10-22) walks the located sites of
the issuers an organisation's funds hold through the same tree. A site states no value of its own — only its weight, a
share of the issuer — so its figure is the share of the value its curve applies to (a value of 1), recorded in the share
columns; a head-office proxy (services.reference.footprint) is not a site of the issuer's physical assets and is a named
gap first. Its figures are weighted into the issuer's share, and into euros on a holding, by services.loss.lookthrough.

A projected run (assess_projected; the product owner's decisions of 2026-10-07, recorded with the aqueduct_river_flood
layer) reads the published projection's own depths for the scenario's pathway and the horizon's period, one figure per
climate model: the middle model is the central figure, the models' lowest and highest the range, and the same source's
present-day figure stands beside it — the only figure a projected loss is compared with. A scenario or horizon the source
does not publish, and any peril without a registered projection, is a named gap."""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.loss import curves, gaps, protection, registry

ENGINE_VERSION = "loss-v1"
LAYERS = {"flood": "jrc_river_flood", "storm": "storm_v4_wind"}
BOOKS = ("banking", "insurance", "insurer_investments", "realestate", "assetmgmt", "company_sites", "issuer_sites")
SHARE_BOOKS = ("issuer_sites",)       # books whose figures are a share of value: no site states a value of its own
SCENARIOS = ("baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c")
HORIZONS = ("current", "2030", "2050", "2100")     # the platform's horizons (the one timeline, 2026-10-22)


PRESENT = {"scenario": "present", "period": "present", "climate_model": ""}
PROJECTED_FLOOD = "aqueduct_river_flood"


def _samples(session: Session, layer_key: str, version: str, lat: float, lon: float,
             variant: Optional[dict] = None) -> dict[int, dict]:
    v = variant or PRESENT
    return {r["rp_years"]: dict(r) for r in session.execute(text("""
        SELECT rp_years, status, value, cell_fraction, cell_mean, caution FROM hazard_intensity_samples
        WHERE layer_key = :k AND layer_version = :v AND latitude = :la AND longitude = :lo
          AND scenario = :s AND period = :p AND climate_model = :m"""),
        {"k": layer_key, "v": version, "la": lat, "lo": lon, "s": v["scenario"], "p": v["period"],
         "m": v["climate_model"]}).mappings()}


def _band_at(curve: dict, x: float, central: float) -> tuple[float, float]:
    """(low, high) damage ratio at intensity x:
      measured curve   the band holding x (its claims' 10th–90th percentile)
      published curve  the publisher's standard deviation at x (linear between its points, the last held beyond):
                       central ± one standard deviation, bounded to [0, 1]
      none published   no range of its own: (central, central)"""
    for b in curve.get("bands") or []:
        if b["from_m"] < x <= b["to_m"]:
            return b["p10"], b["p90"]
    bands = curve.get("bands") or []
    if bands and x > bands[-1]["to_m"]:
        return bands[-1]["p10"], bands[-1]["p90"]
    if curve.get("sd"):
        sd = curves.ratio(curve["sd"], x) if x > curve["sd"][0][0] else curve["sd"][0][1]
        return max(0.0, central - sd), min(1.0, central + sd)
    if curve.get("spread") == "none published":
        return central, central
    raise ValueError("no band")


def eal(losses: dict[int, float]) -> float:
    """Area under the loss–exceedance curve over the return periods held: trapezoids in annual exceedance probability
    between consecutive return periods, the rarest loss held beyond the rarest return period."""
    rps = sorted(losses)
    p = [1.0 / rp for rp in rps]
    out = sum((p[i] - p[i + 1]) * (losses[rps[i]] + losses[rps[i + 1]]) / 2 for i in range(len(rps) - 1))
    return out + p[-1] * losses[rps[-1]]


def standing(family: dict, country: str, curve: Optional[dict] = None) -> str:
    """The figure's standing under data/reference/loss_protocol.json: a curve tested on its own (published_curve_test)
    is published or held by that test; otherwise the family's test where it covers the country; otherwise untested."""
    if curve is not None and curve.get("test"):
        return "published" if curve["test"].get("passed") else "held"
    t = family.get("test")
    if not t:
        return "untested"
    tested = set(t.get("countries") or [c for cur in family["curves"] for c in cur["countries"]])
    if country not in tested:
        return "untested"
    return "published" if t.get("passed") else "held"


# Where each book states the BUILDING's own value (land excluded) — what a building damage curve's share is taken of —
# and, where it cannot, the message saying why not. A market, appraised or position value is never read as one.
_BUILDING_VALUE = {
    "banking": ("LEFT JOIN ext_banking x ON x.entity_id = e.entity_id", "x.building_value_eur", "loss.gap.no_building_value"),
    "insurance": ("LEFT JOIN ext_insurance x ON x.entity_id = e.entity_id", "x.building_value_eur", "loss.gap.no_building_value"),
    "realestate": ("LEFT JOIN ext_realestate x ON x.entity_id = e.entity_id", "x.building_value_eur", "loss.gap.no_building_value"),
    "assetmgmt": ("", "NULL", "loss.gap.not_a_building"),
    "insurer_investments": ("", "NULL", "loss.gap.not_a_building"),
}
# Where each book states the asset's PHYSICAL value — what an asset-value curve's share is taken of (the cyclone curves:
# Eberenz 2021's exposure is produced capital, buildings and contents, land excluded) — and why not where it cannot (the
# product owner's decision of 2026-10-21, E307): an insurer's insured building and contents (business interruption is
# not a physical asset), a bank's or property trust's building value; a holding or an investment is never one. Read over
# the same join as the building value; a market, appraised, exposure or position value is never read as one.
_ASSET_VALUE = {
    "banking": ("x.building_value_eur", "loss.gap.asset_value_not_stated"),
    "insurance": ("NULLIF(COALESCE(x.building_value_eur, 0) + COALESCE(x.contents_value_eur, 0), 0)",
                  "loss.gap.asset_value_not_stated"),
    "realestate": ("x.building_value_eur", "loss.gap.asset_value_not_stated"),
    "assetmgmt": ("NULL", "loss.gap.not_a_building"),
    "insurer_investments": ("NULL", "loss.gap.not_a_building"),
}


def _assets(session: Session, org_id: str, book: str) -> list[dict]:
    if book == "issuer_sites":                # which sites, and the head-office proxy: the look-through's to say
        from services.loss.lookthrough import held_sites
        return held_sites(session, org_id)
    if book == "company_sites":
        return [{**dict(r), "asset_kind": "company_site", "value": None, "building_value": None, "asset_value": None,
                 "no_building_value": "loss.gap.site_value_not_stated", "no_asset_value": "loss.gap.site_value_not_stated",
                 "table": "sc_company_sites.site_type"}
                for r in session.execute(text("""
                    SELECT site_id::text AS asset_id, latitude, longitude, country, occupancy, site_type AS asset_type
                    FROM sc_company_sites WHERE org_id = CAST(:o AS uuid)"""), {"o": org_id}).mappings()]
    join, col, why = _BUILDING_VALUE[book]
    acol, awhy = _ASSET_VALUE[book]
    position = col == "NULL" and acol == "NULL"          # a book of holdings: no curve applies, whatever else is stated
    return [{**dict(r), "asset_kind": "portfolio_entity", "table": "portfolio_entities.entity_type", "no_building_value": why,
             "no_asset_value": awhy, "position": position}
            for r in session.execute(text(f"""
                SELECT e.entity_id::text AS asset_id, e.latitude, e.longitude, e.country, e.occupancy,
                       e.entity_type AS asset_type, CAST(e.primary_value_eur AS FLOAT) AS value,
                       CAST({col} AS FLOAT) AS building_value, CAST({acol} AS FLOAT) AS asset_value
                FROM portfolio_entities e {join}
                WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = :b AND e.source = 'own'"""),
                {"o": org_id, "b": book}).mappings()]


def _value_for(asset: dict, family: dict) -> tuple[Optional[float], Optional[str]]:
    """(the value the family's ratio is a share of, or None; the message code of the reason when None). An issuer's site
    states no value: it is read on a value of 1 — the figure is the share lost of the value the family's basis names."""
    if asset.get("per_unit"):
        return 1.0, None
    basis = family.get("damage_basis") or "building"
    if basis == "building":
        v = asset.get("building_value")
        return (v, None) if v and v > 0 else (None, asset["no_building_value"])
    if basis == "asset_value":
        v = asset.get("asset_value")
        return (v, None) if v and v > 0 else (None, asset["no_asset_value"])
    return None, "loss.gap.curves_not_usable"


@lru_cache(maxsize=1)
def _countries() -> frozenset[str]:
    """ISO alpha-2 codes that are countries (ref_countries.is_country): a grouping such as 'EU' is not (E154)."""
    from core.db.config import SessionLocal
    s = SessionLocal()
    try:
        return frozenset(r[0].strip() for r in s.execute(text("SELECT iso2 FROM ref_countries WHERE is_country")).all())
    finally:
        s.close()


def _resolve(session: Session, asset: dict, peril: str, family_key: Optional[str], base: dict):
    """Steps 2–5: (base, None) with base['gap'] set, or (base, {family, curve, value, country})."""
    if not family_key:
        return {**base, **gaps.gap("loss.gap.no_curves_chosen", peril=gaps.peril_name(peril))}, None
    family = curves.families().get(family_key)
    if family is None:             # registered but refused (curves.refused() says why, for the methods page)
        return {**base, **gaps.gap("loss.gap.curves_not_usable", peril=gaps.peril_name(peril))}, None
    if asset.get("position"):      # the first reason a holding has no figure: it is not a physical asset (E307)
        return {**base, **gaps.gap(asset["no_asset_value"])}, None
    occ, _why = registry.occupancy_of(asset.get("occupancy"), asset["table"], asset.get("asset_type"))
    if occ is None:
        return {**base, **gaps.occupancy(asset.get("asset_type"))}, None
    base = {**base, "occupancy": occ}
    country = (asset.get("country") or "").strip().upper()
    if country not in _countries():
        return {**base, **gaps.country(session, asset, country)}, None
    curve = curves.curve_for(family_key, occ, country)
    if curve is None:
        return {**base, **gaps.gap("loss.gap.no_curve", use=occ, country=gaps.country_name(country))}, None
    base = {**base, "curve_key": curve["key"]}
    value, why = _value_for(asset, family)
    if value is None:
        return {**base, **gaps.gap(why)}, None
    return {**base, "exposed_value_eur": value}, {"family": family, "curve": curve, "value": value, "country": country}


def _rp_figures(curve: dict, value: float, s: dict[int, dict], peril: str,
                per: float = 1.0) -> tuple[Optional[dict], Optional[dict]]:
    """Step 6 per return period: {rp: (low, central, high)}, or the gap that stopped it. A layer's value is read in the
    curve's own metric by the registered divisor `per` (registry.divisor: 1 for the layer's own metric)."""
    rows = {}
    for rp, r in sorted(s.items()):
        if peril == "flood":
            share, depth = (r["cell_fraction"] or 0.0), (r["cell_mean"] or 0.0)
            if share == 0 or depth <= 0:
                rows[rp] = (0.0, 0.0, 0.0)
                continue
            central = curves.ratio(curve["points"], depth)
            try:
                lo, hi = _band_at(curve, depth, central)
            except ValueError:
                return None, gaps.gap("loss.gap.no_damage_range", depth=f"{depth:.2f}")
            rows[rp] = (value * share * min(lo, central), value * share * central, value * share * max(hi, central))
        else:
            ratio = curves.ratio(curve["points"], float(r["value"] or 0.0) / per)
            rows[rp] = (value * ratio, value * ratio, value * ratio)
    return rows, None


CENTS, SHARE_PLACES = 2, 12          # a euro figure to the cent; a share of value to twelve decimals


def _summary(rows: dict, places: int = CENTS) -> dict:
    low, central, high = ({rp: v[i] for rp, v in rows.items()} for i in range(3))
    return {"eal_eur": round(eal(central), places), "eal_low_eur": round(eal(low), places),
            "eal_high_eur": round(eal(high), places),
            "loss_at_rp": {str(rp): {"low": round(low[rp], places), "central": round(central[rp], places),
                                     "high": round(high[rp], places)} for rp in sorted(rows)}}


# An issuer site's figure — computed on a value of 1 — is recorded in the share columns, never as euros.
_SHARE = {"eal_eur": "eal_ratio", "eal_low_eur": "eal_ratio_low", "eal_high_eur": "eal_ratio_high",
          "eal_defended_eur": "eal_defended_ratio", "eal_defended_low_eur": "eal_defended_ratio_low",
          "eal_defended_high_eur": "eal_defended_ratio_high", "loss_at_rp": "ratio_at_rp"}


def _as_share(out: dict) -> dict:
    return {**{_SHARE.get(k, k): v for k, v in out.items()}, "exposed_value_eur": None}


def replacement(peril: str, country: str) -> Optional[str]:
    """The layer in use that replaces the peril's global layer for an asset stated in `country`, or None."""
    for k, L in registry.layers().items():
        if (L.get("replaces") == LAYERS[peril] and L.get("status") == "in_use"
                and country in registry.coverage_countries(k)):
            return k
    return None


def _present_samples(session: Session, asset: dict, peril: str, lat: float, lon: float) -> tuple[str, str, dict]:
    """(layer key, version, samples) of the map that serves this asset today: the replacing layer where it is in use
    for the asset's country and reaches the location, else the peril's global layer."""
    k = replacement(peril, (asset.get("country") or "").strip().upper())
    if k:
        L = registry.layer(k)
        s = _samples(session, k, L["version"], lat, lon)
        if not s or all(r["status"] == "sampled" for r in s.values()):
            return k, L["version"], s
    k = LAYERS[peril]
    v = registry.layer(k)["version"]
    return k, v, _samples(session, k, v, lat, lon)


def _defences(session: Session, lat: float, lon: float, rows: dict, places: int = CENTS) -> dict:
    """Step 8: the defended figure beside the undefended one, or the reason there is none."""
    rp, code = protection.at(session, lat, lon)
    if rp is None:
        return gaps.protection(code)
    low, central, high = ({k: v[i] for k, v in rows.items()} for i in range(3))
    return {"protection_rp_years": rp, **gaps.protection(code, rp),
            "eal_defended_eur": round(protection.defended_eal(central, rp), places),
            "eal_defended_low_eur": round(protection.defended_eal(low, rp), places),
            "eal_defended_high_eur": round(protection.defended_eal(high, rp), places)}


def assess(session: Session, asset: dict, peril: str, family_key: Optional[str]) -> dict:
    """One asset and peril through the decision tree, today's climate (no database writes)."""
    base = {"peril": peril, "exposed_value_eur": None, "occupancy": None, "curve_key": None}
    if asset.get("proxy"):         # where the issuer is registered, not where its physical assets are
        return {**base, **gaps.gap("loss.gap.head_office_only")}
    if asset.get("latitude") is None or asset.get("longitude") is None:
        return {**base, **gaps.gap("loss.gap.no_location")}
    if not family_key:             # a run reads the hazard only for a peril with adopted curves: the choice comes first (E324)
        return {**base, **gaps.gap("loss.gap.no_curves_chosen", peril=gaps.peril_name(peril))}
    lat, lon = float(asset["latitude"]), float(asset["longitude"])
    layer_key, version, s = _present_samples(session, asset, peril, lat, lon)
    if peril == "flood":
        base["flood_layer"] = layer_key
    why = gaps.intensity(s, layer_key)
    if why:
        return {**base, **why}
    base, ctx = _resolve(session, asset, peril, family_key, base)
    if ctx is None:
        return base
    per = registry.divisor(layer_key, ctx["family"]["metric"])
    if per is None:                # the map serving this asset cannot be read in the curves' metric
        return {**base, **gaps.gap("loss.gap.curves_not_usable", peril=gaps.peril_name(peril))}
    rows, why = _rp_figures(ctx["curve"], ctx["value"], s, peril, per)
    if rows is None:
        return {**base, **why}
    places = SHARE_PLACES if asset.get("per_unit") else CENTS
    out = {**base, "gap": None, "standing": standing(ctx["family"], ctx["country"], ctx["curve"]), **_summary(rows, places)}
    if peril == "flood":
        out.update(_defences(session, lat, lon, rows, places), **gaps.caution(any(r["caution"] for r in s.values())))
    return _as_share(out) if asset.get("per_unit") else out


PROJECTED = {"flood": PROJECTED_FLOOD}      # each peril's projection source; a peril not listed has none yet


def projection_gap(peril: str, scenario: str, horizon: str) -> Optional[dict]:
    """Why a projected run has no figure for this peril, scenario and horizon (a gap's fields) — or None."""
    return gaps.projection(peril, scenario, horizon, PROJECTED.get(peril))


def _blend(lower: dict[int, dict], upper: dict[int, dict], w: float, dry_below: float) -> dict[int, dict]:
    """The hazard between two maps, by warming (the product owner's decision of 2026-10-22): per return period the water
    depth — a dry pixel's depth is none — blended linearly by w; the pixel is wet where the blended depth is above the
    source's dry level."""
    out = {}
    for rp in sorted(set(lower) & set(upper)):
        a, b = lower[rp], upper[rp]
        da = (a["cell_fraction"] or 0.0) * (a["cell_mean"] or 0.0)
        db = (b["cell_fraction"] or 0.0) * (b["cell_mean"] or 0.0)
        depth = da + (db - da) * w
        wet = depth > dry_below
        out[rp] = {"status": "sampled", "cell_fraction": 1.0 if wet else 0.0, "cell_mean": depth if wet else 0.0}
    return out


def assess_projected(session: Session, asset: dict, peril: str, family_key: Optional[str], scenario: str,
                     horizon: str) -> dict:
    """One asset and peril in a projected climate (product owner's decisions, 2026-10-07 and 2026-10-22): the pathway-year
    reads the two maps of the source that bracket its warming on the platform's timeline (services.loss.timeline) — for
    each climate model, the water depth blended between them by warming (the present day, made from observed weather, is
    the same for every model); central = the middle model (by expected annual loss), its whole loss curve; low = the
    lowest curve-low of the models, high = the highest curve-high, per return period and for the annual figure; beside it
    the same source's present-day figure, the only figure it is compared with."""
    base = {"peril": peril, "exposed_value_eur": None, "occupancy": None, "curve_key": None}
    why = projection_gap(peril, scenario, horizon)
    if why:
        return {**base, **why}
    if asset.get("latitude") is None or asset.get("longitude") is None:
        return {**base, **gaps.gap("loss.gap.no_location")}
    if not family_key:             # as today's run: no adopted curves, nothing read — the choice comes first (E324)
        return {**base, **gaps.gap("loss.gap.no_curves_chosen", peril=gaps.peril_name(peril))}
    L = registry.layer(PROJECTED_FLOOD)
    lat, lon = float(asset["latitude"]), float(asset["longitude"])
    today_v = {"scenario": L["present"]["scenario"], "period": L["present"]["year"], "climate_model": L["present"]["model"]}
    today = _samples(session, PROJECTED_FLOOD, L["version"], lat, lon, today_v)
    why = gaps.intensity(today, PROJECTED_FLOOD)
    if why:
        return {**base, **why}
    base, ctx = _resolve(session, asset, peril, family_key, base)
    if ctx is None:
        return base
    from services.loss import timeline
    where = timeline.place(PROJECTED_FLOOD, scenario, horizon)
    per = registry.divisor(PROJECTED_FLOOD, ctx["family"]["metric"])
    if per is None:
        return {**base, **gaps.gap("loss.gap.curves_not_usable", peril=gaps.peril_name(peril))}

    def read(key: str, m: str) -> dict[int, dict]:
        if key == "present":
            return today
        pathway, period = key.split(":")
        return _samples(session, PROJECTED_FLOOD, L["version"], lat, lon,
                        {"scenario": pathway, "period": period, "climate_model": m})
    per_model = {}
    for m in L["models"]:
        lo, hi = read(where["lower"], m), read(where["upper"], m)
        why = gaps.intensity(lo, PROJECTED_FLOOD) or gaps.intensity(hi, PROJECTED_FLOOD)
        if why:
            return {**base, **why}
        s = _blend(lo, hi, where["w"], L["dry_below"])
        rows, why = _rp_figures(ctx["curve"], ctx["value"], s, peril, per)
        if rows is None:
            return {**base, **why}
        per_model[m] = _summary(rows)
    today_rows, why = _rp_figures(ctx["curve"], ctx["value"], today, peril, per)
    if today_rows is None:
        return {**base, **why}
    ranked = sorted(per_model.values(), key=lambda x: x["eal_eur"])
    middle = ranked[len(ranked) // 2]
    rps = sorted(middle["loss_at_rp"], key=int)
    return {**base, "gap": None, "standing": standing(ctx["family"], ctx["country"], ctx["curve"]),
            "flood_layer": PROJECTED_FLOOD, **gaps.protection("loss.protection.not_projected"),
            "eal_eur": middle["eal_eur"],
            "eal_low_eur": min(x["eal_low_eur"] for x in per_model.values()),
            "eal_high_eur": max(x["eal_high_eur"] for x in per_model.values()),
            "loss_at_rp": {rp: {"low": min(x["loss_at_rp"][rp]["low"] for x in per_model.values()),
                                "central": middle["loss_at_rp"][rp]["central"],
                                "high": max(x["loss_at_rp"][rp]["high"] for x in per_model.values())} for rp in rps},
            "eal_same_source_today_eur": _summary(today_rows)["eal_eur"],
            "model_eal": {m: x["eal_eur"] for m, x in per_model.items()}}


def run(session: Session, org_id: str, book: str, scenario: str = "baseline", horizon: str = "current",
        created_by: Optional[str] = None) -> dict:
    """Compute and record one loss run. Not committed here."""
    from services.calc_settings import get_calc_settings
    if book not in BOOKS:
        raise ValueError(f"book must be one of {BOOKS}")
    if (scenario == "baseline") != (horizon == "current"):
        raise ValueError("today's climate is scenario 'baseline' with horizon 'current'; a projection names both")
    if scenario not in SCENARIOS or horizon not in HORIZONS:
        raise ValueError(f"scenario must be one of {SCENARIOS} and horizon one of {HORIZONS}")
    projected = scenario != "baseline"
    if projected and book in SHARE_BOOKS:      # a projected share would need its same-source today as a share too
        raise ValueError("the issuers' sites are assessed in today's climate only")
    settings = get_calc_settings(session, org_id)
    adopted = {p: settings.get(f"loss_curve_family_{p}") for p in LAYERS}
    assets = _assets(session, org_id, book)
    results = []
    for a in assets:
        for peril in LAYERS:
            r = (assess_projected(session, a, peril, adopted[peril], scenario, horizon) if projected
                 else assess(session, a, peril, adopted[peril]))
            results.append({**r, "asset_kind": a["asset_kind"], "asset_id": a["asset_id"]})
    gapped = {a["asset_id"] for a in assets} - {r["asset_id"] for r in results if r["gap"] is None}
    protocol = json.loads((registry.REF / "loss_protocol.json").read_text())
    inputs = {
        "layers": ({p: {"key": k, "version": registry.layer(k)["version"],
                        "replaced_by": [{"key": r, "version": registry.layer(r)["version"],
                                         "status": registry.layer(r)["status"],
                                         "countries": registry.layer(r)["coverage_countries"]}
                                        for r, L in registry.layers().items() if L.get("replaces") == k]}
                    for p, k in LAYERS.items()} if not projected
                   else {"flood": _projection_inputs(scenario, horizon), "storm": None}),
        "flood_protection": None if projected else {
            "layer": protection.LAYER, "version": protection.layer()["version"], "rule": protocol["flood_protection"]},
        "flood_headline": settings.get("loss_flood_headline"),
        "families_adopted": adopted,
        "readings": {p: {"layer": k, "metric": curves.families()[adopted[p]]["metric"],
                         "divide_by": registry.divisor(k, curves.families()[adopted[p]]["metric"])}
                     for p, k in LAYERS.items() if not projected and adopted.get(p) in curves.families()},
        "families": {k: {"kind": f.get("kind", "published"), "source_sha256": f["source"]["sha256"],
                         "test_passed": (f.get("test") or {}).get("passed")} for k, f in curves.families().items()
                     if k in adopted.values()},
        "families_refused": curves.refused(),
        "protocol": protocol["protocol"],
        "value_basis": "a family's ratio is taken of the value its damage basis names: 'building' — the building's own "
                       "value, land excluded, as the book states it (never a market, appraised or position value); "
                       "'asset_value' — the asset's physical value as the book states it: an insurer's insured building "
                       "and contents (business interruption excluded), a bank's or property trust's building value; a "
                       "holding or investment is never one (E307); 'issuer site' — no value of its own: the share lost "
                       "of the value its curve's basis names (a value of 1), recorded as a share, never as euros",
        "flood_basis": "the asset's H3 res-8 cell: its flooded share × the damage ratio at its mean flooded depth "
                       "(asset coordinates are not verified to the building)",
        "eal_basis": "the area under the loss–exceedance curve from the most frequent return period the layer holds to "
                     "the rarest, the rarest loss held beyond it; more frequent events are not in the maps and are not "
                     "counted",
        "occupancy_crosswalk_sha256": __import__("hashlib").sha256((registry.REF / "occupancy.json").read_bytes()).hexdigest(),
        "dependence": {"flood": settings.get("loss_flood_dependence")}}
    run_id = session.execute(text("""
        INSERT INTO loss_runs (org_id, book, scenario, time_horizon, as_of, engine_version, inputs, n_assets, n_gaps,
                               created_by)
        VALUES (CAST(:o AS uuid), :b, :sc, :h, :d, :v, CAST(:i AS jsonb), :n, :g, CAST(:u AS uuid)) RETURNING run_id::text"""),
        {"o": org_id, "b": book, "sc": scenario, "h": horizon, "d": date.today(), "v": ENGINE_VERSION,
         "i": json.dumps(inputs), "n": len(assets), "g": len(gapped), "u": created_by}).scalar()
    if results:
        session.execute(text("""
            INSERT INTO loss_results (run_id, asset_kind, asset_id, peril, exposed_value_eur, occupancy, curve_key, eal_eur,
                                      eal_low_eur, eal_high_eur, standing, loss_at_rp, gap, eal_same_source_today_eur,
                                      model_eal, flood_layer, protection_rp_years, protection_basis, eal_defended_eur,
                                      eal_defended_low_eur, eal_defended_high_eur, caution, gap_code, gap_params,
                                      protection_code, caution_code, eal_ratio, eal_ratio_low, eal_ratio_high,
                                      eal_defended_ratio, eal_defended_ratio_low, eal_defended_ratio_high, ratio_at_rp)
            VALUES (CAST(:run AS uuid), :asset_kind, CAST(:asset_id AS uuid), :peril, :exposed_value_eur, :occupancy,
                    :curve_key, :eal_eur, :eal_low_eur, :eal_high_eur, :standing, CAST(:loss_at_rp AS jsonb), :gap,
                    :eal_same_source_today_eur, CAST(:model_eal AS jsonb), :flood_layer, :protection_rp_years,
                    :protection_basis, :eal_defended_eur, :eal_defended_low_eur, :eal_defended_high_eur, :caution,
                    :gap_code, CAST(:gap_params AS jsonb), :protection_code, :caution_code, :eal_ratio, :eal_ratio_low,
                    :eal_ratio_high, :eal_defended_ratio, :eal_defended_ratio_low, :eal_defended_ratio_high,
                    CAST(:ratio_at_rp AS jsonb))"""),
            [{"run": run_id, "eal_eur": None, "eal_low_eur": None, "eal_high_eur": None, "standing": None,
              "eal_same_source_today_eur": None, "flood_layer": None, "protection_rp_years": None,
              "protection_basis": None, "eal_defended_eur": None, "eal_defended_low_eur": None,
              "eal_defended_high_eur": None, "caution": None, "gap_code": None, "protection_code": None,
              "caution_code": None, **{c: None for c in _SHARE.values()}, **r,
              "gap_params": json.dumps(r["gap_params"]) if r.get("gap_params") else None,
              "loss_at_rp": json.dumps(r["loss_at_rp"]) if r.get("loss_at_rp") else None,
              "ratio_at_rp": json.dumps(r["ratio_at_rp"]) if r.get("ratio_at_rp") else None,
              "model_eal": json.dumps(r["model_eal"]) if r.get("model_eal") else None} for r in results])
    ep = _ep_points(session, run_id, results, settings)
    return {"run_id": run_id, "assets": len(assets), "with_a_figure": len(assets) - len(gapped),
            "results": len(results), "ep_points": ep, "gaps": _gap_summary(results)}


def _projection_inputs(scenario: str, horizon: str) -> dict:
    """What a projected run read, recorded with it: the source, and where the pathway-year sits on the timeline — its
    warming, the two maps that bracket it and the weight between them (or that it is warmer than every map)."""
    from services.loss import timeline
    L = registry.layer(PROJECTED_FLOOD)
    use = L["use"]
    return {"key": PROJECTED_FLOOD, "version": L["version"], "models": L["models"], "decided": use["decided"],
            "compared_with": use["compared_with"], "range": use["range"], "reads_as": L["reads_as"],
            "licence": L["licence"], "timeline": use["timeline"], "placement": timeline.place(PROJECTED_FLOOD, scenario, horizon)}


def _ep_points(session: Session, run_id: str, results: list[dict], settings: dict) -> int:
    """The book's flood exceedance curve from published figures, on the stated dependence. Returns the points written."""
    if settings.get("loss_flood_dependence") != "comonotonic":
        return 0
    pub = [r for r in results if r["peril"] == "flood" and r["gap"] is None and r.get("standing") == "published"
           and r.get("loss_at_rp")]                  # euro figures only: shares of different sites' values never add
    if not pub:
        return 0
    rps = sorted({int(rp) for r in pub for rp in r["loss_at_rp"]})
    rows = [{"run": run_id, "rp": rp, "loss": round(sum(r["loss_at_rp"][str(rp)]["central"] for r in pub), 2)} for rp in rps]
    session.execute(text("""INSERT INTO loss_ep_points (run_id, peril, kind, rp_years, loss_eur, basis)
                            VALUES (CAST(:run AS uuid), 'flood', 'aep', :rp, :loss, 'stated_dependence')"""), rows)
    return len(rows)


def _gap_summary(results: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in results:
        key = r["gap"] or f"figure ({r['standing']})"
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def run_job(org_id: str, book: str, scenario: str = "baseline", horizon: str = "current",
            created_by: Optional[str] = None) -> dict:
    """The background job (services.tasks.jobs 'loss.run'): its own session, committed. A run of today's climate first
    samples whatever its book's locations are missing (services.loss.intensity.prepare_book) for the perils with an
    adopted curve family."""
    from core.db.session import get_session
    with get_session() as session:
        if scenario == "baseline" and book in BOOKS:
            from services.calc_settings import get_calc_settings
            from services.loss.intensity import prepare_book
            settings = get_calc_settings(session, org_id)
            prepare_book(session, [a for a in _assets(session, org_id, book) if not a.get("proxy")],
                         [p for p in LAYERS if settings.get(f"loss_curve_family_{p}")])
        out = run(session, org_id, book, scenario, horizon, created_by)
        session.commit()
    return out
