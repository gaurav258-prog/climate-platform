"""Demote coffee: real FAO production data contradicts its validation record

Revision ID: coffee_demote_20260716
Revises: crop_registry_20260715
Create Date: 2026-07-16

Coffee/BR was marked passed=true on a curated label of "-12.7% (ICO/USDA approx)". We then
ingested the FAOSTAT bulk panel (9,264 real country-year labels) and cross-checked. It does
not hold up, on three independent counts:

  1. WORLD SHOCK. The calibration was fitted to reproduce a -12.7% WORLD supply shock in 2021.
     FAO's actual world green-coffee production fell -5.94% (11,239 -> 10,572 kt). The fitted
     target is ~2.1x the real shock.
  2. WORLD SHARE. We use Brazil = 0.35 of world coffee. FAO puts it at 28.2% in 2021
     (28.5/33.0/28.2/28.9% across 2019-22).
  3. BIENNIAL CYCLE — the big one. Brazil arabica alternate-bears, hard and regularly:
     off-years run -13.2/-12.6/-12.8/-7.1/-2.4/-5.6/-11.2/-15.2% across 2005-2019 with no
     weather in them. 2021's -19.4% is the worst off-year on record, but only ~8pp beyond a
     typical off-year. Our chain attributes a 38.5% yield shock to drought — it charges the
     entire biennial trough to climate.
  Net: the model's 13.48% world shock vs FAO's real -5.94% is ~2.3x over-attributed.

Some of the gap is convention (FAO calendar 2021 vs ICO crop-year 2021/22, green vs total),
and coffee's price genuinely did move +44-60% in 2021 — but a -5.94% world shock cannot
produce that through our chain, which means the chain is not what reproduced the event. We
cannot claim the coffee chain reproduces a real crop failure. So it does not publish a euro.

This is the derived-tier mechanism doing its job: flip the evidence, the claim follows
automatically (v_sc_commodity_calibration recomputes -> 'indicative' -> the publish gate
withholds coffee's euro). No code change, no hand-edited badge.

COCOA IS LEFT PASSED, deliberately and on the evidence: Cote d'Ivoire cocoa is NOT biennial
(2014 +13.0, 2015 +9.7, 2016 -9.0, 2017 +24.5, 2018 +3.9, 2019 +5.8, 2020 -1.6, 2021 +1.3,
2022 +5.9, 2023 -22.7, 2024 +3.7) — the 2023 collapse is an unambiguous outlier with no cycle
to confound it, FAO independently confirms it (-22.74% vs our curated -23.9%), and the origin
shares check out (GH 12-18% vs our 0.15; CI 36-42% vs our 0.45). The one caveat, recorded on
the row: FAO's calendar-2023 world cocoa shock is -8.88% where ICCO's crop-year figure is
-12.9%; the calibration targets ICCO, which is the industry reference for cocoa seasons.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "coffee_demote_20260716"
down_revision: Union[str, None] = "crop_registry_20260715"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE sc_model_validation v SET
            passed = false,
            skill_note = 'FAILS re-validation against the FAOSTAT panel (ingested 2026-07-16). '
                || 'Fitted to a -12.7% world shock; FAO real world green coffee 2021 = -5.94% '
                || '(11,239->10,572 kt), ~2.1x over. Brazil world share used 0.35; FAO says 28.2%. '
                || 'Worst of all, Brazil arabica alternate-bears (off-years -13.2/-12.6/-12.8/-7.1/'
                || '-2.4/-5.6/-11.2/-15.2% 2005-2019, no weather in them): 2021 -19.4% is only ~8pp '
                || 'beyond a typical off-year, but the chain charges a 38.5% yield shock to drought. '
                || 'Model world shock 13.48% vs FAO -5.94% = ~2.3x over-attributed. Euro withheld '
                || 'until the biennial cycle is separated from the climate signal and the target is '
                || 'restated on a stated convention.'
        FROM sc_commodities co
        WHERE co.name = 'Coffee' AND v.commodity_id = co.commodity_id
          AND v.origin = 'BR' AND v.hazard = 'drought';
    """)

    # Cocoa keeps its pass; record the FAO cross-check + the source convention on the evidence.
    op.execute("""
        UPDATE sc_model_validation v SET
            skill_note = v.skill_note || ' RE-VALIDATED vs FAOSTAT 2026-07-16: FAO independently '
                || 'confirms the CI collapse (-22.74% calendar 2023 vs our curated -23.9% for the '
                || '2023/24 season) and cocoa shows NO biennial cycle to confound it (CI 2014..2024: '
                || '+13.0/+9.7/-9.0/+24.5/+3.9/+5.8/-1.6/+1.3/+5.9/-22.7/+3.7). Origin shares check '
                || 'out: GH 12-18% (we use 0.15), CI 36-42% (we use 0.45, slightly high). CAVEAT: '
                || 'FAO calendar-2023 world cocoa is -8.88% where ICCO crop-year is -12.9%; this '
                || 'calibration targets ICCO, the industry reference for cocoa crop seasons.'
        FROM sc_commodities co
        WHERE co.name = 'Cocoa' AND v.commodity_id = co.commodity_id AND v.passed;
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE sc_model_validation v SET passed = true
        FROM sc_commodities co
        WHERE co.name = 'Coffee' AND v.commodity_id = co.commodity_id
          AND v.origin = 'BR' AND v.hazard = 'drought';
    """)
