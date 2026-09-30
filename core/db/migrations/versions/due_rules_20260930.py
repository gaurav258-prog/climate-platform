"""Filing deadlines follow the mandate's rule — stored dates that were derived from a wrong rule corrected.

Two stores held the same deadline and disagreed: the typed month/day of each report type (services.governance.filings)
and the cited rule of its mandate (data/reference/regulatory_mandates.json). Four typed dates were wrong: insurer_solvency
30 April (Del. Reg. 2015/35 Art. 312: 14 weeks after the financial year end — 8 April for 31 December), bank_p3esg and
csrd_e1 31 March and assetmgmt_tcfd 30 June (their mandates: with the annual report, 4 months after year end). And the
rule reader clamped a month end to the 28th (4 months after 31 December gave 28 April). Only derived dates change:
obligations the platform dated itself (source 'entity') and supervisory deadlines drawn from the rule (due_source
'registry') with the obligations propagated from them; a date an authority or an organisation set is untouched.

Revision ID: due_rules_20260930
Revises: postal_code_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "due_rules_20260930"
down_revision: Union[str, None] = "postal_code_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# frozen here: the report types whose typed date was wrong → (the corrected rule as SQL, the old typed month/day)
_FOUR_MONTHS = "(date_trunc('month', period_end) + interval '5 months - 1 day')::date"
_FIX = {
    "insurer_solvency": ("(period_end + interval '14 weeks')::date", (4, 30)),
    "bank_p3esg": (_FOUR_MONTHS, (3, 31)),
    "csrd_e1": (_FOUR_MONTHS, (3, 31)),
    "assetmgmt_tcfd": (_FOUR_MONTHS, (6, 30)),
}
# mandates whose rule is 'with the annual report, 4 months after year end'
_ANNUAL_REPORT = ("crr_449a_pillar3_esg", "taxonomy_art8_credit", "assetmgmt_tcfd_guidance", "taxonomy_art8_reit", "csrd_esrs_e1")
_MONTH_END = "period_end = (date_trunc('month', period_end) + interval '1 month - 1 day')::date"


def upgrade() -> None:
    for fw, (rule, (m, d)) in _FIX.items():
        op.execute(f"""UPDATE regulatory_obligation SET due_date = {rule}
                       WHERE source = 'entity' AND framework = '{fw}' AND {_MONTH_END}
                         AND due_date = make_date(extract(year FROM period_end)::int + 1, {m}, {d})""")
    ids = ", ".join(f"'{x}'" for x in _ANNUAL_REPORT)
    op.execute(f"""
        WITH fixed AS (
            UPDATE supervision_deadline SET due_date = (date_trunc('month', due_date) + interval '1 month - 1 day')::date
            WHERE due_source = 'registry' AND mandate_id IN ({ids}) AND {_MONTH_END} AND extract(day FROM due_date) = 28
            RETURNING deadline_id, due_date)
        UPDATE regulatory_obligation o SET due_date = f.due_date FROM fixed f
        WHERE o.supervision_deadline_id = f.deadline_id AND o.source = 'supervisor'
          AND extract(day FROM o.due_date) = 28""")


def downgrade() -> None:
    for fw, (rule, (m, d)) in _FIX.items():
        op.execute(f"""UPDATE regulatory_obligation SET due_date = make_date(extract(year FROM period_end)::int + 1, {m}, {d})
                       WHERE source = 'entity' AND framework = '{fw}' AND {_MONTH_END} AND due_date = {rule}""")
    ids = ", ".join(f"'{x}'" for x in _ANNUAL_REPORT)
    op.execute(f"""
        WITH back AS (
            UPDATE supervision_deadline SET due_date = make_date(extract(year FROM due_date)::int, extract(month FROM due_date)::int, 28)
            WHERE due_source = 'registry' AND mandate_id IN ({ids}) AND {_MONTH_END}
              AND due_date = (date_trunc('month', due_date) + interval '1 month - 1 day')::date
            RETURNING deadline_id, due_date)
        UPDATE regulatory_obligation o SET due_date = b.due_date FROM back b
        WHERE o.supervision_deadline_id = b.deadline_id AND o.source = 'supervisor'""")
