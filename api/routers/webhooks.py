"""Outbound webhook management — an admin registers endpoints, sees deliveries, and sends a test event.

All endpoints here are user-JWT + admin.users.manage (managing a tenant's integrations). The actual event
delivery lives in services/integrations/webhooks.py and fires from real product moments (see the
approval-decide tap in api/routers/approvals.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from services.integrations import webhooks as wh

router = APIRouter(prefix="/v1/webhooks", tags=["Integration"])


class EndpointCreate(BaseModel):
    url:    str = Field(..., min_length=8, max_length=500)
    name:   str = Field(..., min_length=2, max_length=80)
    events: list[str] = Field(default_factory=list, description="Event types to receive; empty = all.")

    @field_validator("url")
    @classmethod
    def _http(cls, v: str) -> str:
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("url must start with http:// or https://")
        return v


@router.get("/events", summary="The catalogue of webhook event types")
def events(ctx: dict = Depends(require_permission("admin.users.manage"))):
    return {"events": wh.KNOWN_EVENTS}


@router.post("", status_code=201, summary="Register a webhook endpoint (signing secret shown once)")
def create_endpoint(body: EndpointCreate, session: DbSession,
                    ctx: dict = Depends(require_permission("admin.users.manage"))):
    known = {e["type"] for e in wh.KNOWN_EVENTS}
    bad = [e for e in body.events if e not in known]
    if bad:
        raise HTTPException(422, {"error": "unknown_events", "message": f"Unknown event type(s): {bad}"})
    res = wh.create_endpoint(session, ctx["org"]["org_id"], body.url, body.name, body.events, ctx["user"]["id"])
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="webhook.endpoint.create", target_type="webhook_endpoint", target_id=res["endpoint_id"],
                detail={"url": body.url, "events": body.events})
    return res


@router.get("", summary="List your organization's webhook endpoints")
def list_endpoints(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    return wh.list_endpoints(session, ctx["org"]["org_id"])


@router.delete("/{endpoint_id}", summary="Revoke a webhook endpoint")
def revoke_endpoint(endpoint_id: str, session: DbSession,
                    ctx: dict = Depends(require_permission("admin.users.manage"))):
    if not wh.revoke_endpoint(session, endpoint_id, ctx["org"]["org_id"]):
        raise HTTPException(404, {"error": "not_found", "message": "Endpoint not found or already revoked."})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="webhook.endpoint.revoke", target_type="webhook_endpoint", target_id=endpoint_id)
    return {"revoked": True}


@router.post("/{endpoint_id}/test", summary="Send a test event to one endpoint now")
def test_endpoint(endpoint_id: str, session: DbSession,
                  ctx: dict = Depends(require_permission("admin.users.manage"))):
    res = wh.deliver_to_endpoint(session, endpoint_id, ctx["org"]["org_id"], "test.ping",
                                 {"message": "This is a Tellumen webhook test.", "org": ctx["org"]["org_id"]})
    if res is None:
        raise HTTPException(404, {"error": "not_found", "message": "Endpoint not found or inactive."})
    return res


@router.get("/deliveries", summary="Recent webhook delivery attempts (the ledger)")
def deliveries(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    return wh.list_deliveries(session, ctx["org"]["org_id"])
