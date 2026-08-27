"""Standardized decision layer — free the action vocabulary from a hardcoded DB CHECK.

The decision engine now carries per-sector verb-packs (reprice/limit_exit for a bank, non_renew for an insurer,
reallocate_origin for agri, …) validated in code against the sector registry (ALL_ACTIONS). The old
5-value CHECK constraints on risk_decision.action and decision_playbook.action would reject every new verb, so
they are dropped — the application is the authority on the vocabulary, which now evolves without a migration.
Idempotent.

Revision ID: decision_verb_packs_20260826
Revises: sso_saml_20260826
"""
from alembic import op

revision = "decision_verb_packs_20260826"
down_revision = "sso_saml_20260826"
branch_labels = None
depends_on = None

_DDL = """
ALTER TABLE risk_decision DROP CONSTRAINT IF EXISTS risk_decision_action_check;
ALTER TABLE decision_playbook DROP CONSTRAINT IF EXISTS decision_playbook_action_check;
"""


def upgrade() -> None:
    op.execute(_DDL)


def downgrade() -> None:
    # restore the original financial-only vocabulary
    op.execute("""
        ALTER TABLE risk_decision ADD CONSTRAINT risk_decision_action_check
          CHECK (action IN ('reprice','engage','disclose','monitor','accept'));
        ALTER TABLE decision_playbook ADD CONSTRAINT decision_playbook_action_check
          CHECK (action IN ('reprice','engage','disclose','monitor','accept'));
    """)
