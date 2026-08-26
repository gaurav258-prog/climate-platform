"""P3 growth: self-serve trials, sandbox environments, and billing (plans + subscriptions + invoices).

Adds the plan/trial/environment fields on organizations and the subscription + invoice tables behind
self-serve signup, seat-enforced plans, and (Stripe-gated) billing. Idempotent.

Revision ID: growth_p3_20260826
Revises: enterprise_p2_20260826
"""
from alembic import op

revision = "growth_p3_20260826"
down_revision = "enterprise_p2_20260826"
branch_labels = None
depends_on = None

_DDL = """
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS plan varchar(20) NOT NULL DEFAULT 'trial';
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS trial_ends_at timestamptz;
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS environment varchar(20) NOT NULL DEFAULT 'production';

CREATE TABLE IF NOT EXISTS subscription (
  org_id uuid PRIMARY KEY REFERENCES organizations(org_id) ON DELETE CASCADE,
  plan varchar(20) NOT NULL DEFAULT 'trial',
  seats int NOT NULL DEFAULT 5,
  status varchar(20) NOT NULL DEFAULT 'trialing' CHECK (status IN ('trialing','active','past_due','canceled')),
  billing_mode varchar(20) NOT NULL DEFAULT 'manual',
  current_period_start timestamptz,
  current_period_end timestamptz,
  stripe_customer_id text,
  stripe_subscription_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS invoice (
  invoice_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id uuid NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  number varchar(40) NOT NULL,
  amount_cents int NOT NULL DEFAULT 0,
  currency varchar(3) NOT NULL DEFAULT 'EUR',
  status varchar(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open','paid','void')),
  period_start timestamptz,
  period_end timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  paid_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_invoice_org ON invoice(org_id, created_at DESC);
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS invoice")
    op.execute("DROP TABLE IF EXISTS subscription")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS plan")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS trial_ends_at")
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS environment")
