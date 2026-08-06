"""Provided datapoints (Lane 2) — a value calculated on the customer's or a vendor's side, brought into
Tellumen, reconciled against our own computed value where one exists, and attested through 4-eyes before it
lands in a filing. Provenance (source client/vendor + data_vintage) is preserved; precedence client > vendor.

Revision ID: provided_datapoint_202608
Revises: kri_threshold_esrs_202608
"""
from alembic import op

revision = "provided_datapoint_202608"
down_revision = "kri_threshold_esrs_202608"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE IF NOT EXISTS provided_datapoint (
    provided_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(org_id),
    framework       TEXT NOT NULL,
    datapoint_key   TEXT NOT NULL,               -- a 'provided'-lane key from the datapoint catalog
    value_num       DOUBLE PRECISION,
    value_text      TEXT,
    unit            TEXT,
    source          TEXT NOT NULL CHECK (source IN ('client','vendor')),
    provider_name   TEXT,                          -- e.g. the vendor / carbon-tool name
    data_vintage    DATE,
    period_label    TEXT,
    tellumen_value  DOUBLE PRECISION,              -- our baseline at submit time (NULL = we have no counterpart)
    delta_pct       DOUBLE PRECISION,              -- (provided - baseline) / baseline * 100
    within_tolerance BOOLEAN,
    recon_note      TEXT,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','attested','rejected','superseded')),
    approval_request_id UUID,
    submitted_by    UUID REFERENCES users(user_id),
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_by      UUID REFERENCES users(user_id),
    decided_at      TIMESTAMPTZ
);
-- one live (pending or attested) provided value per (org, framework, datapoint)
CREATE UNIQUE INDEX IF NOT EXISTS ux_provided_live ON provided_datapoint(org_id, framework, datapoint_key)
    WHERE status IN ('pending','attested');
"""

DOWN = "DROP TABLE IF EXISTS provided_datapoint;"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
