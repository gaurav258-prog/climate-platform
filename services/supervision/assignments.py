"""Per-person visibility inside a supervisory organisation.

supervision_scope answers "what may this ORGANISATION see". This module answers "what does this PERSON see":
  • each role template in supervision_profiles.json carries a `scope` — 'assigned' (works a case list) or
    'population' (horizontal: everything the organisation supervises);
  • a person's effective scope is the widest scope among their roles;
  • a person on 'assigned' scope sees exactly the entities in supervision_assignment for them (active rows).
Nothing here names a sector or a role in code: both come from the registry and the database.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from services.supervision.profiles import role_templates

ASSIGNED, POPULATION = "assigned", "population"


def role_scope(role_name: str) -> str:
    """Scope of one role template; unknown / custom roles default to the narrow scope."""
    return (role_templates().get(role_name) or {}).get("scope", ASSIGNED)


def effective_scope(roles: list[str]) -> str:
    """Widest scope among a person's roles. No supervisory role at all → narrow scope (assignments only)."""
    return POPULATION if any(role_scope(r) == POPULATION for r in roles or []) else ASSIGNED


def assigned_entity_ids(session, reg_org_id: str, user_id: str) -> set[str]:
    rows = session.execute(text("""
        SELECT supervised_org_id::text FROM supervision_assignment
        WHERE regulator_org_id = CAST(:r AS uuid) AND user_id = CAST(:u AS uuid) AND revoked_at IS NULL
    """), {"r": reg_org_id, "u": user_id}).scalars().all()
    return set(rows)


def visible_entity_ids(session, ctx: dict, in_scope_ids: list[str]) -> list[str]:
    """Filter the organisation's scope down to what this person sees. Order is preserved."""
    if effective_scope(ctx.get("roles") or []) == POPULATION:
        return list(in_scope_ids)
    mine = assigned_entity_ids(session, ctx["org"]["org_id"], ctx["user"]["id"])
    return [i for i in in_scope_ids if i in mine]


def visibility(session, ctx: dict) -> dict:
    """What the UI tells the person about their view."""
    scope = effective_scope(ctx.get("roles") or [])
    n = len(assigned_entity_ids(session, ctx["org"]["org_id"], ctx["user"]["id"])) if scope == ASSIGNED else None
    return {"scope": scope, "assigned": n}


def list_assignments(session, reg_org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT a.assignment_id::text AS assignment_id, a.supervised_org_id::text AS supervised_org_id,
               a.user_id::text AS user_id, u.full_name, u.email, a.capacity, a.assigned_at
        FROM supervision_assignment a JOIN users u ON u.user_id = a.user_id
        WHERE a.regulator_org_id = CAST(:r AS uuid) AND a.revoked_at IS NULL
        ORDER BY a.supervised_org_id, a.capacity, u.full_name
    """), {"r": reg_org_id}).mappings().all()
    return [dict(r) for r in rows]


def team(session, reg_org_id: str) -> list[dict]:
    """People in the supervisory organisation with their roles and the scope those roles give them."""
    rows = session.execute(text("""
        SELECT u.user_id::text AS user_id, u.full_name, u.email, u.status,
               COALESCE(array_agg(r.name ORDER BY r.name) FILTER (WHERE r.name IS NOT NULL), '{}') AS roles
        FROM users u
        LEFT JOIN user_roles ur ON ur.user_id = u.user_id
        LEFT JOIN roles r ON r.role_id = ur.role_id
        WHERE u.org_id = CAST(:r AS uuid)
        GROUP BY u.user_id, u.full_name, u.email, u.status
        ORDER BY u.full_name
    """), {"r": reg_org_id}).mappings().all()
    return [{**dict(r), "roles": list(r["roles"]), "scope": effective_scope(list(r["roles"]))} for r in rows]


def assign(session, reg_org_id: str, supervised_org_id: str, user_id: str, by_user_id: str,
           capacity: str = "lead") -> Optional[str]:
    """Idempotent: returns the active assignment id (existing or new). The user must belong to the regulator."""
    ok = session.execute(text("SELECT 1 FROM users WHERE user_id = CAST(:u AS uuid) AND org_id = CAST(:r AS uuid)"),
                         {"u": user_id, "r": reg_org_id}).first()
    if not ok:
        return None
    existing = session.execute(text("""
        SELECT assignment_id::text FROM supervision_assignment
        WHERE regulator_org_id = CAST(:r AS uuid) AND supervised_org_id = CAST(:s AS uuid)
          AND user_id = CAST(:u AS uuid) AND revoked_at IS NULL
    """), {"r": reg_org_id, "s": supervised_org_id, "u": user_id}).scalar()
    if existing:
        session.execute(text("UPDATE supervision_assignment SET capacity = :c WHERE assignment_id = CAST(:a AS uuid)"),
                        {"c": capacity, "a": existing})
        return existing
    return session.execute(text("""
        INSERT INTO supervision_assignment (regulator_org_id, supervised_org_id, user_id, capacity, assigned_by)
        VALUES (CAST(:r AS uuid), CAST(:s AS uuid), CAST(:u AS uuid), :c, CAST(:b AS uuid))
        RETURNING assignment_id::text
    """), {"r": reg_org_id, "s": supervised_org_id, "u": user_id, "c": capacity, "b": by_user_id}).scalar()


def revoke(session, reg_org_id: str, assignment_id: str, by_user_id: str) -> bool:
    res = session.execute(text("""
        UPDATE supervision_assignment SET revoked_at = now(), revoked_by = CAST(:b AS uuid)
        WHERE assignment_id = CAST(:a AS uuid) AND regulator_org_id = CAST(:r AS uuid) AND revoked_at IS NULL
    """), {"a": assignment_id, "r": reg_org_id, "b": by_user_id})
    return bool(res.rowcount)
