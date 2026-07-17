"""The validation record must state the VOLUME claim, and must not state it circularly.

TWO REAL DEFECTS, found 2026-07-17 by reading the rows instead of the notes.

1. THE MODEL FIGURE WAS COPIED FROM THE OBSERVATION. cocoa_refit_20260716 wrote
       observed_prod_shock_pct = -8.88,
       model_prod_shock_pct    = -8.88,
   in one statement, and the skill_note then advertised "INDEPENDENT CONFIRMATION ... two
   unrelated sources converging". They cannot converge: one was assigned from the other. The
   engine's actual world shock for cocoa is 8.92% (compute() -> global_shock_pct, from the
   re-fitted per-origin sensitivities against the seasonal heat climatology). Against FAOSTAT's
   independently measured 8.88% that is a 0.45% error — the claim SURVIVES, and it is worth
   more now because the two numbers are no longer the same number. This is the same circularity
   caught in the cocoa re-fit itself; it had simply been persisted rather than fixed.

2. COFFEE'S OBSERVED FIGURE IS THE PRESS NUMBER ITS OWN NOTE RETIRED. observed_prod_shock_pct
   sat at -20.00 while the note beside it says "FAO real world green coffee 2021 = -5.94%
   (11,239->10,572 kt)". The re-validation corrected the prose and left the column. So the
   failure was recorded against the wrong target: 13.48 vs -20.00 looks like a modest miss;
   13.48 vs -5.94 is the real ~2.3x over-attribution that withheld coffee's euro.

Also adds price_claim_retired. The price columns are KEPT — they are the audit trail of what
we used to assert and how it was fitted, and deleting them would erase the record of a
corrected mistake — but they are marked so that no reader, and no UI, mistakes them for a
standing claim. Across 440 real crop-years a world supply shock explains r^2 = 0.018 of the
contemporaneous price move; the product no longer forecasts price, so the price columns are
history, not a claim.
"""
from alembic import op
import sqlalchemy as sa

revision = "validation_volume_claim_20260717"
down_revision = "amp_curve_flag_20260716"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sc_model_validation",
                  sa.Column("price_claim_retired", sa.Boolean(), server_default=sa.true(),
                            nullable=False))

    # (1) The engine's real output, verified live before this migration was written, replacing
    # the copied figure. Sign convention follows the column: a contraction is negative.
    op.execute("""
        UPDATE sc_model_validation
        SET model_prod_shock_pct = -8.92,
            skill_note = replace(skill_note,
                'INDEPENDENT CONFIRMATION: the shock required to produce the observed price '
                '(8.61%) matches FAO''s separately measured world production shock (8.88%) '
                'within 3.1% -- two unrelated sources converging.',
                'THE CLAIM: the engine''s modelled world supply shock is 8.92% against '
                'FAOSTAT''s independently measured 8.88% -- a 0.45% error between two figures '
                'with no shared input. (Corrected 2026-07-17: this row previously carried a '
                'model figure of -8.88 COPIED from the observation, and called the resulting '
                'exact match an independent confirmation. It was circular. The real engine '
                'output is 8.92 and the claim holds on its own.)')
        WHERE event = 'Cocoa 2023/24' AND passed
    """)

    # (2) Restore coffee's real target from its own note. The model figure -13.48 already
    # reflects the chain's claim; only the observation was stale.
    op.execute("""
        UPDATE sc_model_validation
        SET observed_prod_shock_pct = -5.94,
            skill_note = skill_note || ' TARGET CORRECTED 2026-07-17: observed_prod_shock_pct '
                'was still the -20.0% press figure this note had already retired; it is now '
                'FAOSTAT''s -5.94% (11,239->10,572 kt). The recorded miss is therefore the real '
                '2.3x over-attribution, not the flattering 13.48-vs-20.0 it used to display.'
        WHERE event = 'Coffee 2021'
    """)


def downgrade():
    op.drop_column("sc_model_validation", "price_claim_retired")
    op.execute("UPDATE sc_model_validation SET model_prod_shock_pct = -8.88 "
               "WHERE event = 'Cocoa 2023/24' AND passed")
    op.execute("UPDATE sc_model_validation SET observed_prod_shock_pct = -20.00 "
               "WHERE event = 'Coffee 2021'")
