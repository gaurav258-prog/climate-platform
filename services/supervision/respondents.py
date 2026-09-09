"""Respondent entities — supervised entities that do not use Tellumen as a workspace, and the channel they use.

A supervisory body adds such an entity to its population and invites a named contact. The contact activates an
account the ordinary way (password, two-factor) and sees only the supervisory portal: acknowledge the supervision,
state the regulatory attributes, submit the templates the mandate requires, answer requests. Everything they do
is audited on both sides and lands in the same tables the supervisor's own intake fills — the supervisor's screens
do not know or care whether a template arrived by upload, portal or API, only the channel label says which.
Sector-agnostic: the template and its fields come from the supervisor's profile for the entity's sector.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import text

from services.governance.tenant_provisioning import role_templates_for


def create_respondent(session, *, regulator_org_id: str, cfg: dict, name: str, org_type: str, country: str, jurisdiction: Optional[str],
                      legal_name: Optional[str], lei: Optional[str], contact_email: str, contact_name: Optional[str], by_user_id: str) -> dict:
    """Organisation (plan 'respondent') + respondent role + scope + invited contact. Refuses a sector outside the profile."""
    from services.supervision.scope import add as add_scope
    if org_type not in cfg["sectors"]:
        raise ValueError(f"{org_type} is outside your profile ({cfg['label']}).")
    if session.execute(text("SELECT 1 FROM organizations WHERE lower(name) = lower(:n)"), {"n": name.strip()}).first():
        raise ValueError("An organisation with this name already exists on the platform — add it to your population instead.")
    org_id = str(uuid.uuid4())
    session.execute(text("""INSERT INTO organizations (org_id, name, type, country, legal_name, lei, plan, created_at, updated_at)
                            VALUES (CAST(:o AS uuid), :n, :t, :c, :ln, :lei, 'respondent', now(), now())"""),
                    {"o": org_id, "n": name.strip(), "t": org_type, "c": country, "ln": legal_name, "lei": lei})
    for role_name, perms in role_templates_for(org_type, plan="respondent").items():
        rid = session.execute(text("INSERT INTO roles (org_id, name, description, is_system) VALUES (CAST(:o AS uuid), :n, :d, true) RETURNING role_id"),
                              {"o": org_id, "n": role_name, "d": "Supervisory portal — respond to your supervisor"}).scalar()
        for code in perms:
            session.execute(text("INSERT INTO role_permissions (role_id, permission_id) SELECT :r, permission_id FROM permissions WHERE code = :c ON CONFLICT DO NOTHING"), {"r": rid, "c": code})
    scope = add_scope(session, regulator_org_id, org_id, jurisdiction, by_user_id, cfg)
    invite = invite_contact(session, regulator_org_id=regulator_org_id, supervised_org_id=org_id, email=contact_email, full_name=contact_name, by_user_id=by_user_id)
    return {"org_id": org_id, "name": name.strip(), "supervision_id": scope["supervision_id"], "invite": invite}


def invite_contact(session, *, regulator_org_id: str, supervised_org_id: str, email: str, full_name: Optional[str], by_user_id: str) -> dict:
    """Invite (or re-invite) a named contact at a supervised entity: an invited user with the respondent role and an activation link."""
    from services.governance.client_onboarding import _issue_activation
    org = session.execute(text("SELECT name, type, plan FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": supervised_org_id}).mappings().first()
    if not org:
        raise KeyError(supervised_org_id)
    email = email.strip().lower()
    existing = session.execute(text("SELECT user_id::text, status FROM users WHERE org_id = CAST(:o AS uuid) AND lower(email) = :e"), {"o": supervised_org_id, "e": email}).mappings().first()
    if existing and existing["status"] == "active":
        raise ValueError("This person already has an active account at the entity.")
    if existing:
        user_id = existing["user_id"]
        session.execute(text("UPDATE users SET full_name = COALESCE(:fn, full_name) WHERE user_id = CAST(:u AS uuid)"), {"fn": full_name, "u": user_id})
    else:
        user_id = str(uuid.uuid4())
        session.execute(text("""INSERT INTO users (user_id, org_id, email, role, full_name, status, created_at)
                                VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :e, 'respondent', :fn, 'invited', now())"""),
                        {"u": user_id, "o": supervised_org_id, "e": email, "fn": full_name})
    role_name = "respondent" if org["plan"] == "respondent" else "admin"
    rid = session.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :n"), {"o": supervised_org_id, "n": role_name}).scalar()
    if rid is None and org["plan"] == "respondent":
        rid = session.execute(text("INSERT INTO roles (org_id, name, description, is_system) VALUES (CAST(:o AS uuid), 'respondent', 'Supervisory portal', true) RETURNING role_id"), {"o": supervised_org_id}).scalar()
        for code in role_templates_for(org["type"], plan="respondent")["respondent"]:
            session.execute(text("INSERT INTO role_permissions (role_id, permission_id) SELECT :r, permission_id FROM permissions WHERE code = :c ON CONFLICT DO NOTHING"), {"r": rid, "c": code})
    if rid is not None:
        session.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (CAST(:u AS uuid), :r) ON CONFLICT DO NOTHING"), {"u": user_id, "r": rid})
    link = _issue_activation(session, org_id=supervised_org_id, user_id=user_id, email=email, full_name=full_name, company=org["name"])
    return {"user_id": user_id, "email": email, "status": "invited", "activation_link_sent": True, "activation_link": link}


def contacts(session, supervised_org_id: str) -> list[dict]:
    rows = session.execute(text("SELECT user_id::text AS user_id, email, full_name, status, last_login_at FROM users WHERE org_id = CAST(:o AS uuid) ORDER BY created_at"),
                           {"o": supervised_org_id}).mappings().all()
    return [dict(r) | {"last_login_at": r["last_login_at"].isoformat() if r["last_login_at"] else None} for r in rows]


# ── the entity's side: what to submit, and submitting it ─────────────────────────────────────────────────────
def submission_spec(session, supervised_org_id: str, supervision_id: str) -> Optional[dict]:
    """The template the supervisor expects from this entity (from the supervisor's profile for the entity's sector)."""
    from services.supervision.profiles import config_for, sector_config
    row = session.execute(text("""SELECT ss.regulator_org_id::text AS reg, o.name AS regulator, e.type FROM supervision_scope ss
                                  JOIN organizations o ON o.org_id = ss.regulator_org_id JOIN organizations e ON e.org_id = ss.supervised_org_id
                                  WHERE ss.supervision_id = CAST(:s AS uuid) AND ss.supervised_org_id = CAST(:o AS uuid) AND ss.active"""),
                          {"s": supervision_id, "o": supervised_org_id}).mappings().first()
    if not row:
        return None
    cfg = config_for(session, row["reg"])
    sec = sector_config(cfg, row["type"])
    if not sec or not sec.get("intake"):
        return {"regulator": row["regulator"], "regulator_org_id": row["reg"], "available": False,
                "reason": f"{row['regulator']} has no template intake configured for your sector yet — respond to its requests on the thread instead."}
    sub = sec["intake"]["submission"]
    return {"regulator": row["regulator"], "regulator_org_id": row["reg"], "available": True, "framework": sub["framework"], "template": sub["template"],
            "label": sub["label"], "fields": sub["cell_fields"], "note": sec["intake"].get("_about")}


def submit_template(session, *, supervised_org_id: str, supervision_id: str, raw: bytes, filename: Optional[str], mapping: dict,
                    period_label: str, basis: dict, user_id: str, channel: str = "entity_portal") -> dict:
    from services.supervision.intake import map_rows, save_submission
    spec = submission_spec(session, supervised_org_id, supervision_id)
    if not spec or not spec.get("available"):
        raise ValueError((spec or {}).get("reason") or "No supervisor found for this submission.")
    rep = map_rows(raw, filename, spec["fields"], mapping)
    if rep["missing_required"] or rep["n_error"]:
        return {"accepted": False, "report": {k: v for k, v in rep.items() if k != "rows"}}
    from services.supervision.lens import cell_key
    cells = {cell_key(r["geography"], r["sector"]): {**r} for r in rep["rows"]}
    res = save_submission(session, regulator_org_id=spec["regulator_org_id"], subject_org_id=supervised_org_id, framework=spec["framework"],
                          template=spec["template"], period_label=period_label, basis=basis or {}, cells=cells, raw=raw, filename=filename,
                          mapping=mapping, user_id=user_id, channel=channel)
    _tell_supervisor(session, spec["regulator_org_id"], supervised_org_id, res, channel)
    return {"accepted": True, "result": res, "regulator": spec["regulator"], "n_valid": rep["n_valid"]}


def _tell_supervisor(session, regulator_org_id: str, supervised_org_id: str, res: dict, channel: str) -> None:
    from services.integrations.webhooks import emit_event
    from services.notifications.mailer import queue_email
    try:
        ent = session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": supervised_org_id}).scalar()
        people = session.execute(text("""SELECT DISTINCT u.email FROM users u
                                         LEFT JOIN supervision_assignment a ON a.user_id = u.user_id AND a.supervised_org_id = CAST(:s AS uuid) AND a.revoked_at IS NULL
                                         LEFT JOIN user_roles ur ON ur.user_id = u.user_id LEFT JOIN roles r ON r.role_id = ur.role_id
                                         WHERE u.org_id = CAST(:r AS uuid) AND u.status = 'active' AND (a.assignment_id IS NOT NULL OR r.name IN ('head', 'data_steward'))"""),
                                 {"s": supervised_org_id, "r": regulator_org_id}).scalars().all()
        for em in people:
            queue_email(session, org_id=regulator_org_id, to_email=em, subject=f"{ent}: {res['template']} {res['period_label']} received via {channel.replace('_', ' ')}",
                        html=None, text_body=f"{ent} has submitted {res['framework']} · {res['template']} for {res['period_label']} ({res['n_cells']} cells) through the supervisory portal. "
                                             "It is on file under the entity's intake; the plausibility band is ready to run.", kind="supervision_submission", ref_type="organization", ref_id=supervised_org_id)
        emit_event(session, regulator_org_id, "supervision.submission.received", {"entity_org_id": supervised_org_id, "entity": ent, **res, "channel": channel})
    except Exception:
        pass
