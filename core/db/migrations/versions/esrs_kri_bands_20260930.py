"""The ESRS KRIs are the statement's own figures, keyed by concept (services.governance.kri_esrs); the platform-default
appetite bands on the retired E1 / nature KRIs (share of sites at risk, plots scored, peak water stress, deforestation,
forest loss, non-compliant plots) grade indicators that no longer exist. They are removed; an ESRS KRI is ungraded
until the organisation sets its own band. An organisation's own bands and their history are its records and stay.

Revision ID: esrs_kri_bands_20260930
Revises: esrs_answer_ids_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "esrs_kri_bands_20260930"
down_revision: Union[str, None] = "esrs_answer_ids_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (framework, kri_key, amber, red, direction) — exactly the defaults removed, restored on downgrade
_DEFAULTS = (
    ("csrd_e1", "coverage", 80, 60, "lower_worse"),
    ("csrd_e1", "pct_at_risk", 15, 30, "higher_worse"),
    ("esrs_pack", "coverage", 80, 60, "lower_worse"),
    ("esrs_pack", "deforestation_free_pct", 99, 95, "lower_worse"),
    ("esrs_pack", "forest_loss_ha", 0.1, 1, "higher_worse"),
    ("esrs_pack", "non_compliant", 1, 3, "higher_worse"),
    ("esrs_pack", "pct_at_risk", 15, 30, "higher_worse"),
    ("esrs_pack", "water_peak", 40, 60, "higher_worse"),
)
_KEYS = ", ".join(f"('{f}', '{k}')" for f, k, *_ in _DEFAULTS)


def upgrade() -> None:
    op.execute(f"DELETE FROM kri_threshold WHERE org_id IS NULL AND (framework, kri_key) IN ({_KEYS})")


def downgrade() -> None:
    rows = ", ".join(f"(NULL::uuid, '{f}', '{k}', {a}, {r}, '{d}')" for f, k, a, r, d in _DEFAULTS)
    op.execute(f"""
        INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction)
        SELECT * FROM (VALUES {rows}) AS v(org_id, framework, kri_key, amber, red, direction)
        WHERE NOT EXISTS (SELECT 1 FROM kri_threshold t WHERE t.org_id IS NULL AND t.framework = v.framework
                          AND t.kri_key = v.kri_key)
    """)
