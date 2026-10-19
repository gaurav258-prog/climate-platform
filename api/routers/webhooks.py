"""Outbound webhook management — an admin registers endpoints, sees deliveries, and sends a test event.

All endpoints here are user-JWT + admin.users.manage (managing a tenant's integrations). The actual event
delivery lives in services/integrations/webhooks.py and fires from real product moments (see the
approval-decide tap in api/routers/approvals.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from core import messages
from core.errors import UserError
from services.integrations import webhooks as wh

router = APIRouter(prefix="/v1/webhooks", tags=["Integration"])


class EndpointCreate(BaseModel):
    url:    str = Field(..., min_length=8, max_length=500)
    name:   str = Field(..., min_length=2, max_length=80)
    events: list[str] = Field(default_factory=list, description="Event types to receive; empty = all.")


def _event_name(event_type: str) -> str:
    """An event's short customer name (names "admin.event"); its long description is the catalogue entry's label."""
    return messages.name("admin.event", event_type)


@router.get("/events", summary="The catalogue of webhook event types")
def events(ctx: dict = Depends(require_permission("admin.users.manage"))):
    return {"events": [{**e, "name": _event_name(e["type"])} for e in wh.KNOWN_EVENTS]}


@router.post("", status_code=201, summary="Register a webhook endpoint (signing secret shown once)")
def create_endpoint(body: EndpointCreate, session: DbSession,
                    ctx: dict = Depends(require_permission("admin.users.manage"))):
    if not (body.url.startswith("https://") or body.url.startswith("http://")):
        raise UserError("admin.integrations.bad_url")
    known = {e["type"] for e in wh.KNOWN_EVENTS}
    if any(e not in known for e in body.events):
        raise UserError("admin.integrations.unknown_events")
    res = wh.create_endpoint(session, ctx["org"]["org_id"], body.url, body.name, body.events, ctx["user"]["id"])
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="webhook.endpoint.create", target_type="webhook_endpoint", target_id=res["endpoint_id"],
                detail={"url": body.url, "events": body.events})
    return res


@router.get("", summary="List your organization's webhook endpoints")
def list_endpoints(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    return [{**e, "event_names": [_event_name(x) for x in e["events"]]} for e in wh.list_endpoints(session, ctx["org"]["org_id"])]


@router.delete("/{endpoint_id}", summary="Revoke a webhook endpoint")
def revoke_endpoint(endpoint_id: str, session: DbSession,
                    ctx: dict = Depends(require_permission("admin.users.manage"))):
    if not wh.revoke_endpoint(session, endpoint_id, ctx["org"]["org_id"]):
        raise UserError("admin.integrations.endpoint_not_found")
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="webhook.endpoint.revoke", target_type="webhook_endpoint", target_id=endpoint_id)
    return {"revoked": True}


@router.post("/{endpoint_id}/test", summary="Send a test event to one endpoint now")
def test_endpoint(endpoint_id: str, session: DbSession,
                  ctx: dict = Depends(require_permission("admin.users.manage"))):
    res = wh.deliver_to_endpoint(session, endpoint_id, ctx["org"]["org_id"], "test.ping",
                                 {"message": "This is a Tellumen webhook test.", "org": ctx["org"]["org_id"]})
    if res is None:
        raise UserError("admin.integrations.endpoint_not_found")
    return res


@router.get("/deliveries", summary="Recent webhook delivery attempts (the ledger)")
def deliveries(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    known = {e["type"] for e in wh.KNOWN_EVENTS}
    return [{**d, "event_name": _event_name(d["event_type"]) if d["event_type"] in known else None}
            for d in wh.list_deliveries(session, ctx["org"]["org_id"])]
