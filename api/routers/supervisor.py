"""Regulator / supervisor portal — Phase 1: scoped cross-entity read access + population submission dashboard.

The rest of the app is strictly org-scoped and IDOR-hardened. This router is the ONE governed exception: a
regulator organization (organizations.type = 'regulator') may read across the reporting entities it supervises
— and ONLY those, defined by supervision_scope. Every rule here is deliberate and enforced:
  • ACCESS GATE: caller's org must be type 'regulator' (require_supervisor).
  • SCOPE: every read is restricted to the caller's supervised population (supervision_scope, active rows). A
    regulator can never reach an entity outside it — entity/{org_id} 404s rather than leak existence.
  • READ-ONLY + RELEASED-ONLY: only FILED statuses are ever visible; drafts/rejected are never shown.
  • AUDITED: each per-entity access writes to that supervised entity's own audit log, so the entity sees who
    looked and when (regulator transparency, not surveillance).
Phase 2/3 (system-wide aggregation, independent EO lens) build on this foundation.
"""
from __future__ import annotations

import json
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, require_permission
from api.services.rbac import write_audit
from services.governance import filings as F

router = APIRouter(prefix="/v1/supervisor", tags=["Regulator portal"])

# A filing that actually reached the regulator: submitted or beyond. Drafts/rejected are never shown.
FILED = ("submitted", "accepted", "approved", "attested", "released")


def require_supervisor(ctx: CurrentUser) -> dict:
    """403 unless the caller's organization is a regulator/supervisor AND the user holds the base supervisory
    permission. Finer rights (sites, benchmark, entity file …) are checked per endpoint via `_need`."""
    if (ctx.get("org") or {}).get("type") != "regulator":
        raise HTTPException(status_code=403,
                            detail={"error": "forbidden", "message": "Regulator/supervisor access only."})
    if "supervisor.population.view" not in (ctx.get("permissions") or []):
        raise HTTPException(status_code=403, detail={"error": "forbidden",
                            "message": "Your role has no supervisory permissions (supervisor.population.view)."})
    return ctx


def _need(ctx: dict, code: str) -> None:
    """Per-endpoint RBAC check — the codes come from the supervision-profile role templates."""
    if code not in (ctx.get("permissions") or []):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": f"Missing permission {code}."})


Supervisor = Annotated[dict, Depends(require_supervisor)]


def _org_scope(session, reg_org_id: str) -> list[dict]:
    """Everything the ORGANISATION supervises (supervision_scope, active rows)."""
    rows = session.execute(text("""
        SELECT o.org_id::text AS org_id, o.name, o.type, o.country, ss.jurisdiction
        FROM supervision_scope ss
        JOIN organizations o ON o.org_id = ss.supervised_org_id
        WHERE ss.regulator_org_id = CAST(:r AS uuid) AND ss.active
        ORDER BY o.name
    """), {"r": reg_org_id}).mappings().all()
    return [dict(r) for r in rows]


def _supervised(session, ctx: dict) -> list[dict]:
    """What THIS PERSON sees: the organisation's scope, narrowed to their assignments when their roles work a
    case list rather than the whole population (services.supervision.assignments)."""
    from services.supervision.assignments import visible_entity_ids
    ents = _org_scope(session, ctx["org"]["org_id"])
    keep = set(visible_entity_ids(session, ctx, [e["org_id"] for e in ents]))
    return [e for e in ents if e["org_id"] in keep]


def _in_scope(session, ctx: dict, target_org_id: str) -> bool:
    """Same rule as _supervised for one entity — an entity outside the person's view 404s (never leaks)."""
    from services.supervision.assignments import visible_entity_ids
    reg = ctx["org"]["org_id"]
    ok = session.execute(text("""
        SELECT 1 FROM supervision_scope
        WHERE regulator_org_id = CAST(:r AS uuid) AND supervised_org_id = CAST(:t AS uuid) AND active
    """), {"r": reg, "t": target_org_id}).first() is not None
    return ok and bool(visible_entity_ids(session, ctx, [target_org_id]))


@router.get("/population", summary="Supervised entities × frameworks — latest submission status")
def population(session: DbSession, ctx: Supervisor):
    from services.supervision.assignments import visibility
    entities = _supervised(session, ctx)
    vis = visibility(session, ctx)
    if not entities:
        return {"regulator": ctx["org"].get("name"), "entities": [], "visibility": vis,
                "summary": {"entities": 0, "frameworks_expected": 0, "frameworks_filed": 0, "coverage_pct": None}}

    ids = [e["org_id"] for e in entities]
    # latest filing per (entity, framework)
    latest = session.execute(text("""
        SELECT DISTINCT ON (org_id, framework)
               org_id::text AS org_id, framework, status, period_label, created_at
        FROM regulatory_filing
        WHERE org_id = ANY(CAST(:ids AS uuid[]))
        ORDER BY org_id, framework, created_at DESC
    """), {"ids": ids}).mappings().all()
    by_org: dict[str, dict[str, dict]] = {}
    for r in latest:
        by_org.setdefault(r["org_id"], {})[r["framework"]] = dict(r)

    n_filed = n_expected = 0
    out_entities = []
    for e in entities:
        frameworks = []
        for f in F.available_frameworks(e["type"]):
            fk = f["framework"]
            rec = by_org.get(e["org_id"], {}).get(fk)
            filed = bool(rec and rec["status"] in FILED)
            state = "filed" if filed else ("in_progress" if rec else "none")
            n_expected += 1
            n_filed += 1 if filed else 0
            frameworks.append({"framework": fk, "label": f.get("label", fk), "state": state,
                               "status": rec["status"] if rec else None,
                               "period_label": rec["period_label"] if rec else None})
        out_entities.append({**e, "frameworks": frameworks,
                             "filed": sum(1 for x in frameworks if x["state"] == "filed"),
                             "expected": len(frameworks)})
    return {
        "regulator": ctx["org"].get("name"),
        "entities": out_entities,
        "visibility": vis,
        "summary": {"entities": len(entities), "frameworks_expected": n_expected,
                    "frameworks_filed": n_filed,
                    "coverage_pct": round(100.0 * n_filed / n_expected, 1) if n_expected else None},
    }


