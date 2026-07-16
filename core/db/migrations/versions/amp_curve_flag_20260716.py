"""Flag A(s): the amplification curve is unvalidated, and cocoa's sensitivity is fitted to it

Revision ID: amp_curve_flag_20260716
Revises: cocoa_refit_20260716
Create Date: 2026-07-16

A(s) = (34.7/s)^3.62 decides whether a 9% crop loss moves price 20% or 200%. It is the most
leveraged parameter in the product and it multiplies every euro we publish. It was fitted
through TWO anchor points:
    cocoa 2023/24 : stocks 26.4% -> A 2.69   (ICCO, hand-entered)
    coffee 2021   : stocks 40%   -> A 0.60   (hand-entered)
and the code itself flagged it as "a DIRECTION, not a calibrated curve".

TODAY WE PROVED ONE ANCHOR IS FABRICATED: coffee's real 2021 stocks-to-use was 14.2% (USDA
PSD), not 40%. So the curve's SHAPE rests on a number that does not exist.

TESTED IT AGAINST THE REAL PANEL (scripts/fit_amplification_curve.py), now that prices
(World Bank), stocks (USDA PSD) and world production (FAOSTAT) are all ingested. Inverting the
chain on every crop-year with a real contraction and a real price response gives only FOUR
usable observations, and they suggest an exponent near 1.8 against the hardcoded 3.62 — about
half as steep — with r=0.409. Four points cannot settle it. We are NOT replacing a 2-point
curve with a 4-point curve: that is the same mistake wearing a lab coat. A(s) is recorded as
UNVALIDATED.

WHAT THIS MEANS FOR COCOA, stated on its evidence row because the claim must carry it:
A and the crop sensitivity are CONFOUNDED. Cocoa's re-fit (sens 0.294 -> 0.1995) was fitted
GIVEN A(26.4)=2.69, and the chain does reproduce the real event on real data (model world
shock 8.92% vs FAO 8.88%; model price +120.0% vs WB/ICCO +115.8%). That match is real and it
is evidence. But with ONE event you cannot identify the SPLIT between "the crop is this
sensitive to heat" and "the market amplifies this much" — only their product is pinned. If
A(s) is later re-fitted on a proper panel, cocoa's sensitivity must be re-fitted with it.

Two independent shortfalls remain on cocoa, both now recorded:
  1. stocks-to-use 26.4% is hand-entered from ICCO (USDA PSD does not track cocoa; FAOSTAT SUA
     says 41.1% for 2023 on a different stock definition — the two disagree by ~56%).
  2. A(s) itself is unvalidated, and (1) is its input.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "amp_curve_flag_20260716"
down_revision: Union[str, None] = "cocoa_refit_20260716"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE sc_model_validation v SET
            skill_note = v.skill_note || ' AMPLIFICATION CAVEAT (2026-07-16): A(s)=(34.7/s)^3.62 '
                || 'is UNVALIDATED — it was fitted through 2 anchors and one of them (coffee at '
                || '40% stocks) is fabricated; the real figure is 14.2% (USDA PSD). Tested against '
                || 'the ingested price/stocks/production panel: only 4 usable observations, '
                || 'suggesting an exponent near 1.8 vs the hardcoded 3.62 (r=0.409) — too few to '
                || 'refit. CONSEQUENCE: A and sensitivity are CONFOUNDED. This calibration '
                || 'reproduces the real event (shock 8.92% vs FAO 8.88%; price +120.0% vs ICCO '
                || '+115.8%) and that match is real, but with ONE event only their PRODUCT is '
                || 'identified, not the split. If A(s) is refitted on a proper panel, this '
                || 'sensitivity must be refitted with it. Also: the 26.4% stocks input is itself '
                || 'hand-entered (FAOSTAT SUA says 41.1% on a different stock definition).'
        FROM sc_commodities co
        WHERE co.name = 'Cocoa' AND v.commodity_id = co.commodity_id AND v.passed;
    """)


def downgrade() -> None:
    pass
