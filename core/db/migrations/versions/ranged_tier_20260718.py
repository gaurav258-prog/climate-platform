"""The 'ranged' calibration tier — a crop whose driver explains real but partial variance.

WHY. Between 'indicative' (v0 defaults, no evidence, € withheld) and 'backtested' (reproduces a
real event, € as a point) there was nothing. Olive falls exactly in that gap: a 31-year drought
regression explains HALF its climate-attributable variance (r²=0.51, SPEI-6), correct sign, tail
captured directionally — genuinely useful signal, but ±~15pp on any single year. Publishing that
as a point € would be false precision; withholding it entirely wastes real information. So it is
published AS A RANGE, with the r² stated.

  sc_commodity_fit   the multi-year regression behind a ranged crop: slope/intercept + r² + the
                     residual band, plus n / score_mean / score_sxx so a proper PREDICTION
                     INTERVAL can be reconstructed (the band widens for scores outside training).
                     This is a REGRESSION across years — distinct from sc_model_validation, which
                     records single reproduced EVENTS.

  v_sc_commodity_calibration  gains the tier precedence backtested > ranged > indicative: a
                     passing event still wins (backtested); else a stored fit makes it 'ranged';
                     else 'indicative'. The tier stays DERIVED, never a typeable column — you
                     still cannot write your way to a published euro.
"""
import sqlalchemy as sa
from alembic import op

revision = "ranged_tier_20260718"
down_revision = "measured_basis_20260717"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sc_commodity_fit",
        sa.Column("commodity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin", sa.String(8), nullable=False),
        sa.Column("hazard_driver", sa.String(32), nullable=False),
        sa.Column("region_key", sa.String(64)),
        sa.Column("season_months", sa.ARRAY(sa.Integer)),
        sa.Column("spei_scale", sa.Integer),          # drought accumulation window (months)
        sa.Column("n_years", sa.Integer, nullable=False),
        sa.Column("slope", sa.Numeric(10, 5), nullable=False),
        sa.Column("intercept", sa.Numeric(10, 5), nullable=False),
        sa.Column("r2", sa.Numeric(5, 4), nullable=False),
        sa.Column("rmse", sa.Numeric(10, 5), nullable=False),
        sa.Column("score_mean", sa.Numeric(10, 5), nullable=False),
        sa.Column("score_sxx", sa.Numeric(16, 5), nullable=False),
        sa.Column("baseline_from", sa.Integer),
        sa.Column("baseline_to", sa.Integer),
        sa.Column("fit_version", sa.String(32)),
        sa.Column("source_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("commodity_id", "origin", "hazard_driver"),
    )

    op.execute("""
        CREATE OR REPLACE VIEW v_sc_commodity_calibration AS
        SELECT c.commodity_id, c.origin, c.sensitivity, c.world_share, c.hazard_driver,
               c.event_ref, c.source_note, c.impact_version, c.region_key, c.season_months,
               c.scoring_model, c.baseline_from, c.baseline_to,
               CASE
                 WHEN EXISTS (SELECT 1 FROM sc_model_validation v
                              WHERE v.commodity_id = c.commodity_id
                                AND v.origin::text = c.origin::text
                                AND v.passed
                                AND v.hazard::text = c.hazard_driver::text)
                   THEN 'backtested'
                 WHEN EXISTS (SELECT 1 FROM sc_commodity_fit f
                              WHERE f.commodity_id = c.commodity_id
                                AND f.origin::text = c.origin::text
                                AND f.hazard_driver::text = c.hazard_driver::text)
                   THEN 'ranged'
                 ELSE 'indicative'
               END AS calibration_tier
        FROM sc_commodity_calibration c
    """)


def downgrade():
    op.execute("""
        CREATE OR REPLACE VIEW v_sc_commodity_calibration AS
        SELECT c.commodity_id, c.origin, c.sensitivity, c.world_share, c.hazard_driver,
               c.event_ref, c.source_note, c.impact_version, c.region_key, c.season_months,
               c.scoring_model, c.baseline_from, c.baseline_to,
               CASE
                 WHEN EXISTS (SELECT 1 FROM sc_model_validation v
                              WHERE v.commodity_id = c.commodity_id
                                AND v.origin::text = c.origin::text
                                AND v.passed
                                AND v.hazard::text = c.hazard_driver::text)
                   THEN 'backtested'
                 ELSE 'indicative'
               END AS calibration_tier
        FROM sc_commodity_calibration c
    """)
    op.drop_table("sc_commodity_fit")
