"""Outbound webhooks — forward Tellumen events to a customer's registered endpoints.

One event bus: `emit_event(session, org_id, event_type, payload)` finds the org's active subscriptions for
that event and delivers a signed JSON POST to each, recording every attempt in the ledger. Real emits fire
in a background thread so they never block (or fail) the request that produced them; a manual test delivers
inline so the admin sees the result immediately.

Signing: header `X-Tellumen-Signature: sha256=<hmac>` over the exact request body, using the endpoint's
secret — so the receiver can verify the payload really came from us and wasn't tampered with.

Honesty / scope: HTTP push is the in-house mode and ships live. Auto-retry with backoff is a worker job
(a failed delivery can be resent manually today; the sweep runs when the Celery worker is enabled). SFTP
push needs a destination server and is interface-ready, not live. Storing the secret in plaintext is a
known hardening item (encrypt-at-rest); it is admin-gated and per-tenant.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.db.session import get_session

logger = logging.getLogger(__name__)

SECRET_PREFIX = "whsec_"
_TIMEOUT = 6  # seconds — a receiver must ack quickly; a slow endpoint is a failed delivery, not a hang.

# The documented event catalogue the UI offers. Kept small and tied to real moments in the product.
KNOWN_EVENTS = [
    {"type": "approval.decided",       "label": "A governed change was approved or rejected (publish / release / apply)"},
    {"type": "filing.frozen",          "label": "A disclosure was frozen to an immutable snapshot"},
    {"type": "risk.decision.approved", "label": "A forward-risk decision was approved (reprice / engage / disclose / …)"},
    {"type": "test.ping",              "label": "A manual test event"},
]


def generate_secret() -> str:
    return SECRET_PREFIX + os.urandom(24).hex()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── endpoint CRUD ───────────────────────────────────────────────────────

def create_endpoint(session: Session, org_id: str, url: str, name: str,
                    events: list[str], created_by_user_id: str) -> dict:
    secret = generate_secret()
    endpoint_id = uuid.uuid4()
    session.execute(text("""
        INSERT INTO webhook_endpoints (endpoint_id, org_id, created_by_user_id, name, url, secret, events)
        VALUES (:e, :o, :u, :n, :url, :s, :ev)
    """), {"e": str(endpoint_id), "o": org_id, "u": created_by_user_id, "n": name,
           "url": url, "s": secret, "ev": events or []})
    return {"endpoint_id": str(endpoint_id), "name": name, "url": url, "secret": secret, "events": events or []}


def list_endpoints(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT we.endpoint_id, we.name, we.url, we.events, we.is_active, we.created_at, we.last_delivery_at,
               u.email AS created_by_email
        FROM   webhook_endpoints we LEFT JOIN users u ON u.user_id = we.created_by_user_id
        WHERE  we.org_id = :o ORDER BY we.created_at DESC
    """), {"o": org_id}).mappings().all()
    return [{
        "endpoint_id": str(r["endpoint_id"]), "name": r["name"], "url": r["url"], "events": list(r["events"] or []),
        "is_active": r["is_active"], "created_by_email": r["created_by_email"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "last_delivery_at": r["last_delivery_at"].isoformat() if r["last_delivery_at"] else None,
    } for r in rows]


def revoke_endpoint(session: Session, endpoint_id: str, org_id: str) -> bool:
    res = session.execute(text("""
        UPDATE webhook_endpoints SET is_active = false
        WHERE endpoint_id = :e AND org_id = :o AND is_active = true
    """), {"e": endpoint_id, "o": org_id})
    return res.rowcount > 0


# ── delivery ────────────────────────────────────────────────────────────

def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def deliver_one(url: str, secret: str, event_type: str, payload: dict) -> dict:
    """POST a signed JSON envelope to `url`. Pure HTTP — never raises; returns a result dict."""
    body = json.dumps({"event": event_type, "data": payload, "sent_at": _now_iso()}, default=str).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Tellumen-Webhooks/1.0",
        "X-Tellumen-Event": event_type,
        "X-Tellumen-Signature": _sign(secret, body),
    }
    try:
        r = requests.post(url, data=body, headers=headers, timeout=_TIMEOUT)
        ok = 200 <= r.status_code < 300
        return {"status": "delivered" if ok else "failed", "http_status": r.status_code,
                "error": None if ok else f"endpoint returned HTTP {r.status_code}"}
    except requests.RequestException as exc:
        return {"status": "failed", "http_status": None, "error": str(exc)[:300]}


