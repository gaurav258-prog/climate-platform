"""Loss: damage-curve families, intensity layers, and loss runs with their results (E171).

What a figure stands on is always shown with it: the curve family the institution adopted (a stated-method election,
changed through /v1/calc-settings — audited, 4-eyes where required), the family's test and standing, the layer and its
version, and every asset and peril without a figure named with the reason. Families that cannot be used are listed
with why, so a screen never offers one silently."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/loss", tags=["Loss"])


def _family_view(key: str, f: dict) -> dict:
    t = f.get("test") or {}
    return {"family": key, "kind": f.get("kind", "published"), "peril": f["peril"], "metric": f["metric"], "unit": f["unit"],
            "damage_basis": f.get("damage_basis"), "source": f.get("source"), "licence": f.get("licence"),
            "curves": [{"key": c["key"], "occupancy": c["occupancy"], "region": c.get("region"),
                        "countries": c["countries"], "points": c["points"], "bands": c.get("bands"),
                        "sd": c.get("sd"), "spread": c.get("spread"),
                        "test": {k: v for k, v in c["test"].items() if k not in ("events", "set_aside")} if c.get("test") else None}
                       for c in f["curves"]],
            "regions_basis": f.get("regions_basis"), "absent": f.get("absent"), "not_carried": f.get("not_carried"),
            "derivation": f.get("derivation"),
            "test": {k: v for k, v in t.items() if k != "events"} if t else None,
            "test_events": t.get("events") if t else None}


@router.get("/families", summary="Damage-curve families: usable ones with their test, refused ones with why, and the adopted")
def families(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    from services.calc_settings import get_calc_settings
    from services.loss import curves
    settings = get_calc_settings(session, ctx["org"]["org_id"])
    return {"families": [_family_view(k, f) for k, f in sorted(curves.families().items())],
            "refused": [{"family": k, "reasons": v} for k, v in sorted(curves.refused().items())],
            "adopted": {p: settings.get(f"loss_curve_family_{p}") for p in ("flood", "storm")},
            "dependence": {"flood": settings.get("loss_flood_dependence")}}


@router.get("/layers", summary="Hazard intensity layers (physical units by return period) and how many places are sampled")
def layers(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    from services.loss import registry
    counts = {(r[0], r[1]): {"places": r[2], "outside_coverage": r[3], "maps": r[4]} for r in session.execute(text("""
        SELECT layer_key, layer_version, count(DISTINCT (latitude, longitude)),
               count(DISTINCT (latitude, longitude)) FILTER (WHERE status = 'outside_coverage'),
               count(DISTINCT (scenario, period, climate_model))
        FROM hazard_intensity_samples GROUP BY 1, 2""")).all()}
    return {"layers": [{"key": k, **{f: L.get(f) for f in ("peril", "metric", "unit", "version", "source", "resolution_m",
                                                          "return_periods", "coverage", "licence", "licence_status",
                                                          "status", "refines", "domain_note", "adoption")},
                        "test": L.get("test"), "building_scale_test": L.get("building_scale_test"), "decision": L.get("decision"), "present_day_check": L.get("present_day_check"),
                        "use": L.get("use"), "sampled": counts.get((k, L["version"]), {"places": 0, "outside_coverage": 0})}
                       for k, L in registry.layers().items()]}


class RunRequest(BaseModel):
    book: str = Field(..., pattern="^(banking|insurance|insurer_investments|realestate|assetmgmt|company_sites)$")
    scenario: str = Field("baseline", pattern="^(baseline|orderly_1_5c|disorderly_2c|hot_house_3_5c)$")
    horizon: str = Field("current", pattern="^(current|2030|2050|2080|2100)$")


@router.post("/runs", summary="Start a loss run over one book, today or projected (background job; recorded, never edited)")
def start_run(body: RunRequest, ctx: dict = Depends(require_permission("reports.publish"))):
    if (body.scenario == "baseline") != (body.horizon == "current"):
        raise HTTPException(422, {"error": "scenario_horizon", "message": "today's climate is scenario 'baseline' with "
                                  "horizon 'current'; a projection names both a scenario and a year"})
    from services.tasks.jobs import submit
    job = submit("loss.run", ctx["org"]["org_id"], body.book, body.scenario, body.horizon, ctx["user"]["id"])
    return {"status": "started", "book": body.book, "scenario": body.scenario, "horizon": body.horizon, "job": job}


@router.get("/projection", summary="What a projected run can serve: scenarios and horizons, and why the rest are gaps")
def projection(ctx: dict = Depends(require_permission("modules.view"))):
    from services.loss import engine, registry
    L = registry.layer(engine.PROJECTED_FLOOD)
    cells = [{"scenario": sc, "horizon": h, "gap": engine.projection_gap("flood", sc, h)}
             for sc in engine.SCENARIOS if sc != "baseline" for h in engine.HORIZONS if h != "current"]
    return {"source": L["source"], "citation": L["citation"], "licence": L["licence"], "periods": L["periods"],
            "models": L["models"], "use": L["use"], "present_day_check": L.get("present_day_check"), "flood": cells,
            "storm": engine.projection_gap("storm", "hot_house_3_5c", "2050")}


@router.get("/runs", summary="This org's loss runs, newest first")
def list_runs(session: DbSession, book: Optional[str] = None, limit: int = 50,
              ctx: dict = Depends(require_permission("modules.view"))):
    rows = session.execute(text("""
        SELECT run_id::text, book, scenario, time_horizon, as_of, engine_version, n_assets, n_gaps, created_at, seq,
               inputs -> 'families_adopted' AS families_adopted
        FROM loss_runs WHERE org_id = CAST(:o AS uuid) AND (CAST(:b AS text) IS NULL OR book = :b)
        ORDER BY seq DESC LIMIT :n"""), {"o": ctx["org"]["org_id"], "b": book, "n": max(1, min(limit, 200))}).mappings()
    return {"runs": [dict(r) for r in rows]}


@router.get("/runs/{run_id}", summary="One loss run: its inputs, totals by standing, gaps by reason, results, book curve")
def get_run(run_id: str, session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    run = session.execute(text("""
        SELECT run_id::text, book, scenario, time_horizon, as_of, engine_version, inputs, n_assets, n_gaps, created_at, seq
        FROM loss_runs WHERE run_id = CAST(:r AS uuid) AND org_id = CAST(:o AS uuid)"""),
        {"r": run_id, "o": ctx["org"]["org_id"]}).mappings().first()
    if run is None:
        raise HTTPException(404, {"error": "not_found", "message": "no such loss run for this organisation"})
    results = [dict(r) for r in session.execute(text("""
        SELECT lr.asset_kind, lr.asset_id::text, lr.peril, CAST(lr.exposed_value_eur AS FLOAT) AS exposed_value_eur,
               lr.occupancy, lr.curve_key, CAST(lr.eal_eur AS FLOAT) AS eal_eur, CAST(lr.eal_low_eur AS FLOAT) AS eal_low_eur,
               CAST(lr.eal_high_eur AS FLOAT) AS eal_high_eur, lr.standing, lr.loss_at_rp, lr.gap,
               CAST(lr.eal_same_source_today_eur AS FLOAT) AS eal_same_source_today_eur, lr.model_eal,
               COALESCE(pe.entity_name, cs.name) AS asset_name, COALESCE(pe.country, cs.country) AS country
        FROM loss_results lr
        LEFT JOIN portfolio_entities pe ON lr.asset_kind = 'portfolio_entity' AND pe.entity_id = lr.asset_id
        LEFT JOIN sc_company_sites cs ON lr.asset_kind = 'company_site' AND cs.site_id = lr.asset_id
        WHERE lr.run_id = CAST(:r AS uuid) ORDER BY lr.eal_eur DESC NULLS LAST, lr.peril"""), {"r": run_id}).mappings()]
    by_standing: dict[str, dict] = {}
    gaps: dict[str, int] = {}
    for r in results:
        if r["gap"]:
            gaps[r["gap"]] = gaps.get(r["gap"], 0) + 1
            continue
        k = f"{r['peril']}:{r['standing']}"
        t = by_standing.setdefault(k, {"peril": r["peril"], "standing": r["standing"], "results": 0,
                                       "eal_low_eur": 0.0, "eal_eur": 0.0, "eal_high_eur": 0.0,
                                       "eal_same_source_today_eur": None})
        t["results"] += 1
        for f in ("eal_low_eur", "eal_eur", "eal_high_eur"):
            t[f] = round(t[f] + (r[f] or 0.0), 2)
        if r["eal_same_source_today_eur"] is not None:
            t["eal_same_source_today_eur"] = round((t["eal_same_source_today_eur"] or 0.0) + r["eal_same_source_today_eur"], 2)
    ep = [dict(r) for r in session.execute(text("""
        SELECT peril, kind, rp_years, CAST(loss_eur AS FLOAT) AS loss_eur, basis FROM loss_ep_points
        WHERE run_id = CAST(:r AS uuid) ORDER BY peril, rp_years"""), {"r": run_id}).mappings()]
    return {"run": dict(run), "totals": sorted(by_standing.values(), key=lambda t: (t["peril"], t["standing"])),
            "totals_basis": "sums of per-asset figures within one standing; figures of different standing are never added. "
                            "A projected run's figure is compared only with the same source's present day "
                            "(eal_same_source_today_eur), never with a today run's figure",
            "gaps": [{"reason": k, "count": v} for k, v in sorted(gaps.items(), key=lambda kv: -kv[1])],
            "results": results, "book_curve": ep}