@router.get("/entity/{org_id}", summary="One supervised entity — its released filings (read-only, audited)")
def entity(org_id: str, session: DbSession, ctx: Supervisor):
    _need(ctx, "supervisor.entity.view")
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, org_id):
        # do not confirm existence of an out-of-scope entity
        raise HTTPException(status_code=404, detail={"error": "not_found",
                            "message": "No such supervised entity in your population."})
    org = session.execute(text("SELECT name, type, country FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                          {"o": org_id}).mappings().first() or {}
    rows = session.execute(text("""
        SELECT filing_id::text AS filing_id, framework, status, period_label, submission_ref, created_at
        FROM regulatory_filing
        WHERE org_id = CAST(:o AS uuid) AND status = ANY(:st)
        ORDER BY created_at DESC
    """), {"o": org_id, "st": list(FILED)}).mappings().all()

    # transparency: the supervised entity sees that its regulator accessed its filings
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"],
                action="supervisor.access", target_type="organization", target_id=org_id,
                detail={"regulator_org_id": reg, "regulator": ctx["org"].get("name"), "filings_seen": len(rows)})
    session.commit()

    return {"entity": {"org_id": org_id, **dict(org)},
            "filings": [dict(r) | {"created_at": r["created_at"].isoformat() if r["created_at"] else None}
                        for r in rows]}


@router.get("/summary", summary="Population rollup — one line for the regulator's dashboard header")
def summary(session: DbSession, ctx: Supervisor):
    pop = population(session, ctx)
    s = pop["summary"]
    overdue = sum(1 for e in pop["entities"] for f in e["frameworks"] if f["state"] != "filed")
    return {"regulator": pop["regulator"], **s, "gaps": overdue}


# ── Where the supervised exposure sits ────────────────────────────────────────────────────────────────────
# Two levels, matching what a supervisor is entitled to:
#   • REGIONAL heat map — always available for the whole population: exposures rolled up to NUTS-3 (the unit of
#     EBA Pillar 3 Template 5 / ESRS E1-9), H3 res-4 hexagons outside the EU. No site is identifiable.
#   • INDIVIDUAL SITES — only for an entity that has GRANTED site-level access on its scope row
#     (supervision_scope.site_access_granted_at, not revoked). Each site read is audited on the entity's log.
def _site_access(session, reg_org_id: str, target_org_id: str) -> bool:
    return session.execute(text("""
        SELECT 1 FROM supervision_scope
        WHERE regulator_org_id = CAST(:r AS uuid) AND supervised_org_id = CAST(:t AS uuid) AND active
          AND site_access_granted_at IS NOT NULL AND site_access_revoked_at IS NULL
    """), {"r": reg_org_id, "t": target_org_id}).first() is not None


@router.get("/map", summary="Regional heat map of the supervised population's exposure (NUTS-3 / H3, never sites)")
def exposure_map(session: DbSession, ctx: Supervisor, entity: Optional[str] = None,
                 scenario: str = "baseline", horizon: str = "current"):
    from services.geo.org_assets import org_asset_points
    from services.geo.regions import aggregate_by_region
    reg = ctx["org"]["org_id"]
    ents = _supervised(session, ctx)
    if entity and entity != "all":
        if not _in_scope(session, ctx, entity):
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
        ents = [e for e in ents if e["org_id"] == entity]
    points: list[dict] = []
    per_entity = []
    for e in ents:
        pts = org_asset_points(session, e["org_id"], scenario, horizon)
        for p in pts:
            p["entity"] = e["name"]
        points += pts
        per_entity.append({"org_id": e["org_id"], "name": e["name"], "type": e["type"], "n_sites": len(pts),
                           "value_eur": round(sum(p["value_eur"] for p in pts)),
                           "site_access": _site_access(session, reg, e["org_id"])})
    regions = aggregate_by_region(points)
    return {"scenario": scenario, "horizon": horizon, "level": "NUTS-3 (EU, Eurostat GISCO 2021) · H3 res-4 hexagon elsewhere",
            "n_sites": len(points), "value_eur": round(sum(p["value_eur"] for p in points)),
            "n_regions": len(regions), "entities": per_entity, "regions": regions}


@router.get("/sites", summary="Individual sites of ONE supervised entity — only where that entity granted site-level access")
def entity_sites(entity: str, session: DbSession, ctx: Supervisor, scenario: str = "baseline", horizon: str = "current"):
    _need(ctx, "supervisor.sites.view")
    from services.geo.org_assets import org_asset_points
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, entity):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    if not _site_access(session, reg, entity):
        raise HTTPException(status_code=403, detail={"error": "site_access_not_granted",
                            "message": "This entity has not granted site-level access to its supervisor. Regional aggregates remain available."})
    pts = org_asset_points(session, entity, scenario, horizon)
    write_audit(session, org_id=entity, actor_user_id=ctx["user"]["id"], action="supervisor.sites.access",
                target_type="organization", target_id=entity,
                detail={"regulator_org_id": reg, "regulator": ctx["org"].get("name"), "sites_seen": len(pts),
                        "scenario": scenario, "horizon": horizon})
    session.commit()
    name = session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": entity}).scalar()
    return {"entity": {"org_id": entity, "name": name}, "scenario": scenario, "horizon": horizon, "n_sites": len(pts), "sites": pts}


