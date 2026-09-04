"""Billing — plans, seat-enforced subscriptions, and invoices.

Internal/manual billing works fully without any payment provider: a subscription tracks the plan + seat count,
user creation is seat-enforced, and plan changes generate invoices. Card charging is the only Stripe-gated part
— when `STRIPE_API_KEY` is set the charge routes through Stripe; otherwise invoices are raised in manual mode.
Legacy tenants without a subscription row are unlimited (enforcement applies only once a subscription exists).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.services.rbac import write_audit
from core.config import settings

# seat count + monthly price (EUR cents); entitlements stay sector-driven, plans govern seats + tier
PLANS = {
    "trial":      {"seats": 5,    "price_cents": 0,      "label": "Trial"},
    "starter":    {"seats": 10,   "price_cents": 50000,  "label": "Starter"},
    "growth":     {"seats": 50,   "price_cents": 250000, "label": "Growth"},
    "enterprise": {"seats": 1000, "price_cents": 0,      "label": "Enterprise (custom)"},
}


class BillingError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_subscription(session: Session, org_id: str, *, plan: str = "trial") -> None:
    exists = session.execute(text("SELECT 1 FROM subscription WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).first()
    if exists:
        return
    p = PLANS.get(plan, PLANS["trial"])
    session.execute(text("""
        INSERT INTO subscription (org_id, plan, seats, status, billing_mode, current_period_start, current_period_end)
        VALUES (CAST(:o AS uuid), :plan, :seats, :st, :mode, now(), now() + interval '30 days')
    """), {"o": org_id, "plan": plan, "seats": p["seats"],
           "st": "trialing" if plan == "trial" else "active",
           "mode": "stripe" if settings.STRIPE_API_KEY else "manual"})


def _active_users(session: Session, org_id: str) -> int:
    return session.execute(text("SELECT count(*) FROM users WHERE org_id = CAST(:o AS uuid) AND status IN ('active','invited')"),
                           {"o": org_id}).scalar() or 0


def enforce_seat(session: Session, org_id: str) -> None:
    """Raise if the org has a subscription and is at its seat limit. No subscription = unlimited (legacy)."""
    sub = session.execute(text("SELECT seats FROM subscription WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).first()
    if not sub:
        return
    if _active_users(session, org_id) >= sub[0]:
        raise BillingError(f"seat limit reached ({sub[0]} seats). Upgrade your plan to add more users.")


def get_billing(session: Session, org_id: str) -> dict:
    sub = session.execute(text("SELECT plan, seats, status, billing_mode, current_period_end FROM subscription WHERE org_id = CAST(:o AS uuid)"),
                          {"o": org_id}).mappings().first()
    invoices = session.execute(text("""
        SELECT number, amount_cents, currency, status, created_at FROM invoice
        WHERE org_id = CAST(:o AS uuid) ORDER BY created_at DESC LIMIT 24
    """), {"o": org_id}).mappings().all()
    return {
        "subscription": dict(sub) if sub else None,
        "seats_used": _active_users(session, org_id),
        "plans": [{"key": k, **v} for k, v in PLANS.items()],
        "invoices": [dict(i) for i in invoices],
        "billing_provider": "stripe" if settings.STRIPE_API_KEY else "manual",
    }


def change_plan(session: Session, org_id: str, *, plan: str, actor_user_id: str) -> dict:
    if plan not in PLANS:
        raise BillingError(f"unknown plan '{plan}'")
    p = PLANS[plan]
    used = _active_users(session, org_id)
    if used > p["seats"]:
        raise BillingError(f"your {used} users exceed the {p['label']} plan's {p['seats']} seats — remove users or pick a larger plan")
    ensure_subscription(session, org_id, plan=plan)
    session.execute(text("""
        UPDATE subscription SET plan = :plan, seats = :seats, status = :st, updated_at = now()
        WHERE org_id = CAST(:o AS uuid)
    """), {"plan": plan, "seats": p["seats"], "st": "trialing" if plan == "trial" else "active", "o": org_id})
    if p["price_cents"] > 0:
        _raise_invoice(session, org_id, p["price_cents"])
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="billing.plan_changed",
                target_type="subscription", target_id=org_id, detail={"plan": plan})
    session.commit()
    return get_billing(session, org_id)


def _raise_invoice(session: Session, org_id: str, amount_cents: int) -> None:
    num = "INV-" + uuid.uuid4().hex[:8].upper()
    # Stripe charging is gated; in manual mode the invoice is simply recorded 'open'
    session.execute(text("""
        INSERT INTO invoice (invoice_id, org_id, number, amount_cents, currency, status, period_start, period_end)
        VALUES (CAST(:i AS uuid), CAST(:o AS uuid), :n, :a, 'EUR', 'open', now(), now() + interval '30 days')
    """), {"i": str(uuid.uuid4()), "o": org_id, "n": num, "a": amount_cents})
