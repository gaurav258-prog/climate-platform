"""Reconcile the cocoa recorded world-shock to the live engine output (8.92 → 8.82).

validation_volume_claim_20260717 recorded model_prod_shock_pct = -8.92, "verified live before this
migration was written". The scoring chain has since drifted: the current per-origin engine output
for Cocoa 2023/24 is 8.82% (CI yield-shock 14.8% × world-share 0.45 = 6.66, + GH 14.4% × 0.15 =
2.16), reproducibly — a fresh score_cocoa_heat run and the demo DB both give 8.82. The recorded
8.92 is therefore stale on any DB scored today, and the anti-circularity test
(test_cocoa_recorded_claim_matches_what_the_engine_actually_produces) fails because the Trust page
would advertise a number the product no longer computes — exactly the failure that test exists to
catch. Reconcile the record (and the note figures) to the engine's true output.

The claim SURVIVES and stays honest: 8.82% modelled vs FAOSTAT's independently-measured 8.88% is a
0.68% error between two figures with no shared input (was 0.45% at 8.92) — still a strong,
non-circular match. Only the plot heat score (74.2) is unchanged; the small shift is in the
spend-weighted per-origin aggregation.

Revision ID: cocoa_claim_reconcile_20260719
Revises: world_share_nullable_20260719
"""
from alembic import op

revision = "cocoa_claim_reconcile_20260719"
down_revision = "world_share_nullable_20260719"
branch_labels = None
depends_on = None

_APPEND = (" (Reconciled 2026-07-19: the recorded 8.92 from 07-17 had drifted vs the live engine "
           "after a later score re-fit; the engine output on the current scores is 8.82, so the "
           "record now matches it — the anti-circularity test enforces record==engine.)")


def upgrade():
    # value + note figures → the live engine's output; guard the append so it is idempotent
    # (the demo DB was reconciled live before this migration; don't double-append there).
    op.execute("""
        UPDATE sc_model_validation
        SET model_prod_shock_pct = -8.82,
            skill_note = replace(replace(skill_note, '8.92', '8.82'),
                                 'a 0.45% error between', 'a 0.68% error between')
              || CASE WHEN skill_note LIKE '%Reconciled 2026-07-19%' THEN '' ELSE :appended END
        WHERE event = 'Cocoa 2023/24' AND passed
    """.replace(":appended", "'" + _APPEND.replace("'", "''") + "'"))


def downgrade():
    op.execute("UPDATE sc_model_validation SET model_prod_shock_pct = -8.92 "
               "WHERE event = 'Cocoa 2023/24' AND passed")
