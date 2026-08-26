"""Onboarding tracker — the single 'are we live?' state for a client tenant.

Reads each onboarding step's REAL readiness signal from the platform (identity stamped, users invited, book
loaded, engine configured, governance set, book scored, first filing) and returns a checklist with completion.
This powers both the guided onboarding flow (each step links to the surface that completes it) and the go-live
gate: a tenant is live when every REQUIRED step is done. Nothing here is a stored flag — it is derived, so it
can never drift from the truth on the ground.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_FIN = {"bank", "insurer", "reit", "asset_manager"}


def _scalar(session: Session, sql: str, **params):
    try:
        return session.execute(text(sql), params).scalar()
    except Exception:   # noqa: BLE001 — a missing table/relation must degrade to 'not done', never crash the tracker
        return None


def onboarding_status(session: Session, org_id: str) -> dict:
    """The onboarding checklist for one tenant, with each step's live done-state, detail, and the route that
    completes it. Optional steps don't gate go-live."""
    org = session.execute(text("""
        SELECT name, type, legal_name, lei, filing_contact_email, created_at FROM organizations WHERE org_id = CAST(:o AS uuid)
    """), {"o": org_id}).mappings().first()
    if not org:
        return {"available": False, "reason": "org_not_found"}
    otype = org["type"]

    n_users = _scalar(session, "SELECT count(*) FROM users WHERE org_id = CAST(:o AS uuid) AND status = 'active'", o=org_id) or 0

    # book loaded — org-type-aware (FIN books vs agri sites/plots)
    if otype in _FIN:
        n_book = _scalar(session, "SELECT count(*) FROM portfolio_entities WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
        book_noun = "holdings / assets"
    else:
        n_plots = _scalar(session, "SELECT count(*) FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
        n_sites = _scalar(session, "SELECT count(*) FROM sc_company_sites WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
        n_book = n_plots + n_sites
        book_noun = "sites / sourcing plots"

    # scored — entities/plots carrying a physical-risk score
    if otype in _FIN:
        n_scored = _scalar(session, """
            SELECT count(DISTINCT e.entity_id) FROM portfolio_entities e
            JOIN v_portfolio_entity_physical_risk v ON v.entity_id = e.entity_id
            WHERE e.org_id = CAST(:o AS uuid) AND v.physical_risk_score IS NOT NULL""", o=org_id) or 0
    else:
        n_scored = _scalar(session, """
            SELECT count(DISTINCT p.plot_id) FROM sc_sourcing_plots p
            JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id
            WHERE p.org_id = CAST(:o AS uuid) AND v.physical_risk_score IS NOT NULL""", o=org_id) or 0

    n_source = _scalar(session, "SELECT count(*) FROM source_systems WHERE org_id = CAST(:o AS uuid)", o=org_id)
    has_basis = bool(_scalar(session, "SELECT 1 FROM org_reporting_settings WHERE org_id = CAST(:o AS uuid) LIMIT 1", o=org_id))
    has_policy = bool(_scalar(session, "SELECT 1 FROM approval_policy WHERE org_id = CAST(:o AS uuid) LIMIT 1", o=org_id))
    n_filings = _scalar(session, "SELECT count(*) FROM regulatory_filing WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
    n_contracts = _scalar(session, "SELECT count(*) FROM customer_contract WHERE org_id = CAST(:o AS uuid)", o=org_id)

    steps = [
        {"key": "tenant", "phase": "Provision", "title": "Client tenant created",
         "done": True, "optional": False, "detail": f"{org['name']} · {otype.replace('_', ' ')}", "route": "/platform"},
        {"key": "identity", "phase": "Provision", "title": "Reporting identity",
         "done": bool(org["legal_name"] and org["lei"]), "optional": False,
         "detail": (f"LEI {org['lei']}" if org["lei"] else "legal name + LEI not set — look up in GLEIF"), "route": "/admin"},
        {"key": "access", "phase": "Provision", "title": "People & access",
         "done": n_users >= 1, "optional": False,
         "detail": f"{n_users} active user{'s' if n_users != 1 else ''}" + (" — invite the team" if n_users < 2 else ""), "route": "/admin"},
        {"key": "contracts", "phase": "Provision", "title": "Signed contracts on file",
         "done": (n_contracts or 0) > 0, "optional": True,
         "detail": f"{n_contracts or 0} contract{'s' if (n_contracts or 0) != 1 else ''}", "route": "/contracts"},
        {"key": "book", "phase": "Load & configure", "title": "Book loaded to the golden source",
         "done": n_book > 0, "optional": False, "detail": f"{n_book} {book_noun}", "route": "/data"},
        {"key": "systems", "phase": "Load & configure", "title": "Source systems connected",
         "done": (n_source or 0) > 0, "optional": True,
         "detail": f"{n_source or 0} system{'s' if (n_source or 0) != 1 else ''} registered", "route": "/admin"},
        {"key": "engine", "phase": "Load & configure", "title": "Reporting basis configured",
         "done": has_basis, "optional": False,
         "detail": "period / scenario / horizon set" if has_basis else "using platform defaults — confirm the basis", "route": "/admin"},
        {"key": "governance", "phase": "Govern & go live", "title": "Governance set up",
         "done": has_policy, "optional": False,
         "detail": "approval matrix configured" if has_policy else "using default 4-eyes rules — review", "route": "/admin"},
        {"key": "scored", "phase": "Govern & go live", "title": "Book scored & verified",
         "done": n_scored > 0, "optional": False,
         "detail": f"{n_scored} of {n_book} scored" if n_book else "load the book first", "route": "/"},
        {"key": "filing", "phase": "Govern & go live", "title": "First filing",
         "done": n_filings > 0, "optional": False,
         "detail": f"{n_filings} filing{'s' if n_filings != 1 else ''} created" if n_filings else "generate the first disclosure", "route": "/filings"},
    ]

    required = [s for s in steps if not s["optional"]]
    done_req = sum(1 for s in required if s["done"])
    n_done = sum(1 for s in steps if s["done"])
    return {
        "available": True, "org_id": org_id, "org_name": org["name"], "org_type": otype,
        "steps": steps,
        "required_total": len(required), "required_done": done_req,
        "total": len(steps), "done": n_done,
        "pct": round(100 * done_req / len(required)) if required else 100,
        "live": done_req == len(required),
        "next": next((s for s in steps if not s["optional"] and not s["done"]), None),
    }
