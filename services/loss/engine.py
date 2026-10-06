"""The loss engine (E171): one recorded loss run per organisation, book, scenario and horizon — every asset and peril
walked through the same decision tree, each result a figure with its range and standing, or the named gap that
stopped it.

  1  intensity here?      the layer's samples at the asset (services.loss.intensity) — none, or outside coverage → gap
  2  method adopted?      the institution's adopted curve family for the peril (calc settings loss_curve_family_*) → gap
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
The book's exceedance curve adds only published figures, on the basis the institution states (loss_flood_dependence);
with none, the curve is a named gap. Scenarios beyond today wait on projected intensity (a named gap)."""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.loss import curves, registry

ENGINE_VERSION = "loss-v1"
LAYERS = {"flood": "jrc_river_flood", "storm": "storm_v4_wind"}
BOOKS = ("banking", "insurance", "insurer_investments", "realestate", "assetmgmt", "company_sites")


def _samples(session: Session, layer_key: str, version: str, lat: float, lon: float) -> dict[int, dict]:
    return {r["rp_years"]: dict(r) for r in session.execute(text("""
        SELECT rp_years, status, value, cell_fraction, cell_mean FROM hazard_intensity_samples
        WHERE layer_key = :k AND layer_version = :v AND latitude = :la AND longitude = :lo"""),
        {"k": layer_key, "v": version, "la": lat, "lo": lon}).mappings()}


def _band_at(curve: dict, x: float) -> tuple[float, float]:
    """(low, high) damage ratio at intensity x: the band holding x (measured curves); a published curve without bands
    has no range of its own."""
    for b in curve.get("bands") or []:
        if b["from_m"] < x <= b["to_m"]:
            return b["p10"], b["p90"]
    bands = curve.get("bands") or []
    if bands and x > bands[-1]["to_m"]:
        return bands[-1]["p10"], bands[-1]["p90"]
    raise ValueError("no band")


def eal(losses: dict[int, float]) -> float:
    """Area under the loss–exceedance curve over the return periods held: trapezoids in annual exceedance probability
    between consecutive return periods, the rarest loss held beyond the rarest return period."""
    rps = sorted(losses)
    p = [1.0 / rp for rp in rps]
    out = sum((p[i] - p[i + 1]) * (losses[rps[i]] + losses[rps[i + 1]]) / 2 for i in range(len(rps) - 1))
    return out + p[-1] * losses[rps[-1]]


def standing(family: dict, country: str) -> str:
    t = family.get("test")
    if not t:
        return "untested"
    tested = set(t.get("countries") or [c for cur in family["curves"] for c in cur["countries"]])
    if country not in tested:
        return "untested"
    return "published" if t.get("passed") else "held"


# Where each book states the BUILDING's own value (land excluded) — what a building damage curve's share is taken of —
# and, where it cannot, why not. A market, appraised or position value is never read as a building value.
_BUILDING_VALUE = {
    "banking": ("LEFT JOIN ext_banking x ON x.entity_id = e.entity_id", "x.building_value_eur",
                "the collateral building's own value is not stated (the appraised value includes the land)"),
    "insurance": ("LEFT JOIN ext_insurance x ON x.entity_id = e.entity_id", "x.building_value_eur",
                  "the policy states no building value (its insured value is not broken into buildings, contents and interruption)"),
    "realestate": ("LEFT JOIN ext_realestate x ON x.entity_id = e.entity_id", "x.building_value_eur",
                   "the building's own value is not stated (the property value includes the land)"),
    "assetmgmt": ("", "NULL", "a holding is a share in a company, not a building: it has no building value"),
    "insurer_investments": ("", "NULL", "a holding is a share in a company, not a building: it has no building value"),
}