# ── Supervision profile (configuration) · peer benchmark · entity file ─────────────────────────────────────
# The profile says which customer class this regulator is (banking, insurance, markets, agri-food, integrated),
# which sectors/frameworks/metrics/thresholds apply — all from data/reference/supervision_profiles.json plus the
# regulator's own overrides in supervisor_settings. No sector is named in the code below.
def _overrides(session, reg_org_id: str) -> dict:
    row = session.execute(text("""SELECT profile, default_scenario, default_horizon, thresholds FROM supervisor_settings
                                  WHERE org_id = CAST(:o AS uuid)"""), {"o": reg_org_id}).mappings().first()
    return dict(row) if row else {}


def _config(session, reg_org_id: str) -> dict:
    from services.supervision.profiles import resolve
    return resolve(None, _overrides(session, reg_org_id))


@router.get("/profile", summary="This regulator's effective supervision configuration (profile + overrides)")
def get_profile(session: DbSession, ctx: Supervisor):
    from services.supervision.profiles import profile_ids, registry
    cfg = _config(session, ctx["org"]["org_id"])
    return {"config": cfg, "overrides": _overrides(session, ctx["org"]["org_id"]),
            "available_profiles": {pid: registry()["profiles"][pid]["label"] for pid in profile_ids()}}


class ProfileUpdate(BaseModel):
    profile: Optional[str] = None
    default_scenario: Optional[str] = None
    default_horizon: Optional[str] = None
    thresholds: Optional[dict] = None


