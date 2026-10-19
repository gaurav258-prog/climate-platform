"""The signed-in person's front door (Horizon) and what needs them now.

  /globe     the organisation's book on the globe at today and each modelled year (services.intelligence.front_door —
             the one cross-sector reader the sector pages and the supervisor's map use); a supervisory body sees its
             population rolled up to regions
  /entities  the reporting entities the person can scope it to
  /tasks     a role-filtered, ranked feed: the failing readiness checks (services.governance.readiness — one
             definition each) routed to who acts on them, approvals waiting, support replies, a reporting period
             ending, frozen filings with new data

Nothing here is a new number, and nothing is a sentence: every explanation is a catalogue message (horizon.*).
"""
from __future__ import annotations

from typing import Optional

import h3
from fastapi import APIRouter, Query
from sqlalchemy import text

from api.deps import CurrentUser, DbSession
from core import messages

router = APIRouter(prefix="/v1/me", tags=["Me"])

_SCENARIO = "^(orderly_1_5c|disorderly_2c|hot_house_3_5c)$"


@router.get("/globe", summary="This org's located book at today and each modelled year, against its stated at-risk level")
def globe(session: DbSession, ctx: CurrentUser,
          scenario: str = Query("disorderly_2c", pattern=_SCENARIO),
          entity_id: Optional[str] = Query(None, description="scope to one reporting entity and everything below it")):
    """Every located exposure the organisation holds with its headline score (the worst hazard over the scales that
    apply to it) today and in each modelled year under the scenario, whether it is at or above the organisation's
    stated at-risk level, the totals, the filing-readiness checklist and the person's roles. A supervisory body gets
    the regions its supervised population sits in (never a site) and its population totals."""
    from services.governance.readiness import org_readiness
    from services.intelligence import front_door as fd
    org_id = ctx["org"]["org_id"]
    org_type = session.execute(text("SELECT type FROM organizations WHERE org_id=:o"), {"o": org_id}).scalar()

    supervisor = None
    if org_type == "regulator":
        from api.routers.supervisor import _supervised
        ents = _supervised(session, ctx)
        view = fd.population(session, ents, scenario)
        supervisor = _population_totals(session, ctx, ents)
    else:
        view = fd.book(session, org_id, org_type, scenario, entity_id)

    rd = org_readiness(session, org_id, org_type)
    raised_pending = session.execute(text(
        "SELECT count(*) FROM approval_requests WHERE org_id=:o AND maker_user_id=:u AND status='pending'"),
        {"o": org_id, "u": ctx["user"]["id"]}).scalar() or 0
    return {"audience": "supervisor" if org_type == "regulator" else "book", "sector": org_type,
            "noun": messages.name("horizon.noun", org_type if org_type in messages.names().get("horizon.noun", {}) else "other"),
            "scenario": {"key": scenario, "name": messages.name("scenario", scenario)},
            "scenarios": fd.scenarios(), "stops": fd.stops(scenario),
            **view,
            "readiness": {"passed": rd["passed"], "total": rd["total"],
                          "checks": [{k: c[k] for k in ("key", "ok", "message", "fix_href", "fix_label")} for c in rd["checks"]]},
            "my_scope": {"roles": fd.role_names(org_type, ctx.get("roles", [])), "raised_pending": int(raised_pending)},
            "supervisor": supervisor}


def _population_totals(session, ctx: dict, ents: list[dict]) -> dict:
    """The supervisor's three figures: entities in view, expected filings not yet received, requests still open."""
    from api.routers.supervisor import population
    pop = population(session, ctx)
    s = pop["summary"]
    outstanding = sum(1 for e in pop["entities"] for f in e["frameworks"] if f["state"] != "filed")
    ids = [e["org_id"] for e in ents]
    open_requests = session.execute(text("""
        SELECT count(*) FROM supervision_request WHERE regulator_org_id = CAST(:r AS uuid)
           AND supervised_org_id = ANY(CAST(:ids AS uuid[])) AND closed_at IS NULL
    """), {"r": ctx["org"]["org_id"], "ids": ids}).scalar() if ids else 0
    return {"entities": len(ents), "filings_expected": s["frameworks_expected"], "filings_outstanding": outstanding,
            "open_requests": int(open_requests or 0)}