def _assets(session: Session, org_id: str, book: str) -> list[dict]:
    if book == "company_sites":
        return [{**dict(r), "asset_kind": "company_site", "value": None, "building_value": None,
                 "no_building_value": "the site's building value is not stated (its annual value is a flow, not what the "
                                      "building is worth)", "table": "sc_company_sites.site_type"}
                for r in session.execute(text("""
                    SELECT site_id::text AS asset_id, latitude, longitude, country, occupancy, site_type AS asset_type
                    FROM sc_company_sites WHERE org_id = CAST(:o AS uuid)"""), {"o": org_id}).mappings()]
    join, col, why = _BUILDING_VALUE[book]
    return [{**dict(r), "asset_kind": "portfolio_entity", "table": "portfolio_entities.entity_type", "no_building_value": why}
            for r in session.execute(text(f"""
                SELECT e.entity_id::text AS asset_id, e.latitude, e.longitude, e.country, e.occupancy,
                       e.entity_type AS asset_type, CAST(e.primary_value_eur AS FLOAT) AS value,
                       CAST({col} AS FLOAT) AS building_value
                FROM portfolio_entities e {join}
                WHERE e.org_id = CAST(:o AS uuid) AND e.vertical = :b AND e.source = 'own'"""),
                {"o": org_id, "b": book}).mappings()]


def _value_for(asset: dict, family: dict) -> tuple[Optional[float], str]:
    """(the value the family's ratio is a share of, or None; the reason when None)."""
    basis = family.get("damage_basis") or "building"
    if basis == "building":
        v = asset.get("building_value")
        return (v, "") if v and v > 0 else (None, asset["no_building_value"])
    if basis == "asset_value":
        v = asset.get("value")
        return (v, "") if v and v > 0 else (None, "the asset's value is not stated")
    return None, f"the family's damage basis '{basis}' is not one the books state"


@lru_cache(maxsize=1)
def _countries() -> frozenset[str]:
    """ISO alpha-2 codes that are countries (ref_countries.is_country): a grouping such as 'EU' is not (E154)."""
    from core.db.config import SessionLocal
    s = SessionLocal()
    try:
        return frozenset(r[0].strip() for r in s.execute(text("SELECT iso2 FROM ref_countries WHERE is_country")).all())
    finally:
        s.close()


def _country_gap(session: Session, asset: dict, country: str) -> str:
    """Why the asset has no country a curve can be chosen by — with the country its coordinates fall in as a hint,
    never as a substitute for what the book states."""
    from services.intake.observations import _country_from_location
    where = _country_from_location(session, asset)
    hint = f" (its coordinates are in {where})" if where else ""
    if not country:
        return f"the asset's country is not stated{hint}"
    return f"the book states '{country}', which is not a country — a curve is chosen by country{hint}"


def assess(session: Session, asset: dict, peril: str, family_key: Optional[str]) -> dict:
    """One asset and peril through the decision tree (no database writes)."""
    layer_key = LAYERS[peril]
    L = registry.layer(layer_key)
    base = {"peril": peril, "exposed_value_eur": None, "occupancy": None, "curve_key": None}
    if asset.get("latitude") is None or asset.get("longitude") is None:
        return {**base, "gap": "the asset has no location"}
    s = _samples(session, layer_key, L["version"], float(asset["latitude"]), float(asset["longitude"]))
    if not s:
        return {**base, "gap": f"{layer_key} {L['version']} has not been sampled at this location yet"}
    if any(r["status"] != "sampled" for r in s.values()):
        return {**base, "gap": f"outside the coverage of {layer_key} {L['version']}"}
    if not family_key:
        return {**base, "gap": f"no {peril} damage-curve family adopted (stated method)"}
    family = curves.families().get(family_key)
    if family is None:
        why = "; ".join(curves.refused().get(family_key, ["not registered"]))
        return {**base, "gap": f"the adopted family {family_key} cannot be used: {why}"}
    occ, why = registry.occupancy_of(asset.get("occupancy"), asset["table"], asset.get("asset_type"))
    if occ is None:
        return {**base, "gap": why}
    base["occupancy"] = occ
    country = (asset.get("country") or "").strip().upper()
    if country not in _countries():
        return {**base, "gap": _country_gap(session, asset, country)}
    curve = curves.curve_for(family_key, occ, country)
    if curve is None:
        return {**base, "gap": f"{family_key} has no {occ} curve for {country or 'an unknown country'}"}
    base["curve_key"] = curve["key"]
    value, why = _value_for(asset, family)
    if value is None:
        return {**base, "exposed_value_eur": None, "gap": why}
    base["exposed_value_eur"] = value
    rp_rows = {}
    for rp, r in sorted(s.items()):
        if peril == "flood":
            share, depth = (r["cell_fraction"] or 0.0), (r["cell_mean"] or 0.0)
            if share == 0 or depth <= 0:
                rp_rows[rp] = (0.0, 0.0, 0.0)
                continue
            central = curves.ratio(curve["points"], depth)
            try:
                lo, hi = _band_at(curve, depth)
            except ValueError:
                return {**base, "gap": f"{curve['key']} has no damage range at {depth:.2f} m"}
            rp_rows[rp] = (value * share * min(lo, central), value * share * central, value * share * max(hi, central))
        else:
            ratio = curves.ratio(curve["points"], float(r["value"] or 0.0))
            rp_rows[rp] = (value * ratio, value * ratio, value * ratio)
    low, central, high = ({rp: v[i] for rp, v in rp_rows.items()} for i in range(3))
    return {**base, "gap": None, "standing": standing(family, country),
            "eal_eur": round(eal(central), 2), "eal_low_eur": round(eal(low), 2), "eal_high_eur": round(eal(high), 2),
            "loss_at_rp": {str(rp): {"low": round(low[rp], 2), "central": round(central[rp], 2), "high": round(high[rp], 2)}
                           for rp in sorted(rp_rows)}}


