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


@router.get("/globe", summary="This org's real assets at true lat/lon with their projected risk trajectory")
def globe(session: DbSession, ctx: CurrentUser,
          scenario: str = Query("disorderly_2c", pattern="^(baseline|orderly_1_5c|disorderly_2c|hot_house_3_5c)$")):
    """Every located site + sourcing plot, its coordinates, and its WORST-hazard physical-risk score at
    current / 2030 / 2050 / 2100 under the chosen warming path. Real coordinates + real projection scores —
    the front-door globe reads straight off the golden source, no illustrative euros."""
    org_id = ctx["org"]["org_id"]

    def _pivot(rows):
        by_asset: dict = {}
        for r in rows:
            a = by_asset.setdefault(r["id"], {
                "id": str(r["id"]), "name": r["name"], "kind": r["kind"], "lat": float(r["lat"]),
                "lon": float(r["lon"]), "region": r["region"], "value_eur": float(r["value_eur"] or 0),
                "_haz": {}})
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
        vol_today = round(summ.get("rollup", {}).get("volume_at_risk_eur", 0))
    except Exception:
        vol_today = None

    return {"scenario": scenario, "horizons": _HORIZONS, "n_assets": len(assets),
            "volume_at_risk_eur_today": vol_today, "assets": assets}

# severity → sort weight (higher first). action = needs a decision/edit; warning = will block a filing;
# info = awareness; good = a positive confirmation.
_WEIGHT = {"action": 3, "warning": 2, "info": 1, "good": 0}


def _task(key, title, detail, severity, cta_label, cta_href, need):
    return {"key": key, "title": title, "detail": detail, "severity": severity,
            "cta_label": cta_label, "cta_href": cta_href, "_need": need}


@router.get("/tasks", summary="Role-filtered actionable tasks for the cockpit")
def my_tasks(session: DbSession, ctx: CurrentUser):
    org_id = ctx["org"]["org_id"]
    perms = set(ctx.get("permissions") or [])
    tasks: list[dict] = []

    # ── APPROVER: decisions waiting ───────────────────────────────────────────────────────────────
    pending = session.execute(text(
        "SELECT count(*) FROM approval_requests WHERE org_id=:o AND status='pending'"), {"o": org_id}).scalar() or 0
    if pending:
        tasks.append(_task(
            "approvals_pending", f"{pending} approval{'s' if pending != 1 else ''} waiting for you",
            "Review and approve or reject — the second pair of eyes in 4-eyes.",
            "action", "Review approvals", "/approvals", "approvals.decide"))

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
            tasks.append(_task(
                "golden_source_stale", "Refresh a stale golden source",
                "A basis feed is overdue: " + ", ".join(f["name"] for f in overdue[:3])
                + ". Refresh before you file.", "warning", "Review data", "/foundation", "admin.users.manage"))
    except Exception:
        pass

    try:
        from services.intelligence.revalidation import revalidation_status
        rv = revalidation_status(session)
        if rv["overdue_count"]:
            tasks.append(_task(
                "calibrations_due", f"{rv['overdue_count']} crop calibration(s) due for re-validation",
                "Their training window is far enough behind that new crop-years should re-check them.",
                "info", "See models", "/models", "admin.users.manage"))
    except Exception:
        pass

    # ── ANALYST / DOER: data & filing completeness ────────────────────────────────────────────────
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

    # keep only tasks this user has the permission to act on, drop the private _need, rank by severity
    visible = [t for t in tasks if t["_need"] in perms]
    for t in visible:
        t.pop("_need", None)
    visible.sort(key=lambda t: -_WEIGHT.get(t["severity"], 0))
    return {"tasks": visible, "all_clear": len(visible) == 0}
