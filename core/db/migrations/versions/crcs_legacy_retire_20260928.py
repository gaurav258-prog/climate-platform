"""Retire the legacy CRCS schema: eleven tables of a first CRCS design that no code path ever used.

The live CRCS runs on reg_source_snapshot / reg_detected_change / reg_alert (EU register, daily) and the version,
impact and readiness services. These tables were created by the bank-vertical migration from the ORM and stayed
empty (regulatory_frameworks held six seed rows only the retired code read). Their ORM classes stay in
core/db/models_regulatory_complete.py solely so that historic migration replays unchanged.

Revision ID: crcs_legacy_retire_20260928
Revises: filing_views_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "crcs_legacy_retire_20260928"
down_revision: Union[str, None] = "filing_views_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY = ("dashboard_notifications", "filing_amendments", "regulatory_alerts", "regulatory_change_details",
          "regulatory_document_snapshots", "org_regulation_version_preference", "regulatory_filings",
          "regulatory_changes", "org_crcs_subscription", "regulation_versions", "regulatory_frameworks")


def upgrade() -> None:
    for t in LEGACY:                      # dependants first
        op.execute(f"DROP TABLE IF EXISTS {t}")


def downgrade() -> None:
    from core.db.models_regulatory_complete import Base
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in reversed(LEGACY)])
