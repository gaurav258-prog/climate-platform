"""Supervision scope — which entities an authority supervises — and the rule that scope respects the profile.

A supervisory body's profile says which sectors it works (supervision_profiles.json). An entity can only be in
scope if its sector is in the profile; anything that slipped in outside it (a profile switch, a legacy row) is
reported as a warning in Settings and never shown as population. Adding or ending supervision is audited on both
sides and the entity is told; the entity acknowledges from its own workspace.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

EXCLUDED_TYPES = ("platform", "regulator")


def profile_types(cfg: dict) -> list[str]:
    return sorted(cfg["sectors"].keys())


def _rows(session, reg_org_id: str, active_only: bool = True) -> list[dict]:
    rows = session.execute(text(f"""
        SELECT ss.supervision_id::text AS supervision_id, o.org_id::text AS org_id, o.name, o.type, o.country, o.lei,
               ss.jurisdiction, ss.created_at, ss.ended_at, ss.acknowledged_at,
               (ss.site_access_granted_at IS NOT NULL AND ss.site_access_revoked_at IS NULL) AS site_access
        FROM supervision_scope ss JOIN organizations o ON o.org_id = ss.supervised_org_id
        WHERE ss.regulator_org_id = CAST(:r AS uuid) {'AND ss.active' if active_only else ''}
        ORDER BY o.name
    """), {"r": reg_org_id}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        for k in ("created_at", "ended_at", "acknowledged_at"):
            d[k] = d[k].isoformat() if d.get(k) else None
        out.append(d)
    return out


def org_scope(session, reg_org_id: str, cfg: dict) -> list[dict]:
    """The population: active scope rows whose sector the profile covers."""
    types = set(profile_types(cfg))
    return [r for r in _rows(session, reg_org_id) if r["type"] in types]


def health(session, reg_org_id: str, cfg: dict) -> dict:
    types = set(profile_types(cfg))
    rows = _rows(session, reg_org_id)
    return {"profile_id": cfg["profile_id"], "profile_label": cfg["label"], "sectors": sorted(types),
            "in_profile": [r for r in rows if r["type"] in types],
            "out_of_profile": [r for r in rows if r["type"] not in types]}


def candidates(session, reg_org_id: str, cfg: dict, q: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Entities on the platform this authority could supervise: in-profile sector, not already in active scope."""
    rows = session.execute(text("""
        SELECT o.org_id::text AS org_id, o.name, o.type, o.country, o.lei
        FROM organizations o
        WHERE o.type = ANY(CAST(:types AS text[])) AND o.type <> ALL(CAST(:excl AS text[]))
          AND NOT EXISTS (SELECT 1 FROM supervision_scope ss WHERE ss.regulator_org_id = CAST(:r AS uuid)
                          AND ss.supervised_org_id = o.org_id AND ss.active)
          AND (CAST(:q AS text) IS NULL OR o.name ILIKE '%' || CAST(:q AS text) || '%' OR o.lei ILIKE '%' || CAST(:q AS text) || '%')
        ORDER BY o.name LIMIT :lim
    """), {"types": profile_types(cfg), "excl": list(EXCLUDED_TYPES), "r": reg_org_id, "q": (q or "").strip() or None, "lim": limit}).mappings().all()
    return [dict(r) for r in rows]


