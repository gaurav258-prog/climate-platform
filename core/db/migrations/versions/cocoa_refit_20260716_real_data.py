"""Re-fit cocoa on REAL data: sensitivity 0.294 -> 0.1995, targets from series not press

Revision ID: cocoa_refit_20260716
Revises: cocoa_price_flag_20260716
Create Date: 2026-07-16

Cocoa's calibration was fitted to two hand-typed numbers: ICCO's -12.9% world crop (crop-year)
and a press "+177%" price move. Today we ingested the actual series and both targets moved.

RE-FIT, every term now from ingested data:
    price target   : +115.8%  World Bank Pink Sheet cocoa (= the ICCO daily average, the
                     industry reference), crop-year Oct-Sep 2023/24 -- the trade convention.
                     Was: "+177%", which matches NO measure of the reference series.
    world shock    :   8.88%  FAOSTAT world cocoa 2023 (5,623 -> 5,123 kt).
                     Was: 12.9% (ICCO, hand-typed).
    stocks         :  26.4%  ICCO (unchanged -- USDA PSD does not track cocoa; still the most
                     leveraged unverified number in the model, and now the ONLY one).
    elasticity     :   0.20  (unchanged)

THE CHAIN NOW VALIDATES INDEPENDENTLY, which the old one never did:
    price_move = A(stocks) x global_shock / elasticity
    A(26.4) = 2.690
    Required world shock to produce the REAL +115.8% price = 8.61%
    FAO's INDEPENDENTLY MEASURED world shock                = 8.88%
    -> agree within 3.1%
That is two separate sources -- a price series and a production panel -- converging on the
same number. The old calibration matched a press headline to a hand-typed crop figure and
called it a backtest.

    implied sensitivity: global_shock = ys x (CI 0.45 + GH 0.15)
                         ys = 8.88 / 0.60 = 14.80%  at seasonal heat 74.2
                         sens = 0.1480 / 0.742 = 0.1995   (was 0.294, i.e. 32% too hot)
Model now predicts +119.4% vs the real +115.8% (3.1% error), where it previously predicted
+176.8% against a real +115.8% -- a 1.5x over-prediction dressed up as a 0.1pp match.

Cocoa's euro falls accordingly. That is the point.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "cocoa_refit_20260716"
down_revision: Union[str, None] = "cocoa_price_flag_20260716"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE sc_commodity_calibration c SET
            sensitivity = 0.1995,
            impact_version = 'sc-impact-v0.4',
            source_note = source_note || ' RE-FIT 2026-07-16 on ingested series: sensitivity '
                || '0.294 -> 0.1995. Fitted so the chain reproduces the REAL crop-year price '
                || 'move (+115.8%, World Bank/ICCO Oct-Sep 2023/24) at the REAL world shock '
                || '(8.88%, FAOSTAT 2023). The old 0.294 was fitted to a press "+177%" and '
                || 'ICCO hand-typed -12.9%, and over-predicted the real move by ~1.5x.'
        FROM sc_commodities co
        WHERE co.name = 'Cocoa' AND c.commodity_id = co.commodity_id;
    """)
    op.execute("""
        UPDATE sc_model_validation v SET
            observed_price_move_pct = 115.8,
            model_price_move_pct = 119.4,
            observed_prod_shock_pct = -8.88,
            model_prod_shock_pct = -8.88,
            impact_version = 'sc-impact-v0.4',
            tolerance_pct = 10.0,
            passed = true,
            source = 'FAOSTAT QCL bulk (production); World Bank Pink Sheet = ICCO daily average (price)',
            skill_note = 'RE-VALIDATED 2026-07-16 against ingested series, replacing hand-typed '
                || 'press figures. Chain: A(26.4% stocks)=2.690 x world shock 8.88% / elasticity '
                || '0.20 = +119.4% vs the REAL crop-year move +115.8% (Oct-Sep 2023/24, World '
                || 'Bank = ICCO daily average) -> 3.1% error. INDEPENDENT CONFIRMATION: the shock '
                || 'required to produce the observed price (8.61%) matches FAO''s separately '
                || 'measured world production shock (8.88%) within 3.1% -- two unrelated sources '
                || 'converging. Sensitivity re-fitted 0.294 -> 0.1995 on the seasonal heat score '
                || '74.2. Production side independently holds: FAO confirms CI -22.74% and cocoa '
                || 'has NO biennial cycle to confound it (CI 2014-24: +13.0/+9.7/-9.0/+24.5/+3.9/'
                || '+5.8/-1.6/+1.3/+5.9/-22.7/+3.7). REMAINING GAP: stocks-to-use 26.4% is still '
                || 'hand-entered from ICCO -- USDA PSD does not track cocoa -- and it is now the '
                || 'only unverified term in the chain, on the most leveraged parameter.'
        FROM sc_commodities co
        WHERE co.name = 'Cocoa' AND v.commodity_id = co.commodity_id;
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE sc_commodity_calibration c SET sensitivity = 0.294, impact_version = 'sc-impact-v0.3'
        FROM sc_commodities co WHERE co.name = 'Cocoa' AND c.commodity_id = co.commodity_id;
    """)
