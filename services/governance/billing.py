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
from core import messages
from core.config import settings
from core.errors import UserError

# The price book's currency: every plan price and every invoice is in it. Amounts are in its minor units (ISO 4217
# minor_units: cents for EUR) — the screen formats them from the invoice's own currency, never assumes €.
PRICE_CURRENCY = "EUR"

# seat count + monthly price (minor units of PRICE_CURRENCY); entitlements stay sector-driven, plans govern seats + tier
# `self_serve`: a customer may switch to it themselves; Enterprise is agreed with our team, never switched to (E182).
PLANS = {
    "trial":      {"seats": 5,    "price_cents": 0,      "label": "Trial",               "self_serve": True},
    "starter":    {"seats": 10,   "price_cents": 50000,  "label": "Starter",             "self_serve": True},
    "growth":     {"seats": 50,   "price_cents": 250000, "label": "Growth",              "self_serve": True},
    "enterprise": {"seats": 1000, "price_cents": 0,      "label": "Enterprise (custom)", "self_serve": False},
}


class BillingError(UserError):
    """A plan or seat refusal in customer words: a catalogue code with its values (core/errors.py)."""


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
        raise BillingError("admin.users.seat_limit", seats=sub[0])


def get_billing(session: Session, org_id: str) -> dict:
    sub = session.execute(text("SELECT plan, seats, status, billing_mode, current_period_end FROM subscription WHERE org_id = CAST(:o AS uuid)"),
                          {"o": org_id}).mappings().first()
    invoices = session.execute(text("""
        SELECT number, amount_cents, currency, status, created_at FROM invoice
        WHERE org_id = CAST(:o AS uuid) ORDER BY created_at DESC, invoice_id LIMIT 24
    """), {"o": org_id}).mappings().all()
    status = messages.names()["admin.subscription_status"]
    provider = "stripe" if settings.STRIPE_API_KEY else "manual"
    return {
        "subscription": ({**dict(sub), "plan_label": PLANS.get(sub["plan"], {}).get("label"),
                          "status_label": status.get(sub["status"])} if sub else None),
        "seats_used": _active_users(session, org_id),
        "plans": [{"key": k, **v} for k, v in PLANS.items()],
        "price_currency": PRICE_CURRENCY,
        "invoices": [{**dict(i), "status_label": messages.name("admin.invoice_status", i["status"])} for i in invoices],
        "billing_provider": provider,
        "billing_note": messages.render(f"admin.billing.{provider}"),
        "plan_note": None if sub else messages.render("admin.billing.no_plan"),
    }


def change_plan(session: Session, org_id: str, *, plan: str, actor_user_id: str) -> dict:
    if plan not in PLANS:
        raise BillingError("admin.billing.unknown_plan")
    p = PLANS[plan]
    if not p["self_serve"]:
        raise BillingError("admin.billing.agreed", plan=p["label"])
    used = _active_users(session, org_id)
    if used > p["seats"]:
        raise BillingError("admin.billing.too_many_users", plan=p["label"], used=used, seats=p["seats"])
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
        VALUES (CAST(:i AS uuid), CAST(:o AS uuid), :n, :a, :c, 'open', now(), now() + interval '30 days')
    """), {"i": str(uuid.uuid4()), "o": org_id, "n": num, "a": amount_cents, "c": PRICE_CURRENCY})