@router.put("/profile", summary="Set this regulator's profile / defaults / threshold overrides (org admin)")
def put_profile(body: ProfileUpdate, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    if (ctx.get("org") or {}).get("type") != "regulator":
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Regulator/supervisor access only."})
    from services.supervision.profiles import profile_ids, resolve
    reg = ctx["org"]["org_id"]
    cur = _overrides(session, reg)
    new = {"profile": body.profile or cur.get("profile") or "banking_supervisor",
           "default_scenario": body.default_scenario if body.default_scenario is not None else cur.get("default_scenario"),
           "default_horizon": body.default_horizon if body.default_horizon is not None else cur.get("default_horizon"),
           "thresholds": body.thresholds if body.thresholds is not None else (cur.get("thresholds") or {})}
    if new["profile"] not in profile_ids():
        raise HTTPException(status_code=422, detail={"error": "unknown_profile", "message": "Select a valid supervision profile."})
    resolve(None, new)   # validates
    session.execute(text("""
        INSERT INTO supervisor_settings (org_id, profile, default_scenario, default_horizon, thresholds, updated_at, updated_by)
        VALUES (CAST(:o AS uuid), :p, :sc, :h, CAST(:t AS jsonb), now(), CAST(:u AS uuid))
        ON CONFLICT (org_id) DO UPDATE SET profile = EXCLUDED.profile, default_scenario = EXCLUDED.default_scenario,
            default_horizon = EXCLUDED.default_horizon, thresholds = EXCLUDED.thresholds, updated_at = now(), updated_by = EXCLUDED.updated_by
    """), {"o": reg, "p": new["profile"], "sc": new["default_scenario"], "h": new["default_horizon"],
           "t": json.dumps(new["thresholds"]), "u": ctx["user"]["id"]})
    write_audit(session, org_id=reg, actor_user_id=ctx["user"]["id"], action="supervisor.profile.updated",
                target_type="supervisor_settings", target_id=reg, detail=new)
    session.commit()
    return get_profile(session, ctx)


@router.get("/benchmark", summary="Peer benchmark of the supervised population, per sector in the profile")
def get_benchmark(session: DbSession, ctx: Supervisor, scenario: Optional[str] = None, horizon: Optional[str] = None):
    _need(ctx, "supervisor.benchmark.view")
    from services.supervision.benchmark import benchmark
    reg = ctx["org"]["org_id"]
    cfg = _config(session, reg)
    return benchmark(session, cfg, _supervised(session, ctx), scenario or cfg["default_scenario"], horizon or cfg["default_horizon"])


@router.get("/entity/{org_id}/file", summary="The entity file — what a line supervisor opens: identity, submissions, exposure, peer position, access")
def entity_file(org_id: str, session: DbSession, ctx: Supervisor, scenario: Optional[str] = None, horizon: Optional[str] = None):
    _need(ctx, "supervisor.entity.file")
    from services.geo.org_assets import org_asset_points
    from services.geo.regions import aggregate_by_region
    from services.supervision.benchmark import benchmark, entity_position
    from services.supervision.profiles import sector_config
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, org_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    cfg = _config(session, reg)
    sc, hz = scenario or cfg["default_scenario"], horizon or cfg["default_horizon"]
    org = session.execute(text("SELECT org_id::text AS org_id, name, type, country, lei, legal_name FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                          {"o": org_id}).mappings().first()
    pop = population(session, ctx)
    submissions = next((e for e in pop["entities"] if e["org_id"] == org_id), None)
    pts = org_asset_points(session, org_id, sc, hz)
    regions = aggregate_by_region(pts)
    hazards: dict[str, dict] = {}
    for p in pts:
        h = hazards.setdefault(p["hazard"] or "unscored", {"hazard": p["hazard"] or "unscored", "n": 0, "value_eur": 0.0})
        h["n"] += 1; h["value_eur"] += p["value_eur"]
    for h in hazards.values():
        h["value_eur"] = round(h["value_eur"])
    ents = _supervised(session, ctx)
    bench = benchmark(session, cfg, ents, sc, hz)
    accesses = session.execute(text("""
        SELECT action, created_at, detail FROM access_audit_log
        WHERE org_id = CAST(:o AS uuid) AND action LIKE 'supervisor.%' ORDER BY created_at DESC LIMIT 10
    """), {"o": org_id}).mappings().all()
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="supervisor.file.access",
                target_type="organization", target_id=org_id, detail={"regulator_org_id": reg, "regulator": ctx["org"].get("name"), "scenario": sc, "horizon": hz})
    session.commit()
    return {"entity": dict(org), "in_profile": sector_config(cfg, org["type"]) is not None,
            "sector": sector_config(cfg, org["type"]), "scenario": sc, "horizon": hz,
            "submissions": submissions, "book": {"n_assets": len(pts), "value_eur": round(sum(p["value_eur"] for p in pts)),
                                                 "n_regions": len(regions), "top_regions": [{k: v for k, v in r.items() if k != "geometry"} for r in regions[:8]],
                                                 "hazards": sorted(hazards.values(), key=lambda h: -h["value_eur"])},
            "peer_position": entity_position(bench, org_id), "peers_in_sector": bench["sectors"].get(org["type"], {}).get("n_entities"),
            "site_access": _site_access(session, reg, org_id),
            "my_recent_accesses": [{"action": a["action"], "at": a["created_at"].isoformat(), "detail": a["detail"]} for a in accesses]}


# ── Tier-2 intake + the independent lens ────────────────────────────────────────────────────────────────
# The supervisor ingests (1) the entity's SUBMITTED template and (2) its own GRANULAR data (AnaCredit-style),
# mapped to the canonical fields the profile declares for that sector; the granular rows become a SHADOW BOOK on
# the regulator's org and the SAME engine rebuilds the template. The lens compares, cell by cell, and splits the
# gap into scope / basis / scoring / unmatched. Region-resolved precision is stamped on every result.
from fastapi import File, Form, UploadFile  # noqa: E402


def _intake_spec(session, reg: str, subject_org_id: str) -> dict:
    from services.supervision.profiles import sector_config
    cfg = _config(session, reg)
    t = session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": subject_org_id}).scalar()
    sec = sector_config(cfg, t)
    if not sec or not sec.get("intake"):
        raise HTTPException(status_code=422, detail={"error": "no_intake_spec", "message": "No granular intake is configured for this sector under your supervision profile."})
    return {"config": cfg, "sector_type": t, "intake": sec["intake"]}


@router.get("/intake/{org_id}", summary="Intake status for one supervised entity: spec, shadow book, submissions")
def intake_status(org_id: str, session: DbSession, ctx: Supervisor):
    from services.supervision.intake import shadow_status
    _need(ctx, "supervisor.intake.manage")
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, org_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    spec = _intake_spec(session, reg, org_id)
    return {"entity": org_id, "sector_type": spec["sector_type"], "intake": spec["intake"], **shadow_status(session, reg, org_id)}


@router.post("/intake/{org_id}/{kind}/validate", summary="Dry run: parse + suggest/apply a column mapping, report row problems — saves nothing")
async def intake_validate(org_id: str, kind: str, session: DbSession, ctx: Supervisor, file: UploadFile = File(...),
                          mapping: Optional[str] = Form(None)):
    from services.ingest.upload_validation import parse_table
    from services.supervision.intake import map_rows, suggest_mapping
    _need(ctx, "supervisor.intake.manage")
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, org_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    if kind not in ("submission", "granular"):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Select either the submitted template or the granular extract."})
    spec = _intake_spec(session, reg, org_id)["intake"][kind]
    fields = spec["cell_fields"] if kind == "submission" else spec["row_fields"]
    raw = await file.read()
    try:
        cols = [str(c) for c in parse_table(raw, file.filename).columns]
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"error": "unreadable", "message": "The file could not be read. Please upload a valid CSV or Excel file."}) from e
    m = json.loads(mapping) if mapping else suggest_mapping(cols, fields)
    rep = map_rows(raw, file.filename, fields, m)
    rep.pop("rows", None)
    return {"kind": kind, "fields": fields, "mapping": m, **rep}