@router.get("/entities", summary="The reporting entities this org holds — the person scopes Horizon to one")
def entities(session: DbSession, ctx: CurrentUser):
    """The organisation's reporting entities (legal entity / fund / group / …), each with the located assets it and
    the entities below it hold — the slice the globe shows when it is picked. The implicit whole organisation is
    entity_id = null."""
    from services.intelligence.front_door import entity_counts
    return {"entities": entity_counts(session, ctx["org"]["org_id"])}


@router.get("/hexes", summary="The H3 res-8 grid around a location — the granular cell + its neighbours, real scores")
def hexes(session: DbSession, ctx: CurrentUser,
          lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
          scenario: str = Query("disorderly_2c", pattern="^(baseline|orderly_1_5c|disorderly_2c|hot_house_3_5c)$"),
          horizon: str = Query("2050", pattern="^(current|2030|2050|2100)$"), k: int = Query(2, ge=1, le=3),
          score: bool = Query(True)):
    """The platform pins every location to a ~0.7 km H3 res-8 hexagon and scores at that grain. This returns
    the cell the point falls in plus its k-ring neighbours, each with its real polygon boundary and the
    worst-hazard physical-risk score — so you see the risk TEXTURE around a site, not just the one cell.

    When `score=true` (default) each ring cell is scored ON DEMAND for the cheap, fetch-free hazards
    (seismic, chronic heat, storm) using the exact same scorers the any-address lookup uses — no Celery,
    no invented numbers. The worst-hazard per cell then unions the horizon-varying score at the requested
    (scenario, horizon) with the horizon-invariant baseline hazards (seismic/storm). A cell stays null only
    where the golden-source baselines genuinely have no coverage (open ocean, polar gaps)."""
    center = h3.latlng_to_cell(lat, lon, 8)
    cells = list(h3.grid_disk(center, k))

    def _read_scores():
        # Worst-hazard per cell = max over the requested (scenario,horizon) AND the horizon-invariant
        # baseline lane (seismic/storm live there). Null where the golden-source baselines have no
        # coverage — never invented.
        rows = session.execute(text("""
            SELECT h3_cell, MAX(CAST(risk_score AS FLOAT)) score
            FROM   canonical_scores
            WHERE  h3_cell = ANY(:cells) AND valid_to IS NULL
              AND ((scenario = :sc AND time_horizon = :h)
                   OR (scenario = 'baseline' AND time_horizon = 'current'))
            GROUP  BY h3_cell
        """), {"cells": cells, "sc": scenario, "h": horizon}).mappings().all()
        return {r["h3_cell"]: r["score"] for r in rows}

    score_by = _read_scores()

    # A ring cell costs ~3.5s to score cold (heat climatology + seismic catalogue) but ~0 once cached, so
    # scoring all 19 in-request would block for a minute. Instead: return whatever is cached NOW and warm
    # the rest in a background daemon thread (same "computing then re-fetch" pattern the any-address lookup
    # uses). The client re-fetches shortly after and the freshly-scored cells fill in. Fully warm → instant.
    computing = False
    if score:
        # Warm EVERY ring cell (not just the entirely-unscored ones): a cell with only a stale seismic row
        # would otherwise report a misleadingly low worst-hazard until its heat is computed. The scorers
        # short-circuit on a cache hit, so re-warming an already-complete cell is ~free.
        from services.scoring.on_demand import warm_sync_scores
        warm_sync_scores({c: h3.cell_to_latlng(c) for c in cells}, scenario=scenario, horizon=horizon)
        # Ask the client to re-fetch while the ring is still filling in.
        computing = len(score_by) < len(cells)

    from services.geo.cells import cell_shape
    out = []
    for c in cells:
        shp = cell_shape(c)   # clipped to land — a neighbour cell over the sea is drawn only for its land part
        if not shp["on_land"] and c != center:
            continue
        out.append({"cell": c, "is_center": c == center, "rings": shp["rings_latlon"], "on_land": shp["on_land"],
                    "score": (round(score_by[c], 1) if c in score_by else None)})
    scored_n = sum(1 for c in cells if c in score_by)
    return {"center": center, "resolution": 8, "cell_km": 0.7, "scenario": scenario, "horizon": horizon,
            "center_score": (round(score_by[center], 1) if center in score_by else None),
            "n_cells": len(cells), "n_scored": scored_n, "computing": computing, "cells": out}