def add(session, reg_org_id: str, supervised_org_id: str, jurisdiction: Optional[str], by_user_id: str, cfg: dict) -> dict:
    org = session.execute(text("SELECT org_id::text AS org_id, name, type FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                          {"o": supervised_org_id}).mappings().first()
    if not org or org["type"] in EXCLUDED_TYPES:
        raise KeyError("no such entity")
    if org["type"] not in profile_types(cfg):
        from services.supervision.profiles import registry
        lab = lambda t: (registry()["sectors"].get(t) or {}).get("label") or t.replace("_", " ")  # noqa: E731
        raise ValueError(f"{org['name']} belongs to {lab(org['type'])}; your profile ({cfg['label']}) covers "
                         f"{', '.join(lab(t) for t in profile_types(cfg))}. Switch to a profile that covers this sector first.")
    sid = session.execute(text("""
        INSERT INTO supervision_scope (regulator_org_id, supervised_org_id, jurisdiction, active, added_by)
        VALUES (CAST(:r AS uuid), CAST(:s AS uuid), :j, TRUE, CAST(:u AS uuid))
        ON CONFLICT (regulator_org_id, supervised_org_id) DO UPDATE
           SET active = TRUE, jurisdiction = COALESCE(EXCLUDED.jurisdiction, supervision_scope.jurisdiction),
               added_by = EXCLUDED.added_by, ended_at = NULL, ended_by = NULL, acknowledged_at = NULL, acknowledged_by = NULL
        RETURNING supervision_id::text
    """), {"r": reg_org_id, "s": supervised_org_id, "j": (jurisdiction or "").strip() or None, "u": by_user_id}).scalar()
    _tell_entity(session, reg_org_id, supervised_org_id, sid, started=True)
    return {"supervision_id": sid, **org}


def end(session, reg_org_id: str, supervision_id: str, by_user_id: str) -> Optional[str]:
    row = session.execute(text("""
        UPDATE supervision_scope SET active = FALSE, ended_at = now(), ended_by = CAST(:u AS uuid)
        WHERE supervision_id = CAST(:s AS uuid) AND regulator_org_id = CAST(:r AS uuid) AND active
        RETURNING supervised_org_id::text
    """), {"u": by_user_id, "s": supervision_id, "r": reg_org_id}).scalar()
    if row:
        # assignments to an entity no longer supervised end with it
        session.execute(text("""UPDATE supervision_assignment SET revoked_at = now(), revoked_by = CAST(:u AS uuid)
                                WHERE regulator_org_id = CAST(:r AS uuid) AND supervised_org_id = CAST(:s AS uuid) AND revoked_at IS NULL"""),
                        {"u": by_user_id, "r": reg_org_id, "s": row})
        _tell_entity(session, reg_org_id, row, supervision_id, started=False)
    return row


def acknowledge(session, supervised_org_id: str, supervision_id: str, by_user_id: str) -> bool:
    res = session.execute(text("""
        UPDATE supervision_scope SET acknowledged_at = now(), acknowledged_by = CAST(:u AS uuid)
        WHERE supervision_id = CAST(:s AS uuid) AND supervised_org_id = CAST(:o AS uuid) AND active AND acknowledged_at IS NULL
    """), {"u": by_user_id, "s": supervision_id, "o": supervised_org_id})
    return bool(res.rowcount)


def _tell_entity(session, reg_org_id: str, supervised_org_id: str, supervision_id: str, started: bool) -> None:
    """E-mail the entity's administrators and emit a webhook event. Never raises."""
    from services.integrations.webhooks import emit_event
    from services.notifications.mailer import queue_email
    try:
        reg = session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": reg_org_id}).scalar()
        admins = session.execute(text("""
            SELECT DISTINCT u.email FROM users u JOIN user_roles ur ON ur.user_id = u.user_id
            JOIN role_permissions rp ON rp.role_id = ur.role_id JOIN permissions p ON p.permission_id = rp.permission_id
            WHERE u.org_id = CAST(:o AS uuid) AND u.status = 'active' AND p.code = 'admin.users.manage'
        """), {"o": supervised_org_id}).scalars().all()
        subject = f"{reg} now supervises your organisation in Tellumen" if started else f"{reg} has ended its supervision in Tellumen"
        body = (f"{reg} has added your organisation to its supervised population. It sees your released filings and regional "
                "aggregates; individual sites only if you grant it. Please acknowledge under Settings → Entities → Supervisory access."
                if started else f"{reg} has ended its supervision of your organisation. It no longer sees your filings or exposure.")
        for em in admins:
            queue_email(session, org_id=supervised_org_id, to_email=em, subject=subject, html=None, text_body=body,
                        kind="supervision_scope", ref_type="supervision_scope", ref_id=supervision_id)
        emit_event(session, supervised_org_id, "supervision.started" if started else "supervision.ended",
                   {"supervision_id": supervision_id, "regulator": reg})
    except Exception:
        pass
