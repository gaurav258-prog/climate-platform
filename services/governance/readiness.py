"""Sector-aware filing-readiness checklist — the one 'is my house in order' signal.

This is the canonical readiness computation, shared by the admin Control Center (deep view) and the
Horizon front-door KPI (glance view) so both report the SAME real number. It is a pass/fail checklist
with a passed/total count — never a fabricated percentage or grade.

Sector-awareness: the site/plot/EUDR/calibration/input-quality checks are agriculture-shaped (they query
sc_company_sites / sc_sourcing_plots), so a bank or insurer would falsely read 'not ready' on them. Those
checks apply ONLY to manufacturer (agri) orgs. Financial sectors get the cross-sector controls that
genuinely apply to them (a filing contact, 4-eyes, a fresh golden source). Nothing is invented — every
check reads a real signal, and a sector simply omits the checks that do not apply to it.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def org_readiness(session: Session, org_id: str, org_type: str | None) -> dict:
    """Return {passed, total, checks:[{key,label,ok,hint}]} for this org, sector-aware.

    For a manufacturer (agri) org the checklist and order are identical to the Control Center's original
    eight checks. For every other sector only the three cross-sector controls apply."""
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

    from services.data.feeds import overdue_basis_feeds
    overdue = overdue_basis_feeds(session)
    golden_source_check = {
        "key": "golden_source_fresh", "label": "Golden source is fresh (no overdue basis feed)",
        "ok": not overdue,
        "hint": (f"Refresh before filing — overdue: {', '.join(f['name'] for f in overdue)}." if overdue else None)}
    second_approver_check = {
        "key": "second_approver", "label": "A second approver exists (4-eyes works)", "ok": (n_approvers or 0) >= 2,
        "hint": "Only one user can approve — 4-eyes needs a second. Add an approver." if (n_approvers or 0) < 2 else None}

    if not is_agri:
        # Financial sectors: a filing needs a filing contact + LEI, a second approver, and a fresh basis.
        identity_ok = bool(org and org["filing_contact_email"] and org["lei"])
        checks = [
            {"key": "identity", "label": "Reporting identity complete (LEI + filing contact)", "ok": identity_ok,
             "hint": "Set the reporting LEI and a filing contact email." if not identity_ok else None},
            second_approver_check,
            golden_source_check,
        ]
        passed = sum(1 for c in checks if c["ok"])
        return {"passed": passed, "total": len(checks), "checks": checks}

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
               count(*) FILTER (WHERE co.eudr_covered) eudr_covered,
               count(*) FILTER (WHERE co.eudr_covered AND p.eudr_determination IS NOT NULL) eudr_determined
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o
    """), {"o": org_id}).mappings().first()

    identity_ok = bool(org and org["eori"] and org["filing_contact_email"])
    checks = [
        {"key": "identity", "label": "Reporting identity complete (EORI + filing contact)", "ok": identity_ok,
         "hint": "Set EORI and a filing contact email below." if not identity_ok else None},
        {"key": "sites_scored", "label": "All operational sites scored", "ok": (sites["n"] or 0) > 0 and sites["scored"] == sites["n"],
         "hint": f"{(sites['n'] or 0) - (sites['scored'] or 0)} site(s) not yet scored." if (sites["n"] or 0) and sites["scored"] != sites["n"] else ("Add your operational sites." if not sites["n"] else None)},
        {"key": "plots_polygons", "label": "All >4 ha plots have a polygon (EUDR)", "ok": (plots["needs_polygon"] or 0) == 0,
         "hint": f"{plots['needs_polygon']} plot(s) over 4 ha need a boundary polygon." if plots["needs_polygon"] else None},
        {"key": "eudr_run", "label": "EUDR determination run on covered plots", "ok": (plots["eudr_covered"] or 0) == 0 or plots["eudr_determined"] == plots["eudr_covered"],
         "hint": f"{(plots['eudr_covered'] or 0) - (plots['eudr_determined'] or 0)} covered plot(s) not yet checked." if (plots["eudr_covered"] or 0) and plots["eudr_determined"] != plots["eudr_covered"] else None},
        second_approver_check,
        golden_source_check,
    ]
    from services.intelligence.revalidation import revalidation_status
    rv = revalidation_status(session)
    checks.append({"key": "calibrations_current",
                   "label": f"Crop calibrations current (re-validated within {rv['horizon_years']}y)",
                   "ok": rv["overdue_count"] == 0,
                   "hint": (f"{rv['overdue_count']} calibration(s) due for re-validation: "
                            + ", ".join(f"{o['commodity']}·{o['origin']} (trained thru {o['trained_through']})"
                                        for o in rv["overdue"][:4]) + "." if rv["overdue_count"] else None)})
    from services.intelligence.input_quality import input_quality_status
    iq = input_quality_status(session, org_id)
    iq_bits = []
    if iq["low_confidence_count"]:
        iq_bits.append(f"{iq['low_confidence_count']} coarsely-located "
                       f"({', '.join(x['name'] for x in iq['low_confidence'][:3])})")
    if iq["insufficient_data_count"]:
        iq_bits.append(f"{iq['insufficient_data_count']} not yet scored "
                       f"({', '.join(x['name'] for x in iq['insufficient_data'][:3])})")
    checks.append({"key": "inputs_high_quality", "label": "Inputs are filing-grade (precise location + scored)",
                   "ok": iq["all_clear"],
                   "hint": ("Fix before filing — " + "; ".join(iq_bits) + "." if iq_bits else None)})
    passed = sum(1 for c in checks if c["ok"])
    return {"passed": passed, "total": len(checks), "checks": checks}