@router.post("/intake/{org_id}/{kind}", summary="Import: save the submitted template cells, or build the shadow book from granular rows")
async def intake_import(org_id: str, kind: str, session: DbSession, ctx: Supervisor, file: UploadFile = File(...),
                        mapping: str = Form(...), period_label: str = Form(...), basis: Optional[str] = Form(None)):
    from services.supervision.intake import (
        build_shadow_book,
        cells_from_rows,
        map_rows,
        save_submission,
    )
    _need(ctx, "supervisor.intake.manage")
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, org_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    if kind not in ("submission", "granular"):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Select either the submitted template or the granular extract."})
    spec = _intake_spec(session, reg, org_id)["intake"][kind]
    fields = spec["cell_fields"] if kind == "submission" else spec["row_fields"]
    raw = await file.read(); m = json.loads(mapping)
    rep = map_rows(raw, file.filename, fields, m)
    if not rep["ok"]:
        raise HTTPException(status_code=422, detail={"error": "invalid_file", "message": "Please correct the column mapping and flagged rows before importing.", "missing_required": rep["missing_required"], "n_error": rep["n_error"]})
    if kind == "submission":
        cells = cells_from_rows(rep["rows"])
        res = save_submission(session, regulator_org_id=reg, subject_org_id=org_id, framework=spec["framework"], template=spec["template"],
                              period_label=period_label, basis=json.loads(basis) if basis else {}, cells=cells, raw=raw,
                              filename=file.filename, mapping=m, user_id=ctx["user"]["id"])
        action = "supervisor.intake.submission"
    else:
        res = build_shadow_book(session, regulator_org_id=reg, subject_org_id=org_id, period_label=period_label, rows=rep["rows"],
                                raw=raw, filename=file.filename, mapping=m, user_id=ctx["user"]["id"])
        action = "supervisor.intake.granular"
    write_audit(session, org_id=reg, actor_user_id=ctx["user"]["id"], action=action, target_type="organization", target_id=org_id,
                detail={"period_label": period_label, "file": file.filename, "n_valid": rep["n_valid"], "n_error": rep["n_error"]})
    session.commit()
    return {"kind": kind, "period_label": period_label, "n_valid": rep["n_valid"], "n_error": rep["n_error"], "result": res}


@router.get("/entity/{org_id}/lens", summary="The independent lens: submitted template vs the same template rebuilt from the shadow book")
def entity_lens(org_id: str, session: DbSession, ctx: Supervisor, period_label: Optional[str] = None,
                scenario: Optional[str] = None, horizon: Optional[str] = None):
    from services.supervision.intake import load_submission
    from services.supervision.lens_build import build_lens
    _need(ctx, "supervisor.entity.file")
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, org_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    spec = _intake_spec(session, reg, org_id)
    sub_spec = spec["intake"]["submission"]
    sub = load_submission(session, reg, org_id, sub_spec["framework"], sub_spec["template"], period_label)
    if not sub:
        return {"status": "no_submission", "message": "No template has been submitted for this entity yet. Upload one on the Intake screen.", "tier": None}
    cfg = spec["config"]
    out = build_lens(session, reg, org_id, sub, scenario or cfg["default_scenario"], horizon or cfg["default_horizon"],
                     spec["intake"]["granular"]["precision_label"])
    if out["shadow_book"]["n_rows"] == 0:
        out["status"] = "no_shadow_book"; out["message"] = "No granular data has been imported yet, so the rebuilt template is empty and every cell is unmatched."
    else:
        out["status"] = "ok"
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="supervisor.lens.access", target_type="organization",
                target_id=org_id, detail={"regulator_org_id": reg, "period_label": sub["period_label"], "n_flagged": out["n_flagged"]})
    session.commit()
    return out


@router.post("/intake/{org_id}/projections/run", summary="(Re)run scenario × horizon projections for this entity's shadow book")
def intake_project(org_id: str, session: DbSession, ctx: Supervisor, wait: bool = False):
    from services.supervision.projection import (
        project_cells_now,
        projection_coverage,
        schedule_projection,
        shadow_cells,
    )
    _need(ctx, "supervisor.intake.manage")
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, org_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    cells = shadow_cells(session, reg, org_id)
    if not cells:
        raise HTTPException(status_code=422, detail={"error": "no_shadow_book", "message": "Build the shadow book for this entity before running projections."})
    write_audit(session, org_id=reg, actor_user_id=ctx["user"]["id"], action="supervisor.intake.project", target_type="organization",
                target_id=org_id, detail={"n_cells": len(cells), "wait": wait})
    session.commit()
    if wait:
        res = project_cells_now(cells)
        return {"status": "done", **res, "coverage": projection_coverage(session, cells)}
    schedule_projection(cells)
    return {"status": "scheduled", "n_cells": len(cells), "coverage": projection_coverage(session, cells)}