def record_delivery(session: Session, org_id: str, endpoint_id: str, event_type: str,
                    payload: dict, result: dict, attempts: int = 1) -> None:
    session.execute(text("""
        INSERT INTO webhook_deliveries (org_id, endpoint_id, event_type, payload, status, http_status, error, attempts)
        VALUES (:o, :e, :et, CAST(:p AS jsonb), :s, :h, :err, :a)
    """), {"o": org_id, "e": endpoint_id, "et": event_type, "p": json.dumps(payload, default=str),
           "s": result["status"], "h": result["http_status"], "err": result["error"], "a": attempts})
    session.execute(text("UPDATE webhook_endpoints SET last_delivery_at = now() WHERE endpoint_id = :e"),
                    {"e": endpoint_id})


def emit_event(session: Session, org_id: str, event_type: str, payload: dict, inline: bool = False) -> dict:
    """Deliver `event_type` to every active endpoint of `org_id` subscribed to it (empty filter = all).
    inline=False (default) hands delivery to a daemon thread so the caller never blocks or fails on a slow
    receiver. inline=True delivers now and returns per-endpoint results (used by the manual test)."""
    eps = session.execute(text("""
        SELECT endpoint_id, url, secret, events FROM webhook_endpoints
        WHERE org_id = :o AND is_active = true
    """), {"o": org_id}).mappings().all()
    targets = [{"endpoint_id": str(e["endpoint_id"]), "url": e["url"], "secret": e["secret"]}
               for e in eps if (not e["events"]) or (event_type in e["events"])]
    if not targets:
        return {"delivered": 0, "queued": 0}

    if inline:
        results = []
        for t in targets:
            res = deliver_one(t["url"], t["secret"], event_type, payload)
            record_delivery(session, org_id, t["endpoint_id"], event_type, payload, res)
            results.append({"url": t["url"], **res})
        return {"delivered": sum(1 for r in results if r["status"] == "delivered"), "results": results}

    def _run():
        try:
            with get_session() as s:
                for t in targets:
                    res = deliver_one(t["url"], t["secret"], event_type, payload)
                    record_delivery(s, org_id, t["endpoint_id"], event_type, payload, res)
        except Exception:  # a background delivery must never surface anywhere
            logger.exception("webhook delivery thread failed for org %s event %s", org_id, event_type)

    threading.Thread(target=_run, daemon=True).start()
    return {"queued": len(targets), "delivered": 0}


def deliver_to_endpoint(session: Session, endpoint_id: str, org_id: str, event_type: str, payload: dict) -> Optional[dict]:
    """Deliver one event to a SINGLE named endpoint now (the manual 'send test'). Returns the result, or
    None if the endpoint isn't found / not active in this org."""
    e = session.execute(text("""
        SELECT url, secret FROM webhook_endpoints WHERE endpoint_id = :e AND org_id = :o AND is_active = true
    """), {"e": endpoint_id, "o": org_id}).mappings().first()
    if not e:
        return None
    res = deliver_one(e["url"], e["secret"], event_type, payload)
    record_delivery(session, org_id, endpoint_id, event_type, payload, res)
    return {"url": e["url"], **res}


def list_deliveries(session: Session, org_id: str, limit: int = 50) -> list[dict]:
    rows = session.execute(text("""
        SELECT d.delivery_id, d.event_type, d.status, d.http_status, d.error, d.attempts, d.created_at,
               we.name AS endpoint_name, we.url AS endpoint_url
        FROM   webhook_deliveries d LEFT JOIN webhook_endpoints we ON we.endpoint_id = d.endpoint_id
        WHERE  d.org_id = :o ORDER BY d.created_at DESC LIMIT :lim
    """), {"o": org_id, "lim": limit}).mappings().all()
    return [{
        "delivery_id": str(r["delivery_id"]), "event_type": r["event_type"], "status": r["status"],
        "http_status": r["http_status"], "error": r["error"], "attempts": r["attempts"],
        "endpoint_name": r["endpoint_name"], "endpoint_url": r["endpoint_url"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in rows]