# severity → sort weight (higher first). action = needs a decision/edit; warning = will block a filing;
# info = awareness; good = a positive confirmation.
_WEIGHT = {"action": 3, "warning": 2, "info": 1, "good": 0}

# Approval service-level target — a decision that has waited longer than this is treated as overdue. This
# is OUR disclosed target (there is no regulatory approval deadline), stated as such in the task's pop-up, not a
# fabricated regulator date.
_APPROVAL_SLA_DAYS = 3

# Task urgency bucket. "overdue"/"this_week"/"upcoming" are only assigned when a REAL time basis exists
# (feed age, approval age, revalidation lag, reporting-period end). Everything else is honestly "open" —
# a real action with no fixed date — never given an invented deadline.
_BUCKET_ORDER = {"overdue": 0, "this_week": 1, "upcoming": 2, "open": 3}

# A failing readiness check becomes a task for whoever acts on it: (permission, severity, bucket). The check itself —
# what it tests, its words, where it is fixed — is services.governance.readiness, the one definition.
_CHECK_TASK = {
    "identity":             ("admin.users.manage", "warning", "open"),
    "second_approver":      ("admin.users.manage", "warning", "open"),
    "golden_source_fresh":  ("admin.users.manage", "warning", "overdue"),   # past its scheduled refresh
    "calibrations_current": ("admin.users.manage", "info", "overdue"),      # past the re-validation window
    "sites_scored":         ("modules.view", "info", "open"),
    "plots_polygons":       ("modules.view", "warning", "open"),
    "eudr_run":             ("modules.view", "action", "open"),
    "inputs_high_quality":  ("modules.view", "info", "open"),
}


def _task(key, message, severity, action_key, href, need, bucket="open", due=None):
    return {"key": key, "message": message, "severity": severity,
            "action": {"label": messages.name("horizon.action", action_key), "href": href},
            "_need": need, "bucket": bucket, "due": due}


def _finalize(tasks: list[dict], perms: set) -> dict:
    """Keep only tasks this user may act on, drop the private _need, rank by severity."""
    visible = [t for t in tasks if t["_need"] in perms]
    for t in visible:
        t.pop("_need", None)
    # time bucket first (overdue → this_week → upcoming → open), severity as the tie-break within a bucket
    visible.sort(key=lambda t: (_BUCKET_ORDER.get(t["bucket"], 3), -_WEIGHT.get(t["severity"], 0)))
    return {"tasks": visible, "all_clear": len(visible) == 0}