# ── Population-level lens + analytics ───────────────────────────────────────────────────────────────────
@router.get("/lens", summary="Independent lens across the population: who sits far from the rebuilt figure")
def population_lens(session: DbSession, ctx: Supervisor, scenario: Optional[str] = None, horizon: Optional[str] = None):
    from services.supervision.intake import load_submission
    from services.supervision.lens_build import build_lens
    from services.supervision.profiles import sector_config
    _need(ctx, "supervisor.entity.file")
    reg = ctx["org"]["org_id"]
    cfg = _config(session, reg)
    sc, hz = scenario or cfg["default_scenario"], horizon or cfg["default_horizon"]
    rows = []
    for e in _supervised(session, ctx):
        sec = sector_config(cfg, e["type"])
        if not sec or not sec.get("intake"):
            rows.append({**e, "status": "out_of_profile"}); continue
        ss = sec["intake"]["submission"]
        sub = load_submission(session, reg, e["org_id"], ss["framework"], ss["template"])
        if not sub:
            rows.append({**e, "status": "no_submission"}); continue
        L = build_lens(session, reg, e["org_id"], sub, sc, hz, sec["intake"]["granular"]["precision_label"])
        t = L["totals"]
        rows.append({**e, "status": "ok" if L["shadow_book"]["n_rows"] else "no_shadow_book", "period_label": sub["period_label"],
                     "n_cells": L["n_cells"], "n_flagged": L["n_flagged"], "totals": t, "total_gap": L["total_gap"],
                     "gap_pct": (round(100.0 * L["total_gap"] / t["submitted"], 1) if t["submitted"] else None),
                     "precision": L["precision"], "basis_separable": L["basis_separable"],
                     "coverage_pct": (round(100.0 * L["shadow_book"]["n_located"] / L["shadow_book"]["n_rows"], 0) if L["shadow_book"]["n_rows"] else None)})
    rows.sort(key=lambda r: -abs(r.get("gap_pct") or 0))
    return {"scenario": sc, "horizon": hz, "entities": rows,
            "n_with_lens": sum(1 for r in rows if r["status"] == "ok")}


@router.get("/analytics", summary="Population analytics: concentration, scenario shift, metric distributions")
def population_analytics(session: DbSession, ctx: Supervisor, scenario: Optional[str] = None, horizon: Optional[str] = None):
    from services.supervision.analytics import analytics
    _need(ctx, "supervisor.benchmark.view")
    reg = ctx["org"]["org_id"]
    cfg = _config(session, reg)
    return analytics(session, cfg, _supervised(session, ctx), scenario or cfg["default_scenario"], horizon or cfg["default_horizon"])


@router.get("/population/workflow", summary="The population with each entity's stage in the supervisory process, sorting criteria and next action")
def population_workflow(session: DbSession, ctx: Supervisor):
    from services.supervision.benchmark import benchmark
    from services.supervision.intake import load_submission, shadow_status
    from services.supervision.lens_build import build_lens
    from services.supervision.profiles import registry, sector_config
    from services.supervision.projection import projection_coverage, shadow_cells
    from services.supervision.workflow import STEP_LABEL, STEPS, entity_workflow
    reg = ctx["org"]["org_id"]
    cfg = _config(session, reg)
    pop = population(session, ctx)
    ents = _supervised(session, ctx)
    sc, hz = cfg["default_scenario"], cfg["default_horizon"]
    bench = benchmark(session, cfg, ents, sc, hz)
    can_bench = "supervisor.benchmark.view" in (ctx.get("permissions") or [])
    can_lens = "supervisor.entity.file" in (ctx.get("permissions") or [])
    rows = []
    for e in pop["entities"]:
        sec = sector_config(cfg, e["type"])
        in_profile = sec is not None
        headline = None
        if in_profile and can_bench:
            for m in bench["sectors"].get(e["type"], {}).get("metrics", []):
                if m["id"] == "high_risk_share_pct":
                    headline = next((x for x in m["entities"] if x["org_id"] == e["org_id"]), None)
        sub = None; shadow = {"n_rows": 0}; proj = {"complete": False, "cells": 0, "cells_complete": 0}; gap = None; nflag = None
        if in_profile and sec.get("intake"):
            ss = sec["intake"]["submission"]
            sub = load_submission(session, reg, e["org_id"], ss["framework"], ss["template"])
            st = shadow_status(session, reg, e["org_id"]); shadow = st["shadow_book"]
            proj = projection_coverage(session, shadow_cells(session, reg, e["org_id"]))
            if sub and shadow["n_rows"] and can_lens:
                L = build_lens(session, reg, e["org_id"], sub, sc, hz, sec["intake"]["granular"]["precision_label"])
                gap = round(100.0 * L["total_gap"] / L["totals"]["submitted"], 1) if L["totals"]["submitted"] else None
                nflag = L["n_flagged"]
        wf = entity_workflow(session, reg, e, in_profile, sub, shadow, proj, _site_access(session, reg, e["org_id"]), headline, gap, nflag)
        rows.append({**e, "in_profile": in_profile, "sector_label": (sec or registry()["sectors"].get(e["type"]) or {}).get("label") or e["type"].replace("_", " "), **wf})
    return {"regulator": pop["regulator"], "summary": pop["summary"], "visibility": pop["visibility"],
            "scenario": sc, "horizon": hz,
            "steps": [{"key": k, "label": STEP_LABEL[k]} for k in STEPS],
            "criteria": ["sector", "jurisdiction", "stage", "submissions", "high_risk_share_pct", "lens_gap_pct", "site_access"],
            "entities": rows}


