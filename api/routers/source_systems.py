"""External drill-through — register a customer's systems of record and resolve a Tellumen entity to the
deep-link that opens the source record in that system.

Phase 1 is DEEP-LINK only: Tellumen stores the link template + the source record id, never the source data;
the external system renders the record under its own authentication and access controls. Every resolve is
audited (who drilled to which source record, when). Phase 2 — read-through data-pull rendered inside Tellumen
— additionally requires identity federation (SSO/OAuth token exchange) and is deliberately not built here.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator
from sqlalchemy import text

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/source-systems", tags=["Drill-through"])

_KINDS = {"gl", "core_banking", "los", "warehouse", "gis", "other"}


class SystemIn(BaseModel):
    key: str
    name: str
    kind: str = "other"
    deep_link_template: str

    @field_validator("deep_link_template")
    @classmethod
    def _tmpl(cls, v: str) -> str:
        if "{id}" not in v:
            raise ValueError("deep_link_template must contain the '{id}' placeholder for the source record id")
        if not v.startswith("https://"):
            raise ValueError("deep_link_template must be an https:// URL")
        return v

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        return v if v in _KINDS else "other"


class LinkIn(BaseModel):
    entity_id: str
    source_system_key: str
    source_record_id: str


@router.get("", summary="Registered external systems of record for this org")
def list_systems(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    org_id = ctx["org"]["org_id"]
    rows = session.execute(text("""
        SELECT key, name, kind, deep_link_template, active, created_at
        FROM source_systems WHERE org_id = CAST(:o AS uuid) ORDER BY name
    """), {"o": org_id}).mappings().all()
    return {"systems": [dict(r) for r in rows],
            "can_configure": "admin.approval_policy.manage" in ctx["permissions"]}


@router.post("", summary="Register / update an external system of record (admin)")
def register_system(body: SystemIn, session: DbSession,
                    ctx: dict = Depends(require_permission("admin.approval_policy.manage"))):
    org_id = ctx["org"]["org_id"]
    session.execute(text("""
        INSERT INTO source_systems (source_system_id, org_id, key, name, kind, deep_link_template, active, created_by, created_at)
        VALUES (:id, CAST(:o AS uuid), :k, :n, :kind, :tmpl, TRUE, :by, now())
        ON CONFLICT (org_id, key) DO UPDATE SET name = EXCLUDED.name, kind = EXCLUDED.kind,
            deep_link_template = EXCLUDED.deep_link_template, active = TRUE
    """), {"id": uuid.uuid4(), "o": org_id, "k": body.key, "n": body.name, "kind": body.kind,
           "tmpl": body.deep_link_template, "by": ctx["user"]["id"]})
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="source_system.register",
                target_type="source_system", target_id=body.key,
                detail={"name": body.name, "kind": body.kind})
    session.commit()
    return {"ok": True, "key": body.key}


@router.post("/link", summary="Link a Tellumen entity to its record id in a source system (admin)")
def link_entity(body: LinkIn, session: DbSession,
                ctx: dict = Depends(require_permission("admin.approval_policy.manage"))):
    org_id = ctx["org"]["org_id"]
    sys_ok = session.execute(text("SELECT 1 FROM source_systems WHERE org_id = CAST(:o AS uuid) AND key = :k"),
                             {"o": org_id, "k": body.source_system_key}).first()
    if not sys_ok:
        return {"ok": False, "reason": "unknown_source_system"}
    session.execute(text("""
        INSERT INTO entity_source_refs (ref_id, org_id, entity_id, source_system_key, source_record_id, created_at)
        VALUES (:id, CAST(:o AS uuid), CAST(:e AS uuid), :k, :rid, now())
        ON CONFLICT (org_id, entity_id, source_system_key) DO UPDATE SET source_record_id = EXCLUDED.source_record_id
    """), {"id": uuid.uuid4(), "o": org_id, "e": body.entity_id, "k": body.source_system_key,
           "rid": body.source_record_id})
    session.commit()
    return {"ok": True}


@router.get("/drill-through/{entity_id}", summary="Resolve an entity to its source-system deep links (audited)")
def drill_through(entity_id: str, session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    """Return the deep link(s) that open this entity's record in the customer's source system(s). Honest empty
    state: if no system is registered or the entity is not linked, says so (and whether an admin can set it up).
    Every successful resolve is written to the access audit log."""
    org_id = ctx["org"]["org_id"]
    rows = session.execute(text("""
        SELECT r.source_record_id, s.key, s.name, s.kind, s.deep_link_template
        FROM entity_source_refs r
        JOIN source_systems s ON s.org_id = r.org_id AND s.key = r.source_system_key AND s.active
        WHERE r.org_id = CAST(:o AS uuid) AND r.entity_id = CAST(:e AS uuid)
    """), {"o": org_id, "e": entity_id}).mappings().all()

    n_systems = session.execute(text("SELECT count(*) FROM source_systems WHERE org_id = CAST(:o AS uuid) AND active"),
                                {"o": org_id}).scalar()
    can_configure = "admin.approval_policy.manage" in ctx["permissions"]
    if not rows:
        reason = ("no_source_system" if not n_systems else "entity_not_linked")
        return {"available": False, "reason": reason, "n_systems_registered": n_systems,
                "can_configure": can_configure}

    links = [{"system": r["name"], "kind": r["kind"],
              "url": r["deep_link_template"].replace("{id}", r["source_record_id"])} for r in rows]
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="drill_through.resolve",
                target_type="entity", target_id=entity_id,
                detail={"systems": [r["key"] for r in rows]})
    session.commit()
    return {"available": True, "links": links}
