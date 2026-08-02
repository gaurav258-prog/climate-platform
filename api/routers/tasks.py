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

from typing import Optional

import h3
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
               a.outstanding_loan_balance_eur AS f_loan, a.sector AS f_sector, a.taxonomy_status AS f_tax,
               (COALESCE(a.ghg_emissions_scope1_tco2e,0)+COALESCE(a.ghg_emissions_scope2_tco2e,0)
                +COALESCE(a.ghg_emissions_scope3_tco2e,0)) AS f_ghg,
               v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
        FROM bank_assets a JOIN v_bank_asset_physical_risk v ON v.asset_id = a.asset_id
        WHERE a.org_id = :o AND a.latitude IS NOT NULL AND v.scenario = :sc
          AND (a.entity_id = CAST(:ent AS uuid) OR CAST(:ent AS uuid) IS NULL)"""},
    "insurer": {"noun": "insured locations", "sql": """
        SELECT p.policy_id AS id, p.policy_name AS name, 'policy' AS kind, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.region, p.country) AS region, p.sum_insured_eur AS value_eur,
               p.deductible_pct AS f_ded, p.construction_type AS f_ctype, p.year_built AS f_year, p.policy_type AS f_peril,
               v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
        FROM insurance_policies p JOIN v_insurance_policy_physical_risk v ON v.policy_id = p.policy_id
        WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc
          AND (p.entity_id = CAST(:ent AS uuid) OR CAST(:ent AS uuid) IS NULL)"""},
    "asset_manager": {"noun": "holdings", "sql": """
        SELECT h.holding_id AS id, h.holding_name AS name, 'holding' AS kind, h.latitude AS lat, h.longitude AS lon,
               COALESCE(h.region, h.country) AS region, h.position_value_eur AS value_eur,
               h.sector AS f_sector, h.nace_code AS f_nace,
               v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
        FROM assetmgmt_holdings h JOIN v_assetmgmt_holding_physical_risk v ON v.holding_id = h.holding_id
        WHERE h.org_id = :o AND h.latitude IS NOT NULL AND v.scenario = :sc
          AND (h.entity_id = CAST(:ent AS uuid) OR CAST(:ent AS uuid) IS NULL)"""},
    "reit": {"noun": "properties", "sql": """
        SELECT p.property_id AS id, p.property_name AS name, 'property' AS kind, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.region, p.country) AS region, p.property_value_eur AS value_eur,
               p.annual_noi_eur AS f_noi, p.property_type AS f_ptype, p.construction_type AS f_ctype, p.year_built AS f_year,
               v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
        FROM realestate_properties p JOIN v_realestate_property_physical_risk v ON v.property_id = p.property_id
        WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc
          AND (p.entity_id = CAST(:ent AS uuid) OR CAST(:ent AS uuid) IS NULL)"""},
}


def _eur(v) -> str:
    v = float(v or 0)
    if v >= 1e9: return f"€{v/1e9:.2f}bn"
    if v >= 1e6: return f"€{v/1e6:.1f}m"
    if v >= 1e3: return f"€{v/1e3:.0f}k"
    return f"€{v:.0f}"


# Per-sector "key parameters" for a clicked site — real columns from the sector's own table, mapped to
# labelled facets the detail panel renders. Every value is real; a missing column simply shows "—".
def _bank_facets(r):
    loan, av = r.get("f_loan"), r.get("value_eur")
    ltv = f"{round(100*float(loan)/float(av))}%" if loan and av else "—"
    out = [{"k": "Outstanding loan", "v": _eur(loan) if loan else "—"},
           {"k": "Loan-to-value", "v": ltv},
           {"k": "Financed emissions", "v": f"{float(r.get('f_ghg') or 0):,.0f} tCO₂e" if r.get("f_ghg") else "—"}]
    if r.get("f_sector"): out.append({"k": "Sector", "v": r["f_sector"]})
    if r.get("f_tax"): out.append({"k": "Taxonomy", "v": r["f_tax"]})
    return out


def _insurer_facets(r):
    out = [{"k": "Sum insured", "v": _eur(r.get("value_eur"))}]
    if r.get("f_ded") is not None: out.append({"k": "Deductible", "v": f"{r['f_ded']}%"})
    if r.get("f_ctype") or r.get("f_year"):
        out.append({"k": "Construction / year", "v": f"{r.get('f_ctype') or '—'} · {r.get('f_year') or '—'}"})
    if r.get("f_peril"): out.append({"k": "Cover", "v": r["f_peril"]})
    return out


def _am_facets(r):
    out = [{"k": "Position value", "v": _eur(r.get("value_eur"))}]
    if r.get("f_sector"): out.append({"k": "Sector", "v": r["f_sector"]})
    if r.get("f_nace"): out.append({"k": "NACE", "v": r["f_nace"]})
    return out


def _reit_facets(r):
    out = [{"k": "Property value", "v": _eur(r.get("value_eur"))}]
    if r.get("f_noi") is not None: out.append({"k": "Annual NOI", "v": _eur(r.get("f_noi"))})
    if r.get("f_ptype") or r.get("f_year"):
        out.append({"k": "Type / year", "v": f"{r.get('f_ptype') or '—'} · {r.get('f_year') or '—'}"})
    return out


def _site_facets(r):
    return [{"k": "Annual value", "v": _eur(r.get("value_eur"))}, {"k": "Country", "v": r.get("region") or "—"}]


def _plot_facets(r):
    out = [{"k": "Annual spend", "v": _eur(r.get("value_eur"))}]
    if r.get("f_commodity"): out.append({"k": "Commodity", "v": r["f_commodity"]})
    out.append({"k": "EUDR", "v": "covered · undetermined" if r.get("eudr_undetermined")
                else ("covered · determined" if r.get("f_eudr_covered") else "not covered")})
    if r.get("f_area"): out.append({"k": "Plot area", "v": f"{r['f_area']} ha"})
    return out


_FACET_FN = {"bank": _bank_facets, "insurer": _insurer_facets, "asset_manager": _am_facets, "reit": _reit_facets}


@router.get("/globe", summary="This org's real assets at true lat/lon with their projected risk trajectory")
def globe(session: DbSession, ctx: CurrentUser,
          scenario: str = Query("disorderly_2c", pattern="^(baseline|orderly_1_5c|disorderly_2c|hot_house_3_5c)$"),
          entity_id: Optional[str] = Query(None, description="scope to one reporting entity; null = all entities")):
    """Every located exposure this org holds, its coordinates, and its WORST-hazard physical-risk score at
    current / 2030 / 2050 / 2100 under the chosen warming path — sector-aware (bank→financed assets,
    insurer→insured locations, asset manager→holdings, REIT→properties, agri→sites + sourcing plots).
    Real coordinates + real projection scores off the golden source, no illustrative euros."""
    org_id = ctx["org"]["org_id"]
    org_type = session.execute(text("SELECT type FROM organizations WHERE org_id=:o"), {"o": org_id}).scalar()

    def _pivot(rows, facet_fn=None):
        by_asset: dict = {}
        for r in rows:
            if r["id"] not in by_asset:
                by_asset[r["id"]] = {
                    "id": str(r["id"]), "name": r["name"], "kind": r["kind"], "lat": float(r["lat"]),
                    "lon": float(r["lon"]), "region": r["region"], "value_eur": float(r["value_eur"] or 0),
                    "eudr_undetermined": bool(r.get("eudr_undetermined")),
                    "facets": (facet_fn(r) if facet_fn else []), "_haz": {}}
            by_asset[r["id"]]["_haz"].setdefault(r["hazard"], {})[r["horizon"]] = float(r["score"] or 0)
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
              AND (s.entity_id = CAST(:ent AS uuid) OR CAST(:ent AS uuid) IS NULL)
        """), {"o": org_id, "sc": scenario, "ent": entity_id}).mappings().all()
        plots = session.execute(text("""
            SELECT p.plot_id AS id, COALESCE(p.plot_name, co.name) AS name, 'plot' AS kind,
                   p.latitude AS lat, p.longitude AS lon, COALESCE(p.country, p.region) AS region,
                   p.annual_spend_eur AS value_eur,
                   (co.eudr_covered AND p.eudr_determination IS NULL) AS eudr_undetermined,
                   co.name AS f_commodity, co.eudr_covered AS f_eudr_covered, p.plot_area_ha AS f_area,
                   v.hazard_type AS hazard, v.time_horizon AS horizon, v.physical_risk_score AS score
            FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
            JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id
            WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc
              AND (p.entity_id = CAST(:ent AS uuid) OR CAST(:ent AS uuid) IS NULL)
        """), {"o": org_id, "sc": scenario, "ent": entity_id}).mappings().all()
        assets = _pivot(sites, _site_facets) + _pivot(plots, _plot_facets)
        # portfolio euro-at-risk TODAY is the real supply-engine figure (org-wide only — the engine isn't
        # entity-scoped yet, so we don't show an org number against a single entity's book)
        if entity_id is None:
            try:
                from services.intelligence.supply_cogs import project_org_supply
                summ = project_org_supply(session, org_id)
                vol_today = round(summ.volume_at_risk_eur or 0)
            except Exception:
                vol_today = None
    elif org_type in _SECTOR_ASSETS:
        cfg = _SECTOR_ASSETS[org_type]
        noun = cfg["noun"]
        rows = session.execute(text(cfg["sql"]), {"o": org_id, "sc": scenario, "ent": entity_id}).mappings().all()
        assets = _pivot(rows, _FACET_FN.get(org_type))
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


