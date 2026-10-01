"""One obligation per financial product too (E93): the obligation key counted the organisation, report, period and
entity but not the fund, so an asset manager with two Art. 8 / 9 funds could not be owed both funds' periodic documents
for one year — the second insert broke the calendar (as the live-filing rule did before E90).

Revision ID: obligation_fund_key_20261001
Revises: eudr_intake_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "obligation_fund_key_20261001"
down_revision: Union[str, None] = "eudr_intake_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-00000000fef1"
_F1, _F2 = "0bbe0bbe-0000-4000-8000-00000000fea1", "0bbe0bbe-0000-4000-8000-00000000fea2"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'asset_manager', 'LU');
                 INSERT INTO funds (fund_id, org_id, name, fund_type, sfdr_classification)
                 VALUES ('{_F1}', '{_ORG}', 'probe 1', 'fund', 'article_8'), ('{_F2}', '{_ORG}', 'probe 2', 'fund', 'article_8');
                 INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency, fund_id, filing_role)
                 VALUES ('{_ORG}', 'sfdr_periodic', '2026-12-31', 'FY2026', '2027-04-30', 'annual', '{_F1}', 'product'),
                        ('{_ORG}', 'sfdr_periodic', '2026-12-31', 'FY2026', '2027-04-30', 'annual', '{_F2}', 'product');""",
    "cleanup": f"""DELETE FROM regulatory_obligation WHERE org_id = '{_ORG}'; DELETE FROM funds WHERE org_id = '{_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        DROP INDEX ux_reg_obligation_key;
        CREATE UNIQUE INDEX ux_reg_obligation_key ON regulatory_obligation (org_id, framework, period_end,
            COALESCE(entity_id, '00000000-0000-0000-0000-000000000000'::uuid),
            COALESCE(fund_id, '00000000-0000-0000-0000-000000000000'::uuid));
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_obligation GROUP BY org_id, framework, period_end, entity_id HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'cannot downgrade obligation_fund_key_20261001: several funds are owed the same report for one period';
            END IF;
        END $$;
        DROP INDEX ux_reg_obligation_key;
        CREATE UNIQUE INDEX ux_reg_obligation_key ON regulatory_obligation (org_id, framework, period_end,
            COALESCE(entity_id, '00000000-0000-0000-0000-000000000000'::uuid));
    """)