@router.get("/tasks", summary="Role-filtered actionable tasks for the front door")
def my_tasks(session: DbSession, ctx: CurrentUser):
    """What needs this person now, for the whole organisation: each failing readiness check routed to the
    permission that acts on it, approvals waiting for a second person, support replies, an agricultural reporting
    period ending without its statement, and frozen filings with new data."""
    from services.governance.readiness import org_readiness
    org_id = ctx["org"]["org_id"]
    org_type = session.execute(text("SELECT type FROM organizations WHERE org_id=:o"), {"o": org_id}).scalar()
    perms = set(ctx.get("permissions") or [])
    tasks: list[dict] = []

    # ── approvals waiting (bucket from the OLDEST pending request's real age vs our target) ─────────────────
    # Only requests THIS user can actually action — a decider can't approve their own (4-eyes), so a request they
    # raised is not "waiting for you". A request assigned to someone else is still counted (any approver may act
    # unless assignment routes it — keep it discoverable).
    prow = session.execute(text(
        "SELECT count(*) n, min(created_at) AS oldest "
        "FROM approval_requests WHERE org_id=:o AND status='pending' AND maker_user_id <> :u"),
        {"o": org_id, "u": ctx["user"]["id"]}).mappings().first()
    pending = prow["n"] or 0
    if pending:
        from datetime import datetime, timedelta, timezone
        oldest = prow["oldest"]
        due = oldest + timedelta(days=_APPROVAL_SLA_DAYS)
        late = datetime.now(timezone.utc) > due
        raised = oldest.date().isoformat()
        tasks.append(_task(
            "approvals_pending", messages.render("horizon.task.approvals", n=pending, raised=raised),
            "action", "approvals_pending", "/approvals", "approvals.decide", bucket="overdue" if late else "this_week",
            due=messages.render("horizon.due.past_target" if late else "horizon.due.waiting",
                                raised=raised, due=due.date().isoformat(), sla=_APPROVAL_SLA_DAYS)))

    # ── the readiness checklist: every failing check, to whoever fixes it (one definition: readiness.py) ────────
    for c in org_readiness(session, org_id, org_type)["checks"]:
        if c["ok"] or c["key"] not in _CHECK_TASK or not c.get("fix_href"):
            continue
        need, severity, bucket = _CHECK_TASK[c["key"]]
        tasks.append(_task(c["key"], c["message"], severity, c["key"], c["fix_href"], need, bucket=bucket))

    # ── SUPPORT: Tellumen replied to a request you raised (cross-sector; anyone with portal access) ──
    awaiting = session.execute(text("""
        SELECT count(*) FROM service_requests sr
        WHERE sr.org_id = :o AND sr.status <> 'resolved'
          AND (SELECT m.author_side FROM service_request_messages m
               WHERE m.request_id = sr.request_id ORDER BY m.created_at DESC LIMIT 1) = 'support'
    """), {"o": org_id}).scalar() or 0
    if awaiting:
        tasks.append(_task("support_reply", messages.render("horizon.task.support_reply", n=awaiting),
                           "info", "support_reply", "/support", "portal.use"))

    if org_type == "manufacturer":
        period = _reporting_period_task(session, org_id)
        if period:
            tasks.append(period)

    # intake phase 6: new data on assets a frozen filing rests on — the filing is never touched, only flagged
    from services.governance.data_revisions import flagged_filings
    flagged = flagged_filings(session, org_id)
    if flagged:
        tasks.append(_task("filings_new_data", messages.render("horizon.task.filings_new_data", n=len(flagged)),
                           "warning", "filings_new_data", "/filings" if org_type == "manufacturer" else "/compliance",
                           "reports.view"))

    return _finalize(tasks, perms)


def _reporting_period_task(session, org_id: str) -> Optional[dict]:
    """The agricultural reporting period ending (or ended) within 60 days while no live ESRS statement exists for it —
    a REAL forward date from the organisation's reporting basis, bucketed by proximity."""
    from datetime import date
    from datetime import datetime as _dt

    from services.governance.reporting_settings import get_settings
    pe = get_settings(session, org_id).get("reporting_period_end")
    if not pe:
        return None
    end = _dt.strptime(pe, "%Y-%m-%d").date()
    days = (end - date.today()).days
    if days > 60:
        return None
    done = session.execute(text("""
        SELECT 1 FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND framework = 'esrs_pack'
           AND period_end = :pe AND status NOT IN ('superseded', 'withdrawn') LIMIT 1
    """), {"o": org_id, "pe": end}).first()
    if done:
        return None
    bucket = "overdue" if days < 0 else ("this_week" if days <= 7 else "upcoming")
    msg = messages.render("horizon.task.period_ended" if days < 0 else "horizon.task.period_ends", date=pe)
    return _task("reporting_period", msg, "warning" if days <= 7 else "info", "reporting_period", "/esrs",
                 "admin.users.manage", bucket=bucket)
