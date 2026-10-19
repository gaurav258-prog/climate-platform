"""Sector-aware filing-readiness checklist — the one 'is my house in order' signal.

This is the canonical readiness computation, shared by the admin Control Center (deep view) and the
Horizon front-door KPI (glance view) so both report the SAME real number. It is a pass/fail checklist
with a passed/total count — never a fabricated percentage or grade.

Sector-awareness: the site/plot/EUDR/calibration/input-quality checks are agriculture-shaped (they query
sc_company_sites / sc_sourcing_plots), so a bank or insurer would falsely read 'not ready' on them. Those
checks apply ONLY to manufacturer (agri) orgs. Financial sectors get the cross-sector controls that
genuinely apply to them (a filing contact, 4-eyes, a fresh golden source); a supervisory body, which files nothing
and decides no approvals, only the last. Nothing is invented — every
check reads a real signal, and a sector simply omits the checks that do not apply to it.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages

# The workflow destination that REMEDIATES each check — the single source of truth for "where do I go to fix
# this?", colocated with the check definitions so the cockpit never hardcodes a route. Keyed by check key;
# golden_source is sector-nuanced (handled in _attach_fix). A check with no entry simply isn't click-through. The
# button's words are the catalogue's (names "horizon.action").
_FIX: dict[str, str] = {
    "identity":             "/admin?setup=identity",
    "second_approver":      "/admin?tab=team",
    "sites_scored":         "/operations",
    "plots_polygons":       "/sourcing",
    "eudr_run":             "/eudr",
    "calibrations_current": "/models",
    "inputs_high_quality":  "/data",
}


def _attach_fix(checks: list[dict], is_agri: bool) -> list[dict]:
    """Stamp each check with the workflow page that fixes it (fix_href/fix_label). The cockpit renders a
    failing check as a click-through straight to that page — the workflow, not the UI, owns the routing."""
    for c in checks:
        href = ("/foundation" if is_agri else "/data") if c["key"] == "golden_source_fresh" else _FIX.get(c["key"])
        c["fix_href"] = href
        c["fix_label"] = messages.name("horizon.action", c["key"]) if href else None
    return checks


def _check(key: str, ok: bool, **params) -> dict:
    """One check in customer words (core/messages.py): its name is the catalogue's horizon.readiness.<key>; a failing
    check carries horizon.readiness.<key>.failing with the values that say what is missing. `label` and `hint` are
    the same words for the screens that print them as a line (Control Center, board pack, controls register)."""
    passed = messages.render(f"horizon.readiness.{key}", **params)
    failing = None if ok else messages.render(f"horizon.readiness.{key}.failing", **params)
    return {"key": key, "label": passed["label"], "ok": ok, "message": failing or passed,
            "hint": failing["detail"].get("what") if failing else None}


def _names(items: list[str], limit: int = 4) -> str:
    """'A, B, C and 2 more' — a short list of names for a message value."""
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f" and {len(items) - limit} more"


def org_readiness(session: Session, org_id: str, org_type: str | None) -> dict:
    """Return {passed, total, checks:[{key,label,ok,hint,message,fix_href,fix_label}]} for this org, sector-aware.

    For a manufacturer (agri) org the checklist and order are identical to the Control Center's original
    eight checks. A supervisory body files nothing, so it has no reporting-identity check; every other sector
    has the three cross-sector controls."""
    is_agri = org_type == "manufacturer"

    org = session.execute(text("""
        SELECT eori, filing_contact_email, lei FROM organizations WHERE org_id = :o
    """), {"o": org_id}).mappings().first()

    # A second person who can approve — 4-eyes only works with two (cross-sector).
    n_approvers = session.execute(text("""
        SELECT count(DISTINCT u.user_id) FROM users u
        JOIN user_roles ur ON ur.user_id=u.user_id JOIN role_permissions rp ON rp.role_id=ur.role_id
        JOIN permissions p ON p.permission_id=rp.permission_id
        WHERE u.org_id=:o AND u.status='active' AND p.code='approvals.decide'
    """), {"o": org_id}).scalar()

    from services.data.feeds import ensure_basis_fresh
    fresh = ensure_basis_fresh(session)          # safety net: auto-refresh overdue basis feeds on read (throttled)
    overdue = fresh["overdue"]
    golden_source_check = _check("golden_source_fresh", not overdue, sources=_names([f["name"] for f in overdue]))
    second_approver_check = _check("second_approver", (n_approvers or 0) >= 2)

    def _identity(identifier_key: str, has_id: bool) -> dict:
        missing = [messages.name("horizon.identifier", k) for k, ok in
                   ((identifier_key, has_id), ("filing_contact", bool(org and org["filing_contact_email"]))) if not ok]
        return _check("identity", not missing, identifier=messages.name("horizon.identifier", identifier_key),
                      missing=" and ".join(missing))

    if not is_agri:
        # Financial sectors: a filing needs a filing contact + LEI, a second approver, and a fresh basis. A supervisory
        # body files nothing and its roles decide no approvals (its role templates grant none), so it has neither the
        # identity nor the second-approver check.
        from services.governance.tenant_provisioning import role_templates_for
        decides = any("approvals.decide" in perms for perms in role_templates_for(org_type or "").values())
        checks = ([] if org_type == "regulator" else [_identity("lei", bool(org and org["lei"]))]) \
            + ([second_approver_check] if decides else []) + [golden_source_check]
        passed = sum(1 for c in checks if c["ok"])
        return {"passed": passed, "total": len(checks), "checks": _attach_fix(checks, is_agri)}

    # ── Agriculture (manufacturer): the full eight, identical to the Control Center ──────────────────
    sites = session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE v.physical_risk_score IS NOT NULL) scored
        FROM sc_company_sites s
        LEFT JOIN LATERAL (
            SELECT physical_risk_score FROM v_sc_site_physical_risk v
            WHERE v.site_id = s.site_id AND v.scenario='baseline' AND v.time_horizon='current'
            ORDER BY physical_risk_score DESC NULLS LAST LIMIT 1) v ON true
        WHERE s.org_id = :o
    """), {"o": org_id}).mappings().first()
    plots = session.execute(text("""
        SELECT count(*) FILTER (WHERE p.plot_geometry IS NULL AND p.plot_area_ha > 4) needs_polygon,
               count(*) FILTER (WHERE co.eudr_covered) eudr_covered
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o
    """), {"o": org_id}).mappings().first()

    from services.eudr.reading import for_org, tally
    t = tally(for_org(session, org_id, covered_only=True))
    n_sites, n_scored = sites["n"] or 0, sites["scored"] or 0
    if n_sites:
        sites_check = _check("sites_scored", n_scored == n_sites, n=n_sites - n_scored)
    else:                                          # nothing to score yet: the check fails on a missing book, not a count
        none = messages.render("horizon.readiness.sites_scored.none")
        sites_check = {"key": "sites_scored", "label": messages.label("horizon.readiness.sites_scored"), "ok": False,
                       "message": none, "hint": none["detail"]["what"]}
    checks = [
        _identity("eori", bool(org and org["eori"])),
        sites_check,
        _check("plots_polygons", (plots["needs_polygon"] or 0) == 0, n=plots["needs_polygon"] or 0),
        _check("eudr_run", t["unread"] == 0, n=t["unread"]),
        second_approver_check,
        golden_source_check,
    ]
    from services.intelligence.revalidation import revalidation_status
    from services.reference.countries import english_name
    rv = revalidation_status(session)
    checks.append(_check("calibrations_current", rv["overdue_count"] == 0, years=rv["horizon_years"],
                         models=_names([f"{o['commodity']} in {english_name(o['origin']) or o['origin']} "
                                        f"(data to {o['trained_through']})" for o in rv["overdue"]])))
    from services.intelligence.input_quality import input_quality_status
    iq = input_quality_status(session, org_id)

    def _listed(items: list[dict]) -> str:
        return f"{len(items)} ({_names([x['name'] for x in items], 3)})" if items else "none"
    checks.append(_check("inputs_high_quality", iq["all_clear"], coarse=_listed(iq["low_confidence"]),
                         unscored=_listed(iq["insufficient_data"])))
    passed = sum(1 for c in checks if c["ok"])
    return {"passed": passed, "total": len(checks), "checks": _attach_fix(checks, is_agri)}