def run(session: Session, org_id: str, book: str, scenario: str = "baseline", horizon: str = "current",
        created_by: Optional[str] = None) -> dict:
    """Compute and record one loss run. Not committed here."""
    from services.calc_settings import get_calc_settings
    if book not in BOOKS:
        raise ValueError(f"book must be one of {BOOKS}")
    settings = get_calc_settings(session, org_id)
    adopted = {p: settings.get(f"loss_curve_family_{p}") for p in LAYERS}
    assets = _assets(session, org_id, book)
    results = []
    for a in assets:
        for peril in LAYERS:
            if (scenario, horizon) != ("baseline", "current"):
                r = {"peril": peril, "exposed_value_eur": None, "occupancy": None, "curve_key": None,
                     "gap": "projected intensity for this scenario and horizon is not built yet"}
            else:
                r = assess(session, a, peril, adopted[peril])
            results.append({**r, "asset_kind": a["asset_kind"], "asset_id": a["asset_id"]})
    gapped = {a["asset_id"] for a in assets} - {r["asset_id"] for r in results if r["gap"] is None}
    inputs = {
        "layers": {p: {"key": k, "version": registry.layer(k)["version"]} for p, k in LAYERS.items()},
        "families_adopted": adopted,
        "families": {k: {"kind": f.get("kind", "published"), "source_sha256": f["source"]["sha256"],
                         "test_passed": (f.get("test") or {}).get("passed")} for k, f in curves.families().items()
                     if k in adopted.values()},
        "families_refused": curves.refused(),
        "protocol": json.loads((registry.REF / "loss_protocol.json").read_text())["protocol"],
        "value_basis": "a family's ratio is taken of the value its damage basis names: 'building' — the building's own "
                       "value, land excluded, as the book states it (never a market, appraised or position value); "
                       "'asset_value' — the asset's stated value",
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
                                      eal_low_eur, eal_high_eur, standing, loss_at_rp, gap)
            VALUES (CAST(:run AS uuid), :asset_kind, CAST(:asset_id AS uuid), :peril, :exposed_value_eur, :occupancy,
                    :curve_key, :eal_eur, :eal_low_eur, :eal_high_eur, :standing, CAST(:loss_at_rp AS jsonb), :gap)"""),
            [{"run": run_id, "eal_eur": None, "eal_low_eur": None, "eal_high_eur": None, "standing": None, **r,
              "loss_at_rp": json.dumps(r["loss_at_rp"]) if r.get("loss_at_rp") else None} for r in results])
    ep = _ep_points(session, run_id, results, settings)
    return {"run_id": run_id, "assets": len(assets), "with_a_figure": len(assets) - len(gapped),
            "results": len(results), "ep_points": ep, "gaps": _gap_summary(results)}


def _ep_points(session: Session, run_id: str, results: list[dict], settings: dict) -> int:
    """The book's flood exceedance curve from published figures, on the stated dependence. Returns the points written."""
    if settings.get("loss_flood_dependence") != "comonotonic":
        return 0
    pub = [r for r in results if r["peril"] == "flood" and r["gap"] is None and r.get("standing") == "published"]
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
    """The background job (services.tasks.jobs 'loss.run'): its own session, committed."""
    from core.db.session import get_session
    with get_session() as session:
        out = run(session, org_id, book, scenario, horizon, created_by)
        session.commit()
    return out