@router.get("/entities", summary="The reporting entities this org holds — the analyst scopes their work to one")
def entities(session: DbSession, ctx: CurrentUser):
    """Real reporting entities (legal entity / fund / client / …) for the logged-in org, each with a live
    count of the located assets assigned to it. The analyst picks one to scope the globe/KPIs/tasks; the
    implicit 'All entities' (entity_id=null) is the whole org. Assets are counted across every sector table
    so the count is right whatever the sector."""
    org_id = ctx["org"]["org_id"]
    rows = session.execute(text("""
        SELECT e.entity_id, e.name, e.kind,
               (SELECT count(*) FROM bank_assets a WHERE a.entity_id = e.entity_id)
             + (SELECT count(*) FROM insurance_policies p WHERE p.entity_id = e.entity_id)
             + (SELECT count(*) FROM assetmgmt_holdings h WHERE h.entity_id = e.entity_id)
             + (SELECT count(*) FROM realestate_properties r WHERE r.entity_id = e.entity_id)
             + (SELECT count(*) FROM sc_company_sites s WHERE s.entity_id = e.entity_id)
             + (SELECT count(*) FROM sc_sourcing_plots pl WHERE pl.entity_id = e.entity_id) AS n_assets
        FROM reporting_entities e WHERE e.org_id = :o ORDER BY e.name
    """), {"o": org_id}).mappings().all()
    return {"entities": [{"entity_id": str(r["entity_id"]), "name": r["name"], "kind": r["kind"],
                          "n_assets": int(r["n_assets"])} for r in rows]}


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

    out = []
    for c in cells:
        b = h3.cell_to_boundary(c)  # [(lat, lng), ...]
        out.append({"cell": c, "is_center": c == center,
                    "boundary": [[round(p[0], 5), round(p[1], 5)] for p in b],
                    "score": (round(score_by[c], 1) if c in score_by else None)})
    scored_n = sum(1 for c in cells if c in score_by)
    return {"center": center, "resolution": 8, "cell_km": 0.7, "scenario": scenario, "horizon": horizon,
            "center_score": (round(score_by[center], 1) if center in score_by else None),
            "n_cells": len(cells), "n_scored": scored_n, "computing": computing, "cells": out}

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
def my_tasks(session: DbSession, ctx: CurrentUser,
             entity_id: Optional[str] = Query(None, description="scope asset-completeness tasks to one entity")):
    org_id = ctx["org"]["org_id"]
    org_type = session.execute(text("SELECT type FROM organizations WHERE org_id=:o"), {"o": org_id}).scalar()
    is_agri = org_type == "manufacturer"
    perms = set(ctx.get("permissions") or [])
    tasks: list[dict] = []

    # ── APPROVER: decisions waiting (bucket from the OLDEST pending request's real age vs our SLA) ────
    # Only requests THIS user can actually action — a decider can't approve their own (4-eyes), so a
    # request they raised is not "waiting for you". Count excludes own; a request assigned to someone
    # else is still counted (any approver may act unless assignment routes it — keep it discoverable).
    me = ctx["user"]["id"]
    prow = session.execute(text(
        "SELECT count(*) n, EXTRACT(EPOCH FROM (now()-min(created_at)))/86400 AS oldest_days "
        "FROM approval_requests WHERE org_id=:o AND status='pending' AND maker_user_id <> :u"),
        {"o": org_id, "u": me}).mappings().first()
    pending = prow["n"] or 0
    if pending:
        age = float(prow["oldest_days"] or 0)
        past_sla = age > _APPROVAL_SLA_DAYS
        tasks.append(_task(
            "approvals_pending", f"{pending} approval{'s' if pending != 1 else ''} waiting for you",
            "Review and approve, reject, or send back — the second pair of eyes in 4-eyes.",
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
            "warning", "Finish setup", "/admin?setup=identity", "admin.users.manage"))

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
            failed = [f for f in overdue if f.get("status") == "failed"]
            max_days = max((f.get("days_since") or 0) for f in overdue)
            title = "A golden source failed its auto-refresh" if failed else "A golden source is overdue"
            detail = ((("Automated refresh FAILED: " + ", ".join(f["name"] for f in failed[:3]))
                       if failed else ("Overdue: " + ", ".join(f["name"] for f in overdue[:3])))
                      + ". Fix it before you file — the automated pull needs attention.")
            tasks.append(_task(
                "golden_source_stale", title, detail,
                "warning", "Review data", "/foundation", "admin.users.manage",
                bucket="overdue", due=(f"{len(failed)} failed" if failed else f"{max_days:.0f}d overdue")))
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
          AND (s.entity_id = CAST(:ent AS uuid) OR CAST(:ent AS uuid) IS NULL)
    """), {"o": org_id, "ent": entity_id}).mappings().first()
    plots = session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE p.plot_geometry IS NULL AND p.plot_area_ha > 4) needs_polygon,
               count(*) FILTER (WHERE co.eudr_covered AND p.eudr_determination IS NULL) needs_eudr
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id=p.commodity_id
        WHERE p.org_id=:o
          AND (p.entity_id = CAST(:ent AS uuid) OR CAST(:ent AS uuid) IS NULL)
    """), {"o": org_id, "ent": entity_id}).mappings().first()

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