@router.get("/entity/{org_id}/lens/cell", summary="Drill into one lens cell: the submitted figure, every granular row behind the rebuilt one, and the gap arithmetic")
def lens_cell(org_id: str, geography: str, sector: str, session: DbSession, ctx: Supervisor,
              scenario: Optional[str] = None, horizon: Optional[str] = None):
    from core.types import score_to_bucket
    from services.supervision.intake import load_submission
    from services.supervision.lens import cell_key
    from services.supervision.lens_build import _geo, _sector, rebuilt_cells
    _need(ctx, "supervisor.entity.file")
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, org_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such supervised entity in your population."})
    spec = _intake_spec(session, reg, org_id)
    cfg = spec["config"]; sc, hz = scenario or cfg["default_scenario"], horizon or cfg["default_horizon"]
    ss = spec["intake"]["submission"]
    sub = load_submission(session, reg, org_id, ss["framework"], ss["template"])
    key = cell_key(geography, sector)
    submitted = (sub or {}).get("cells", {}).get(key)
    reb, pts = rebuilt_cells(session, reg, org_id, sc, hz)
    rows = []
    for p in pts:
        if cell_key(_geo(p) or "", _sector(p) or "") != key:
            continue
        b = score_to_bucket(float(p["score"])).value if p.get("score") is not None else None
        rows.append({"instrument_id": p.get("external_ref"), "name": p["name"], "outstanding_eur": round(p["value_eur"]),
                     "collateral_country": p.get("country"), "region": p.get("region_name"), "location_precision": p.get("location_precision"),
                     "lat": p.get("lat"), "lon": p.get("lon"), "nace_code": p.get("nace_code"),
                     "headline_hazard": p.get("hazard"), "headline_score": p.get("score"), "bucket": b,
                     "counts_as_sensitive": b in ("H", "VH")})
    rows.sort(key=lambda r: -r["outstanding_eur"])
    rc = reb.get(key)
    located = float((rc or {}).get("located_value_eur") or 0); gross = float((rc or {}).get("gross_carrying_amount_eur") or 0)
    sens = float((rc or {}).get("sensitive_physical_eur") or 0)
    sub_ratio = (float(submitted["sensitive_physical_eur"]) / float(submitted["gross_carrying_amount_eur"])) if submitted and submitted.get("gross_carrying_amount_eur") else None
    reb_ratio = (sens / located) if located else None
    arithmetic = {
        "submitted_sensitive_eur": submitted["sensitive_physical_eur"] if submitted else None,
        "rebuilt_sensitive_eur": round(sens) if rc else None,
        "submitted_share_pct": round(100 * sub_ratio, 1) if sub_ratio is not None else None,
        "rebuilt_share_pct": round(100 * reb_ratio, 1) if reb_ratio is not None else None,
        "located_value_eur": round(located), "unlocated_value_eur": round(gross - located),
        "n_rows": len(rows), "n_located": sum(1 for r in rows if r["lat"] is not None),
        "n_sensitive": sum(1 for r in rows if r["counts_as_sensitive"]),
        "rule": "A row counts as sensitive to physical risk when its headline hazard score is in the High or Very high band. "
                "The rebuilt share is sensitive value ÷ located value; unlocated rows cannot be judged and are shown separately.",
    }
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="supervisor.lens.cell.access", target_type="organization",
                target_id=org_id, detail={"regulator_org_id": reg, "cell": key, "n_rows": len(rows)})
    session.commit()
    return {"cell": {"geography": geography.upper(), "sector": sector.upper(), "key": key}, "scenario": sc, "horizon": hz,
            "submitted": ({**submitted, "period_label": sub["period_label"], "source_file": sub.get("source_file"), "basis": sub.get("basis")} if submitted else None),
            "rebuilt": {"rows": rows, **arithmetic}}


# ── Assignments: who works which entity ────────────────────────────────────────────────────────────────────
class AssignBody(BaseModel):
    supervised_org_id: str
    user_id: str
    capacity: str = "lead"


@router.get("/assignments", summary="Who works which supervised entity (people, roles, their scope)")
def get_assignments(session: DbSession, ctx: Supervisor):
    from services.supervision.assignments import list_assignments, team
    from services.supervision.profiles import role_templates
    _need(ctx, "supervisor.assignments.manage")
    reg = ctx["org"]["org_id"]
    return {"entities": _org_scope(session, reg), "people": team(session, reg),
            "assignments": list_assignments(session, reg),
            "roles": {k: {"label": v["label"], "scope": v.get("scope", "assigned")} for k, v in role_templates().items()}}


@router.put("/assignments", summary="Assign a person to a supervised entity (idempotent)")
def put_assignment(body: AssignBody, session: DbSession, ctx: Supervisor):
    from services.supervision.assignments import assign
    _need(ctx, "supervisor.assignments.manage")
    reg = ctx["org"]["org_id"]
    if not any(e["org_id"] == body.supervised_org_id for e in _org_scope(session, reg)):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Entity is not in your supervised population."})
    cap = (body.capacity or "lead").strip()[:40]
    aid = assign(session, reg, body.supervised_org_id, body.user_id, ctx["user"]["id"], cap)
    if aid is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Person is not in your organisation."})
    write_audit(session, org_id=reg, actor_user_id=ctx["user"]["id"], action="supervisor.assignment.set",
                target_type="organization", target_id=body.supervised_org_id,
                detail={"user_id": body.user_id, "capacity": cap})
    session.commit()
    return {"assignment_id": aid}


