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

from core import messages

_FIN = {"bank", "insurer", "reit", "asset_manager"}


def _scalar(session: Session, sql: str, **params):
    try:
        return session.execute(text(sql), params).scalar()
    except Exception:   # noqa: BLE001 — a missing table/relation must degrade to 'not done', never crash the tracker
        return None


# the checklist's phases, in order; each step's title, what it means (its ⓘ) and its live state are catalogue messages
# (platform.golive.*), never words written here
PHASES = ("provision", "load", "govern")


def _step(key: str, phase: str, done: bool, optional: bool, route: str, state: str, **params) -> dict:
    about = messages.render(f"platform.golive.step.{key}")
    return {"key": key, "phase": phase, "title": about["label"], "about": about, "done": done, "optional": optional,
            "message": messages.render(f"platform.golive.{key}.{state}", **params), "route": route}


def onboarding_status(session: Session, org_id: str) -> dict:
    """The onboarding checklist for one tenant, with each step's live done-state, the message that says where it
    stands, and the route that completes it. Optional steps don't gate go-live."""
    org = session.execute(text("""
        SELECT name, type, legal_name, lei, filing_contact_email, created_at FROM organizations WHERE org_id = CAST(:o AS uuid)
    """), {"o": org_id}).mappings().first()
    if not org:
        return {"available": False, "message": messages.render("platform.golive.unavailable")}
    otype = org["type"]

    n_users = _scalar(session, "SELECT count(*) FROM users WHERE org_id = CAST(:o AS uuid) AND status = 'active'", o=org_id) or 0

    # book loaded — org-type-aware (FIN books vs agri sites/plots)
    if otype in _FIN:
        n_book = _scalar(session, "SELECT count(*) FROM portfolio_entities WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
        book_state = "done_fin"
    else:
        n_plots = _scalar(session, "SELECT count(*) FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
        n_sites = _scalar(session, "SELECT count(*) FROM sc_company_sites WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
        n_book = n_plots + n_sites
        book_state = "done_agri"

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

    n_source = _scalar(session, "SELECT count(*) FROM source_systems WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
    has_basis = bool(_scalar(session, "SELECT 1 FROM org_reporting_settings WHERE org_id = CAST(:o AS uuid) LIMIT 1", o=org_id))
    has_policy = bool(_scalar(session, "SELECT 1 FROM approval_policy WHERE org_id = CAST(:o AS uuid) LIMIT 1", o=org_id))
    n_filings = _scalar(session, "SELECT count(*) FROM regulatory_filing WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
    n_contracts = _scalar(session, "SELECT count(*) FROM customer_contract WHERE org_id = CAST(:o AS uuid)", o=org_id) or 0
    identity = bool(org["legal_name"] and org["lei"])

    steps = [
        _step("tenant", "provision", True, False, "/platform", "done", org=org["name"], sector=messages.name("admin.sector", otype)),
        _step("identity", "provision", identity, False, "/admin", "done" if identity else "todo",
              legal_name=org["legal_name"], lei=org["lei"]),
        _step("access", "provision", n_users >= 1, False, "/admin",
              "todo" if n_users == 0 else "alone" if n_users == 1 else "done", n=n_users),
        _step("contracts", "provision", n_contracts > 0, True, "/contracts", "done" if n_contracts else "todo", n=n_contracts),
        _step("book", "load", n_book > 0, False, "/data", book_state if n_book else "todo", n=n_book),
        _step("systems", "load", n_source > 0, True, "/admin", "done" if n_source else "todo", n=n_source),
        _step("engine", "load", has_basis, False, "/admin", "done" if has_basis else "todo"),
        _step("governance", "govern", has_policy, False, "/admin", "done" if has_policy else "todo"),
        _step("scored", "govern", n_scored > 0, False, "/", "done" if n_book else "no_book", scored=n_scored, book=n_book),
        _step("filing", "govern", n_filings > 0, False, "/filings", "done" if n_filings else "todo", n=n_filings),
    ]

    required = [s for s in steps if not s["optional"]]
    done_req = sum(1 for s in required if s["done"])
    n_done = sum(1 for s in steps if s["done"])
    return {
        "available": True, "org_id": org_id, "org_name": org["name"], "org_type": otype,
        "phases": [{"key": k, "label": messages.name("platform.golive_phase", k)} for k in PHASES],
        "steps": steps,
        "required_total": len(required), "required_done": done_req,
        "total": len(steps), "done": n_done,
        "pct": round(100 * done_req / len(required)) if required else 100,
        "live": done_req == len(required),
        "next": next((s for s in steps if not s["optional"] and not s["done"]), None),
    }
