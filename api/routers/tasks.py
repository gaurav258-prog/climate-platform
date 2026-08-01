"""What needs YOU now — a role-filtered, severity-ranked task feed for the cockpit.

The platform already computes every "preemptive" signal (pending approvals, golden-source staleness,
calibration drift, input quality, EUDR polygons, unscored sites, filing identity). They lived only in the
admin Control-Center readiness list. This assembles them into one actionable feed, filtered to what THIS
user can act on (by permission) so each role lands on their own work:
  * approver → approvals waiting          (approvals.decide)
  * admin    → setup / house-in-order     (admin.users.manage)
  * analyst  → data & filing completeness  (modules.view)
  * viewer   → sees the same awareness items, read-only

Nothing here is a new number — it's routing the signals we have to the person who acts on them.
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import text

from api.deps import CurrentUser, DbSession

router = APIRouter(prefix="/v1/me", tags=["Me"])

# Horizon (the globe) forward path — real projection scores, not a fabricated flare year.
_HORIZONS = ["current", "2030", "2050", "2100"]

# The globe is the front door for EVERY sector. Each org type keeps its located exposures in its own
# table + a physical-risk view of identical shape (id, h3_cell, hazard_type, scenario, time_horizon,
# physical_risk_score). We dispatch by organizations.type so a bank sees financed assets, an insurer sees
# insured locations, an asset manager sees holdings, a REIT sees properties — all on the same real globe,
# scored off the same golden source. `noun` drives the UI copy; agri (manufacturer) is handled separately
# because it unions two tables (own sites + sourcing plots) and carries the EUDR flag.
_SECTOR_ASSETS = {
    "bank": {"noun": "financed assets", "sql": """
        SELECT a.asset_id AS id, a.asset_name AS name, 'asset' AS kind, a.latitude AS lat, a.longitude AS lon,
               COALESCE(a.region, a.country) AS region, a.asset_value_eur AS value_eur,
               v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
        FROM bank_assets a JOIN v_bank_asset_physical_risk v ON v.asset_id = a.asset_id
        WHERE a.org_id = :o AND a.latitude IS NOT NULL AND v.scenario = :sc"""},
    "insurer": {"noun": "insured locations", "sql": """
        SELECT p.policy_id AS id, p.policy_name AS name, 'policy' AS kind, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.region, p.country) AS region, p.sum_insured_eur AS value_eur,
               v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
        FROM insurance_policies p JOIN v_insurance_policy_physical_risk v ON v.policy_id = p.policy_id
        WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc"""},
    "asset_manager": {"noun": "holdings", "sql": """
        SELECT h.holding_id AS id, h.holding_name AS name, 'holding' AS kind, h.latitude AS lat, h.longitude AS lon,
               COALESCE(h.region, h.country) AS region, h.position_value_eur AS value_eur,
               v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
        FROM assetmgmt_holdings h JOIN v_assetmgmt_holding_physical_risk v ON v.holding_id = h.holding_id
        WHERE h.org_id = :o AND h.latitude IS NOT NULL AND v.scenario = :sc"""},
    "reit": {"noun": "properties", "sql": """
        SELECT p.property_id AS id, p.property_name AS name, 'property' AS kind, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.region, p.country) AS region, p.property_value_eur AS value_eur,
               v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
        FROM realestate_properties p JOIN v_realestate_property_physical_risk v ON v.property_id = p.property_id
        WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc"""},
}


@router.get("/globe", summary="This org's real assets at true lat/lon with their projected risk trajectory")
def globe(session: DbSession, ctx: CurrentUser,
          scenario: str = Query("disorderly_2c", pattern="^(baseline|orderly_1_5c|disorderly_2c|hot_house_3_5c)$")):
    """Every located exposure this org holds, its coordinates, and its WORST-hazard physical-risk score at
    current / 2030 / 2050 / 2100 under the chosen warming path — sector-aware (bank→financed assets,
    insurer→insured locations, asset manager→holdings, REIT→properties, agri→sites + sourcing plots).
    Real coordinates + real projection scores off the golden source, no illustrative euros."""
    org_id = ctx["org"]["org_id"]
    org_type = session.execute(text("SELECT type FROM organizations WHERE org_id=:o"), {"o": org_id}).scalar()

    def _pivot(rows):
        by_asset: dict = {}
        for r in rows:
            a = by_asset.setdefault(r["id"], {
                "id": str(r["id"]), "name": r["name"], "kind": r["kind"], "lat": float(r["lat"]),
                "lon": float(r["lon"]), "region": r["region"], "value_eur": float(r["value_eur"] or 0),
                "eudr_undetermined": bool(r.get("eudr_undetermined")), "_haz": {}})
            a["_haz"].setdefault(r["hazard"], {})[r["horizon"]] = float(r["score"] or 0)
        out = []
        from services.intelligence.adaptation import actions_for
        for a in by_asset.values():
            # worst hazard = highest score at 2050 (the CSRD forward anchor), fallback current
            worst = max(a["_haz"].items(),
                        key=lambda kv: kv[1].get("2050", kv[1].get("current", 0)))
            a["hazard"] = worst[0]
            a["traj"] = {h: round(worst[1].get(h, worst[1].get("current", 0)), 1) for h in _HORIZONS}
            # real adaptation measures for this hazard (honest actions, not a fabricated % reduction)
            try:
                acts = actions_for([a["hazard"]])
                a["adaptations"] = acts[0]["actions"][:3] if acts else []
            except Exception:
                a["adaptations"] = []
            a.pop("_haz")
            out.append(a)
        return out

    vol_today = None
    if org_type == "manufacturer":
        # Agriculture: own operational sites UNION sourcing plots (the plots carry the EUDR flag).
        noun = "sites & origins"
        sites = session.execute(text("""
            SELECT s.site_id AS id, s.name, 'site' AS kind, s.latitude AS lat, s.longitude AS lon,
                   s.country AS region, s.annual_value_eur AS value_eur,
                   v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
            FROM sc_company_sites s JOIN v_sc_site_physical_risk v ON v.site_id = s.site_id
            WHERE s.org_id = :o AND s.latitude IS NOT NULL AND v.scenario = :sc
        """), {"o": org_id, "sc": scenario}).mappings().all()
        plots = session.execute(text("""
            SELECT p.plot_id AS id, COALESCE(p.plot_name, co.name) AS name, 'plot' AS kind,
                   p.latitude AS lat, p.longitude AS lon, COALESCE(p.country, p.region) AS region,
                   p.annual_spend_eur AS value_eur,
                   (co.eudr_covered AND p.eudr_determination IS NULL) AS eudr_undetermined,
                   v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
            FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
            JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id
            WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc
        """), {"o": org_id, "sc": scenario}).mappings().all()
        assets = _pivot(sites) + _pivot(plots)
        # portfolio euro-at-risk TODAY is the real supply-engine figure (not derived from scores)
        try:
            from services.intelligence.supply_cogs import project_org_supply
            summ = project_org_supply(session, org_id)
            vol_today = round(summ.volume_at_risk_eur or 0)
        except Exception:
            vol_today = None
    elif org_type in _SECTOR_ASSETS:
        cfg = _SECTOR_ASSETS[org_type]
        noun = cfg["noun"]
        rows = session.execute(text(cfg["sql"]), {"o": org_id, "sc": scenario}).mappings().all()
        assets = _pivot(rows)
    else:
        noun, assets = "assets", []

    # ── left-rail KPIs (org) — all real: book value from the assets, elevated from the 2050 worst-hazard
    #    score, readiness from the shared sector-aware checklist. No fabricated grade. ────────────────
    n_elevated = sum(1 for a in assets if a["traj"].get("2050", a["traj"].get("current", 0)) >= 50)
    book_value = round(sum(a["value_eur"] for a in assets))
    from services.governance.readiness import org_readiness
    rd = org_readiness(session, org_id, org_type)
    kpis = {"book_value_eur": book_value, "n_assets": len(assets), "n_elevated": n_elevated,
            "readiness": {"passed": rd["passed"], "total": rd["total"], "checks": rd["checks"]},
            "volume_at_risk_eur_today": vol_today}

    # ── left-rail 'my scope' — assets are org-scoped (no per-user ownership), so this is honestly
    #    "what YOU can act on": your roles + the approvals YOU raised that are still pending. The count of
    #    your open actions is the /v1/me/tasks feed length (already permission-filtered), read client-side.
    me = ctx["user"]["id"]
    raised_pending = session.execute(text(
        "SELECT count(*) FROM approval_requests WHERE org_id=:o AND maker_user_id=:u AND status='pending'"),
        {"o": org_id, "u": me}).scalar() or 0
    my_scope = {"roles": ctx.get("roles", []), "raised_pending": int(raised_pending)}

    return {"scenario": scenario, "sector": org_type, "noun": noun, "horizons": _HORIZONS,
            "n_assets": len(assets), "volume_at_risk_eur_today": vol_today,
            "kpis": kpis, "my_scope": my_scope, "assets": assets}

# severity → sort weight (higher first). action = needs a decision/edit; warning = will block a filing;
# info = awareness; good = a positive confirmation.
_WEIGHT = {"action": 3, "warning": 2, "info": 1, "good": 0}


# Approval service-level target — a decision that has waited longer than this is treated as overdue. This
# is OUR disclosed SLA (there is no regulatory approval deadline), surfaced as such in the UI, not a
# fabricated regulator date.
_APPROVAL_SLA_DAYS = 3

# Task urgency bucket. "overdue"/"this_week"/"upcoming" are only assigned when a REAL time basis exists
# (feed age, approval age, revalidation lag, reporting-period end). Everything else is honestly "open" —
# a real action with no fixed date — never given an invented deadline.
_BUCKET_ORDER = {"overdue": 0, "this_week": 1, "upcoming": 2, "open": 3}


def _task(key, title, detail, severity, cta_label, cta_href, need, bucket="open", due=None):
    return {"key": key, "title": title, "detail": detail, "severity": severity,
            "cta_label": cta_label, "cta_href": cta_href, "_need": need, "bucket": bucket, "due": due}


def _finalize(tasks: list[dict], perms: set) -> dict:
    """Keep only tasks this user may act on, drop the private _need, rank by severity."""
    visible = [t for t in tasks if t["_need"] in perms]
    for t in visible:
        t.pop("_need", None)
    # time bucket first (overdue → this_week → upcoming → open), severity as the tie-break within a bucket
    visible.sort(key=lambda t: (_BUCKET_ORDER.get(t["bucket"], 3), -_WEIGHT.get(t["severity"], 0)))
    return {"tasks": visible, "all_clear": len(visible) == 0}


@router.get("/tasks", summary="Role-filtered actionable tasks for the cockpit")
def my_tasks(session: DbSession, ctx: CurrentUser):
    org_id = ctx["org"]["org_id"]
    org_type = session.execute(text("SELECT type FROM organizations WHERE org_id=:o"), {"o": org_id}).scalar()
    is_agri = org_type == "manufacturer"
    perms = set(ctx.get("permissions") or [])
    tasks: list[dict] = []

    # ── APPROVER: decisions waiting (bucket from the OLDEST pending request's real age vs our SLA) ────
    prow = session.execute(text(
        "SELECT count(*) n, EXTRACT(EPOCH FROM (now()-min(created_at)))/86400 AS oldest_days "
        "FROM approval_requests WHERE org_id=:o AND status='pending'"), {"o": org_id}).mappings().first()
    pending = prow["n"] or 0
    if pending:
        age = float(prow["oldest_days"] or 0)
        past_sla = age > _APPROVAL_SLA_DAYS
        tasks.append(_task(
            "approvals_pending", f"{pending} approval{'s' if pending != 1 else ''} waiting for you",
            "Review and approve or reject — the second pair of eyes in 4-eyes.",
            "action", "Review approvals", "/approvals", "approvals.decide",
            bucket="overdue" if past_sla else "this_week",
            due=(f"oldest raised {age:.0f}d ago · past the {_APPROVAL_SLA_DAYS}-day SLA" if past_sla
                 else f"oldest raised {age:.0f}d ago · {_APPROVAL_SLA_DAYS}-day SLA")))

    # ── ADMIN: is the house in order (setup + pre-filing controls) ────────────────────────────────
    org = session.execute(text(
        "SELECT eori, filing_contact_email FROM organizations WHERE org_id=:o"), {"o": org_id}).mappings().first()
    if org and not (org["eori"] and org["filing_contact_email"]):
        tasks.append(_task(
            "identity_incomplete", "Complete your reporting identity",
            "EORI and a filing-contact email are needed before a CSRD/EUDR filing.",
            "warning", "Finish setup", "/admin", "admin.users.manage"))

    n_approvers = session.execute(text("""
        SELECT count(DISTINCT u.user_id) FROM users u
        JOIN user_roles ur ON ur.user_id=u.user_id JOIN role_permissions rp ON rp.role_id=ur.role_id
        JOIN permissions p ON p.permission_id=rp.permission_id
        WHERE u.org_id=:o AND u.status='active' AND p.code='approvals.decide'
    """), {"o": org_id}).scalar() or 0
    if n_approvers < 2:
        tasks.append(_task(
            "second_approver", "Add a second approver",
            "4-eyes needs two people who can approve — invite a colleague with the Approver role.",
            "warning", "Invite a teammate", "/admin", "admin.users.manage"))

    try:
        from services.data.feeds import overdue_basis_feeds
        overdue = overdue_basis_feeds(session)
        if overdue:
            max_days = max((f.get("days_since") or 0) for f in overdue)
            tasks.append(_task(
                "golden_source_stale", "Refresh a stale golden source",
                "A basis feed is overdue: " + ", ".join(f["name"] for f in overdue[:3])
                + ". Refresh before you file.", "warning", "Review data", "/foundation", "admin.users.manage",
                bucket="overdue", due=f"{max_days:.0f}d overdue"))
    except Exception:
        pass

    if is_agri:
        try:
            from services.intelligence.revalidation import revalidation_status
            rv = revalidation_status(session)
            if rv["overdue_count"]:
                tasks.append(_task(
                    "calibrations_due", f"{rv['overdue_count']} crop calibration(s) due for re-validation",
                    "Their training window is far enough behind that new crop-years should re-check them.",
                    "info", "See models", "/models", "admin.users.manage",
                    bucket="overdue", due=f"{rv['overdue_count']} past the {rv['horizon_years']}y window"))
        except Exception:
            pass

    # ── ANALYST / DOER: data & filing completeness ────────────────────────────────────────────────
    # The site/plot/EUDR completeness signals below are agriculture-shaped (own ops + sourcing plots) and
    # route to the agri operating pages. Financial sectors keep their exposures elsewhere, so they see only
    # the cross-sector controls above (approvals, identity, 4-eyes, golden source) — never an agri prompt.
    if not is_agri:
        return _finalize(tasks, perms)

    # Reporting-period end — a REAL forward date (the org's reporting basis). Bucket by proximity so the
    # CSRD/ESRS filing shows up as overdue / this week / upcoming rather than as a date-less item.
    try:
        from datetime import date, datetime as _dt
        from services.governance.reporting_settings import get_settings
        pe = get_settings(session, org_id).get("reporting_period_end")
        if pe:
            days = (_dt.strptime(pe, "%Y-%m-%d").date() - date.today()).days
            if days <= 60:
                bucket = "overdue" if days < 0 else ("this_week" if days <= 7 else "upcoming")
                tasks.append(_task(
                    "reporting_period", f"CSRD/ESRS filing for period ending {pe}",
                    "Freeze the ESRS E1 filing for this reporting period once the book is complete.",
                    "warning" if days <= 7 else "info", "Open reporting", "/esrs", "admin.users.manage",
                    bucket=bucket, due=(f"period ended {-days}d ago" if days < 0 else f"period ends in {days}d")))
    except Exception:
        pass

    sites = session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE NOT EXISTS (
                   SELECT 1 FROM v_sc_site_physical_risk v
                   WHERE v.site_id=s.site_id AND v.scenario='baseline' AND v.time_horizon='current')) unscored
        FROM sc_company_sites s WHERE s.org_id=:o
    """), {"o": org_id}).mappings().first()
    plots = session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE p.plot_geometry IS NULL AND p.plot_area_ha > 4) needs_polygon,
               count(*) FILTER (WHERE co.eudr_covered AND p.eudr_determination IS NULL) needs_eudr
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id=p.commodity_id
        WHERE p.org_id=:o
    """), {"o": org_id}).mappings().first()

    if (sites["n"] or 0) == 0 and (plots["n"] or 0) == 0:
        tasks.append(_task(
            "first_run", "Add your first sites or suppliers",
            "Map an operational site or a sourcing plot to see its climate risk from the golden source.",
            "action", "Add operations", "/operations", "modules.view"))
    else:
        if plots["needs_polygon"]:
            tasks.append(_task(
                "plots_polygon", f"{plots['needs_polygon']} plot(s) over 4 ha need a boundary polygon",
                "EUDR needs a geometry, not just a point, for plots over 4 hectares.",
                "warning", "Fix in Sourcing", "/sourcing", "modules.view"))
        if plots["needs_eudr"]:
            tasks.append(_task(
                "eudr_run", f"Run EUDR determination on {plots['needs_eudr']} plot(s)",
                "Covered plots need a deforestation determination before the filing.",
                "action", "Open Disclosure", "/disclosure", "modules.view"))
        if sites["unscored"]:
            tasks.append(_task(
                "sites_unscored", f"{sites['unscored']} site(s) not yet scored",
                "A located site scores from the golden source shortly — check if any are stuck.",
                "info", "Open Operations", "/operations", "modules.view"))

    try:
        from services.intelligence.input_quality import input_quality_status
        iq = input_quality_status(session, org_id)
        if iq["low_confidence_count"]:
            tasks.append(_task(
                "low_confidence", f"{iq['low_confidence_count']} asset(s) located only coarsely",
                "A coarse geocode means an imprecise cell — refine before filing.",
                "info", "Review inputs", "/operations", "modules.view"))
    except Exception:
        pass

    return _finalize(tasks, perms)
