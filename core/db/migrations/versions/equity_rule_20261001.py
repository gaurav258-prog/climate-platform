"""The 'equity_consolidation' interpretation switch is retired: every text a group filing is governed by sets the rule —
an equity-method holding's book is not consolidated (CRR Art. 18(5),(7); Solvency II Del. Reg. 2015/35 Art. 335(1)(d);
Directive 2013/34/EU Art. 27(1); ESRS 1 §62, §67 — data/reference/consolidation/regimes.json, E75). A stored choice is
moved to a side table; the downgrade puts it back.

Revision ID: equity_rule_20261001
Revises: materiality_stated_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "equity_rule_20261001"
down_revision: Union[str, None] = "materiality_stated_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE org_calc_settings_equity_retired_20261001 AS
            SELECT org_id, interpretation -> 'equity_consolidation' AS equity_consolidation
            FROM org_calc_settings WHERE interpretation ? 'equity_consolidation';
        UPDATE org_calc_settings SET interpretation = interpretation - 'equity_consolidation'
        WHERE interpretation ? 'equity_consolidation';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE org_calc_settings s SET interpretation = s.interpretation || jsonb_build_object('equity_consolidation', r.equity_consolidation)
        FROM org_calc_settings_equity_retired_20261001 r WHERE r.org_id = s.org_id;
        DROP TABLE org_calc_settings_equity_retired_20261001;
    """)