@router.delete("/assignments/{assignment_id}", summary="End a person's assignment to an entity")
def delete_assignment(assignment_id: str, session: DbSession, ctx: Supervisor):
    from services.supervision.assignments import revoke
    _need(ctx, "supervisor.assignments.manage")
    reg = ctx["org"]["org_id"]
    if not revoke(session, reg, assignment_id, ctx["user"]["id"]):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such active assignment."})
    write_audit(session, org_id=reg, actor_user_id=ctx["user"]["id"], action="supervisor.assignment.end",
                target_type="supervision_assignment", target_id=assignment_id, detail={})
    session.commit()
    return {"ok": True}


# ── Requests & findings: engage the entity and follow up ───────────────────────────────────────────────────
class RequestCreate(BaseModel):
    supervised_org_id: str
    kind: str
    title: str
    body: Optional[str] = None
    severity: Optional[str] = None
    due_date: Optional[str] = None
    source: Optional[dict] = None


class RequestMessage(BaseModel):
    body: Optional[str] = None
    status_to: Optional[str] = None


def _need_engage(ctx: dict, kind: Optional[str]) -> None:
    _need(ctx, "supervisor.findings.manage" if kind == "finding" else "supervisor.requests.manage")


@router.get("/requests", summary="Requests and findings across the entities you see")
def list_requests(session: DbSession, ctx: Supervisor, status: Optional[str] = None, kind: Optional[str] = None,
                  entity: Optional[str] = None):
    from services.supervision.engagement import kinds, status_label
    from services.supervision.engagement import list_requests as _list
    if not ({"supervisor.requests.manage", "supervisor.findings.manage"} & set(ctx.get("permissions") or [])):
        raise HTTPException(status_code=403, detail={"error": "forbidden", "message": "Missing permission supervisor.requests.manage."})
    reg = ctx["org"]["org_id"]
    ents = _supervised(session, ctx)
    rows = _list(session, regulator_org_id=reg, supervised_org_ids=[e["org_id"] for e in ents], status=status, kind=kind,
                 supervised_org_id=entity)
    return {"requests": rows, "entities": ents,
            "kinds": {k: {"label": v["label"], "statuses": [{"key": st, "label": status_label(st)} for st in v["statuses"]],
                          "supervisor_sets": v["supervisor_sets"], "severities": v["severities"]} for k, v in kinds().items()},
            "summary": {"open": sum(1 for r in rows if r["status"] != "closed"), "overdue": sum(1 for r in rows if r["overdue"]),
                        "findings_open": sum(1 for r in rows if r["kind"] == "finding" and r["status"] != "closed")}}


@router.post("/requests", status_code=201, summary="Raise an information request, site-access request or finding with an entity")
def create_request(body: RequestCreate, session: DbSession, ctx: Supervisor):
    from services.supervision.engagement import create
    _need_engage(ctx, body.kind)
    reg = ctx["org"]["org_id"]
    if not _in_scope(session, ctx, body.supervised_org_id):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "Entity is not in your view."})
    try:
        req = create(session, regulator_org_id=reg, supervised_org_id=body.supervised_org_id, kind=body.kind, title=body.title,
                     body=body.body, raised_by=ctx["user"]["id"], severity=body.severity, due_date=body.due_date, source=body.source)
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": str(e)})
    for audited in (reg, body.supervised_org_id):
        write_audit(session, org_id=audited, actor_user_id=ctx["user"]["id"], action="supervisor.request.raised",
                    target_type="supervision_request", target_id=req["request_id"],
                    detail={"kind": body.kind, "title": req["title"], "regulator_org_id": reg, "supervised_org_id": body.supervised_org_id})
    session.commit()
    return req


@router.get("/requests/{request_id}", summary="One request or finding with its thread")
def get_request(request_id: str, session: DbSession, ctx: Supervisor):
    from services.supervision.engagement import allowed_next, get, status_label
    req = get(session, request_id, regulator_org_id=ctx["org"]["org_id"])
    if not req or not _in_scope(session, ctx, req["supervised_org_id"]):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such request in your view."})
    _need_engage(ctx, req["kind"])
    req["can_set"] = [{"key": st, "label": status_label(st)} for st in allowed_next(req["kind"], "supervisor") if st != req["status"]]
    return req


@router.post("/requests/{request_id}/messages", summary="Add to the thread and/or move the status (supervisor side)")
def post_request_message(request_id: str, body: RequestMessage, session: DbSession, ctx: Supervisor):
    from services.supervision.engagement import add_message, get
    req = get(session, request_id, regulator_org_id=ctx["org"]["org_id"])
    if not req or not _in_scope(session, ctx, req["supervised_org_id"]):
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No such request in your view."})
    _need_engage(ctx, req["kind"])
    if not (body.body or "").strip() and not body.status_to:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": "Write a message or choose a status."})
    try:
        out = add_message(session, request_id, side="supervisor", author_id=ctx["user"]["id"], body=body.body, status_to=body.status_to)
    except PermissionError as e:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": str(e)})
    action = "supervisor.request.status" if body.status_to else "supervisor.request.message"
    for audited in (ctx["org"]["org_id"], req["supervised_org_id"]):
        write_audit(session, org_id=audited, actor_user_id=ctx["user"]["id"], action=action, target_type="supervision_request",
                    target_id=request_id, detail={"status_to": body.status_to, "regulator_org_id": ctx["org"]["org_id"]})
    session.commit()
    return out
