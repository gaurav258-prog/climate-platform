"""insurer_incurred_losses gains region + modelled -- SASB FN-IN-450a.2 disaggregation (via IFRS S2 para 29)

Found by a systematic EIOPA/ISSB Q&A + guidance sweep (not a fetch-access gap): IFRS S2 para 29's
industry-based guidance for insurers points to SASB FN-IN-450a.2, which requires monetary losses from
insurance claims disaggregated by (a) modelled vs non-modelled catastrophes, (b) event type (peril, already
carried as `peril`), and (c) geographic segment, both gross and net of reinsurance (already carried as
gross/net_incurred_loss_eur). Two of the four required disaggregation axes -- geography and the
modelled/non-modelled flag -- were missing from the table built this session. Both are optional and
customer-supplied, same honesty discipline as every other field here (never inferred/fabricated when absent).

Revision ID: ifrs_incurred_region_20260922
Revises: bank_no_stated_maturity_20260922
"""
import sqlalchemy as sa
from alembic import op

revision = "ifrs_incurred_region_20260922"
down_revision = "bank_no_stated_maturity_20260922"
branch_labels = None
depends_on = None

UPGRADE = """
ALTER TABLE insurer_incurred_losses ADD COLUMN IF NOT EXISTS region VARCHAR(60);
ALTER TABLE insurer_incurred_losses ADD COLUMN IF NOT EXISTS modelled BOOLEAN;
"""
DOWNGRADE = """
ALTER TABLE insurer_incurred_losses DROP COLUMN IF EXISTS region;
ALTER TABLE insurer_incurred_losses DROP COLUMN IF EXISTS modelled;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
