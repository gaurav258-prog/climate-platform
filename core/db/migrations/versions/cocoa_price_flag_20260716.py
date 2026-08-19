"""Flag cocoa: its "observed +177%" does not reconcile with the reference price series

Revision ID: cocoa_price_flag_20260716
Revises: sc_prices_20260716
Create Date: 2026-07-16

Cocoa's validation record claims model +176.8% vs observed +177%. We now hold the World Bank
Pink Sheet monthly series — whose Cocoa quote IS the ICCO daily average, the industry
reference for cocoa — and no measure of it reproduces +177%:

    crop-year mean Oct-Sep 2023/24 (the trade convention) : +115.8%
    calendar-2024 mean                                    : +123.4%
    April-2024 peak vs 2022 mean                          : +307%

Against the correct convention the model OVER-PREDICTS by ~1.5x (+176.8% vs +115.8%). The
"+177%" appears to have been a hand-typed press figure on an unstated basis, and the backtest
matched the model to it rather than to a reference series.

We do NOT silently demote here. Cocoa passed two independent checks today — FAO confirms the
CI production collapse (-22.74%) and the crop shows no biennial cycle to confound it — and the
gap may partly be an instrument/basis question (ICE front-month vs ICCO daily average). But
the claim as written is not supported, so the record must say so rather than carry a tidy
match that the data does not back. Flagged for re-validation against the ingested series, on a
stated convention, with the question surfaced to a human rather than resolved by fiat.

Recorded on the evidence row so it travels with the claim.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "cocoa_price_flag_20260716"
down_revision: Union[str, None] = "sc_prices_20260716"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE sc_model_validation v SET
            skill_note = v.skill_note || ' PRICE TARGET UNRECONCILED (2026-07-16): the claimed '
                || 'observed +177% matches no measure of the World Bank/ICCO reference series — '
                || 'crop-year Oct-Sep 2023/24 = +115.8%, calendar-2024 = +123.4%, Apr-2024 peak '
                || '= +307%. On the trade convention (crop-year) the model OVER-PREDICTS ~1.5x '
                || '(+176.8% vs +115.8%). The +177% looks like a hand-typed press figure on an '
                || 'unstated basis. Production side still holds (FAO confirms CI -22.74%, no '
                || 'biennial cycle). Needs re-validation against sc_commodity_prices on a stated '
                || 'convention; may partly be ICE front-month vs ICCO daily-average basis.'
        FROM sc_commodities co
        WHERE co.name = 'Cocoa' AND v.commodity_id = co.commodity_id AND v.passed;
    """)


def downgrade() -> None:
    pass
