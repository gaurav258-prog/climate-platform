"""SCIM 2.0 provisioning — the IdP pushes users into a tenant (create / update / deactivate).

The enterprise auto-provisioning half of SSO (RFC 7643/7644): Okta / Entra ID call these endpoints with the
tenant's SCIM bearer token to create accounts, update attributes, and deactivate leavers — so the customer's
directory is the source of truth and no per-user activation link is needed. SCIM users are active with no local
password (they authenticate via OIDC). Fully self-contained and testable without a live IdP.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
VALID_ROLES = {"admin", "analyst", "approver", "viewer"}


class ScimError(Exception):
    def __init__(self, status: int, detail: str, scim_type: str | None = None):
        self.status = status
        self.detail = detail
        self.scim_type = scim_type
        super().__init__(detail)

    def body(self) -> dict:
        d = {"schemas": [ERROR_SCHEMA], "status": str(self.status), "detail": self.detail}
        if self.scim_type:
            d["scimType"] = self.scim_type
        return d


def _default_role(session: Session, org_id: str) -> str:
    r = session.execute(text("SELECT default_role FROM tenant_sso_config WHERE org_id = CAST(:o AS uuid)"),
                        {"o": org_id}).scalar()
    return r if r in VALID_ROLES else "viewer"


def _email(payload: dict) -> str | None:
    if payload.get("userName") and "@" in payload["userName"]:
        return payload["userName"].strip().lower()
    for e in payload.get("emails", []) or []:
        if e.get("value"):
            return e["value"].strip().lower()
    return None


def _full_name(payload: dict) -> str | None:
    n = payload.get("name") or {}
    parts = [n.get("givenName"), n.get("familyName")]
    joined = " ".join(p for p in parts if p).strip()
    return joined or payload.get("displayName") or None


def _to_scim(row) -> dict:
    return {
        "schemas": [USER_SCHEMA],
        "id": str(row["user_id"]),
        "externalId": row.get("external_id"),
        "userName": row["email"],
        "name": {"formatted": row.get("full_name") or ""},
        "emails": [{"value": row["email"], "primary": True}],
        "active": row["status"] == "active",
        "meta": {"resourceType": "User", "location": f"/scim/v2/Users/{row['user_id']}"},
    }


def _get_row(session: Session, org_id: str, user_id: str):
    return session.execute(text("""
        SELECT user_id, org_id, email, full_name, status, external_id, auth_provider
        FROM users WHERE org_id = CAST(:o AS uuid) AND user_id = CAST(:u AS uuid)
    """), {"o": org_id, "u": user_id}).mappings().first()


def create_user(session: Session, org_id: str, payload: dict) -> dict:
    email = _email(payload)
    if not email:
        raise ScimError(400, "a userName / email is required", "invalidValue")
    dup = session.execute(text("SELECT user_id FROM users WHERE org_id = CAST(:o AS uuid) AND lower(email) = :e"),
                          {"o": org_id, "e": email}).first()
    if dup:
        raise ScimError(409, "a user with this userName already exists", "uniqueness")
    active = payload.get("active", True)
    user_id = str(uuid.uuid4())
    role = _default_role(session, org_id)
    session.execute(text("""
        INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, auth_provider, external_id, created_at)
        VALUES (CAST(:u AS uuid), CAST(:o AS uuid), :e, :r, :n, NULL, :st, 'sso', :x, now())
    """), {"u": user_id, "o": org_id, "e": email, "r": role, "n": _full_name(payload),
           "st": "active" if active else "disabled", "x": payload.get("externalId")})
    rid = session.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :r"),
                          {"o": org_id, "r": role}).scalar()
    if rid:
        session.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (CAST(:u AS uuid), CAST(:r AS uuid)) ON CONFLICT DO NOTHING"),
                        {"u": user_id, "r": str(rid)})
    session.commit()
    return _to_scim(_get_row(session, org_id, user_id))


def get_user(session: Session, org_id: str, user_id: str) -> dict:
    row = _get_row(session, org_id, user_id)
    if not row:
        raise ScimError(404, "user not found")
    return _to_scim(row)


def list_users(session: Session, org_id: str, *, filter_: str | None = None,
               start_index: int = 1, count: int = 100) -> dict:
    params = {"o": org_id}
    where = "org_id = CAST(:o AS uuid)"
    # SCIM clients probe existence with: filter=userName eq "x"
    if filter_ and " eq " in filter_:
        attr, _, val = filter_.partition(" eq ")
        val = val.strip().strip('"')
        if attr.strip() == "userName":
            where += " AND lower(email) = :e"; params["e"] = val.lower()
        elif attr.strip() == "externalId":
            where += " AND external_id = :x"; params["x"] = val
    rows = session.execute(text(f"""
        SELECT user_id, org_id, email, full_name, status, external_id, auth_provider
        FROM users WHERE {where} ORDER BY created_at
        LIMIT :lim OFFSET :off
    """), {**params, "lim": count, "off": max(0, start_index - 1)}).mappings().all()
    total = session.execute(text(f"SELECT count(*) FROM users WHERE {where}"), params).scalar()
    return {
        "schemas": [LIST_SCHEMA], "totalResults": total, "startIndex": start_index,
        "itemsPerPage": len(rows), "Resources": [_to_scim(r) for r in rows],
    }


def replace_user(session: Session, org_id: str, user_id: str, payload: dict) -> dict:
    row = _get_row(session, org_id, user_id)
    if not row:
        raise ScimError(404, "user not found")
    active = payload.get("active", True)
    session.execute(text("""
        UPDATE users SET full_name = :n, status = :st, external_id = COALESCE(:x, external_id)
        WHERE user_id = CAST(:u AS uuid) AND org_id = CAST(:o AS uuid)
    """), {"n": _full_name(payload), "st": "active" if active else "disabled",
           "x": payload.get("externalId"), "u": user_id, "o": org_id})
    session.commit()
    return _to_scim(_get_row(session, org_id, user_id))


def patch_user(session: Session, org_id: str, user_id: str, payload: dict) -> dict:
    """SCIM PATCH — the operation IdPs use to deactivate a leaver: {Operations:[{op:replace,path:active,value:false}]}."""
    row = _get_row(session, org_id, user_id)
    if not row:
        raise ScimError(404, "user not found")
    for op in payload.get("Operations", []):
        action = (op.get("op") or "").lower()
        path = op.get("path")
        value = op.get("value")
        if action not in ("replace", "add"):
            continue
        # value can be a scalar (with path) or a dict of attrs (no path)
        attrs = value if isinstance(value, dict) else ({path: value} if path else {})
        if "active" in attrs:
            active = attrs["active"] in (True, "true", "True")
            session.execute(text("UPDATE users SET status = :st WHERE user_id = CAST(:u AS uuid) AND org_id = CAST(:o AS uuid)"),
                            {"st": "active" if active else "disabled", "u": user_id, "o": org_id})
        name = _full_name(attrs) if ("name" in attrs or "displayName" in attrs) else None
        if name:
            session.execute(text("UPDATE users SET full_name = :n WHERE user_id = CAST(:u AS uuid) AND org_id = CAST(:o AS uuid)"),
                            {"n": name, "u": user_id, "o": org_id})
    session.commit()
    return _to_scim(_get_row(session, org_id, user_id))


def deactivate_user(session: Session, org_id: str, user_id: str) -> None:
    """SCIM DELETE — deprovision by disabling (soft), preserving the audit trail."""
    row = _get_row(session, org_id, user_id)
    if not row:
        raise ScimError(404, "user not found")
    session.execute(text("UPDATE users SET status = 'disabled' WHERE user_id = CAST(:u AS uuid) AND org_id = CAST(:o AS uuid)"),
                    {"u": user_id, "o": org_id})
    session.commit()


# ── SCIM Groups (mapped to roles) ────────────────────────────────────────────
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"


def _role_for(session: Session, org_id: str, display_name: str) -> str | None:
    """Map a directory group to a Tellumen role by matching its display name to a role name."""
    dn = (display_name or "").strip().lower()
    r = session.execute(text("SELECT name FROM roles WHERE org_id = CAST(:o AS uuid) AND lower(name) = :n"),
                        {"o": org_id, "n": dn}).scalar()
    return r if r in VALID_ROLES else None


def _grant(session: Session, org_id: str, user_id: str, role: str) -> None:
    rid = session.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :r"),
                          {"o": org_id, "r": role}).scalar()
    if rid:
        session.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (CAST(:u AS uuid), CAST(:r AS uuid)) ON CONFLICT DO NOTHING"),
                        {"u": user_id, "r": str(rid)})


def _revoke(session: Session, org_id: str, user_id: str, role: str) -> None:
    rid = session.execute(text("SELECT role_id FROM roles WHERE org_id = CAST(:o AS uuid) AND name = :r"),
                          {"o": org_id, "r": role}).scalar()
    if rid:
        session.execute(text("DELETE FROM user_roles WHERE user_id = CAST(:u AS uuid) AND role_id = CAST(:r AS uuid)"),
                        {"u": user_id, "r": str(rid)})


def _group_repr(session: Session, org_id: str, gid: str) -> dict:
    g = session.execute(text("SELECT group_id, display_name, external_id, mapped_role FROM scim_group WHERE group_id = CAST(:g AS uuid)"),
                        {"g": gid}).mappings().first()
    members = session.execute(text("SELECT user_id FROM scim_group_member WHERE group_id = CAST(:g AS uuid)"),
                             {"g": gid}).scalars().all()
    return {"schemas": [GROUP_SCHEMA], "id": str(g["group_id"]), "displayName": g["display_name"],
            "externalId": g["external_id"], "mappedRole": g["mapped_role"],
            "members": [{"value": str(m)} for m in members],
            "meta": {"resourceType": "Group", "location": f"/scim/v2/Groups/{g['group_id']}"}}


def create_group(session: Session, org_id: str, payload: dict) -> dict:
    import uuid as _uuid
    name = (payload.get("displayName") or "").strip()
    if not name:
        raise ScimError(400, "displayName is required", "invalidValue")
    dup = session.execute(text("SELECT group_id FROM scim_group WHERE org_id = CAST(:o AS uuid) AND lower(display_name) = lower(:n)"),
                          {"o": org_id, "n": name}).first()
    if dup:
        raise ScimError(409, "a group with this displayName already exists", "uniqueness")
    gid = str(_uuid.uuid4())
    role = _role_for(session, org_id, name)
    session.execute(text("""
        INSERT INTO scim_group (group_id, org_id, external_id, display_name, mapped_role)
        VALUES (CAST(:g AS uuid), CAST(:o AS uuid), :x, :n, :r)
    """), {"g": gid, "o": org_id, "x": payload.get("externalId"), "n": name, "r": role})
    for m in payload.get("members", []) or []:
        uid = m.get("value")
        if uid:
            session.execute(text("INSERT INTO scim_group_member (group_id, user_id) VALUES (CAST(:g AS uuid), CAST(:u AS uuid)) ON CONFLICT DO NOTHING"),
                            {"g": gid, "u": uid})
            if role:
                _grant(session, org_id, uid, role)
    session.commit()
    return _group_repr(session, org_id, gid)


def get_group(session: Session, org_id: str, gid: str) -> dict:
    g = session.execute(text("SELECT 1 FROM scim_group WHERE group_id = CAST(:g AS uuid) AND org_id = CAST(:o AS uuid)"),
                        {"g": gid, "o": org_id}).first()
    if not g:
        raise ScimError(404, "group not found")
    return _group_repr(session, org_id, gid)


def list_groups(session: Session, org_id: str) -> dict:
    ids = session.execute(text("SELECT group_id FROM scim_group WHERE org_id = CAST(:o AS uuid) ORDER BY created_at"),
                         {"o": org_id}).scalars().all()
    res = [_group_repr(session, org_id, str(g)) for g in ids]
    return {"schemas": [LIST_SCHEMA], "totalResults": len(res), "startIndex": 1, "itemsPerPage": len(res), "Resources": res}


def patch_group(session: Session, org_id: str, gid: str, payload: dict) -> dict:
    g = session.execute(text("SELECT mapped_role FROM scim_group WHERE group_id = CAST(:g AS uuid) AND org_id = CAST(:o AS uuid)"),
                        {"g": gid, "o": org_id}).mappings().first()
    if not g:
        raise ScimError(404, "group not found")
    role = g["mapped_role"]
    for op in payload.get("Operations", []):
        action = (op.get("op") or "").lower()
        path = (op.get("path") or "")
        value = op.get("value")
        if path == "members" or (isinstance(value, dict) and "members" in value):
            members = value if isinstance(value, list) else (value.get("members") if isinstance(value, dict) else [])
            for m in members or []:
                uid = m.get("value") if isinstance(m, dict) else m
                if not uid:
                    continue
                if action == "remove":
                    session.execute(text("DELETE FROM scim_group_member WHERE group_id = CAST(:g AS uuid) AND user_id = CAST(:u AS uuid)"),
                                    {"g": gid, "u": uid})
                    if role:
                        _revoke(session, org_id, uid, role)
                else:
                    session.execute(text("INSERT INTO scim_group_member (group_id, user_id) VALUES (CAST(:g AS uuid), CAST(:u AS uuid)) ON CONFLICT DO NOTHING"),
                                    {"g": gid, "u": uid})
                    if role:
                        _grant(session, org_id, uid, role)
    session.commit()
    return _group_repr(session, org_id, gid)


def delete_group(session: Session, org_id: str, gid: str) -> None:
    g = session.execute(text("SELECT 1 FROM scim_group WHERE group_id = CAST(:g AS uuid) AND org_id = CAST(:o AS uuid)"),
                        {"g": gid, "o": org_id}).first()
    if not g:
        raise ScimError(404, "group not found")
    session.execute(text("DELETE FROM scim_group WHERE group_id = CAST(:g AS uuid)"), {"g": gid})
    session.commit()
