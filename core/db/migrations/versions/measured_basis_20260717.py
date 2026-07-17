"""Disclose WHAT PHYSICAL THING each crop's yield labels actually count.

THE ISSUE. Our commodity names are the bought GOOD ("Olive oil", "Cane sugar", "Wine grapes"),
but the yield series behind them measure the raw CROP: FAOSTAT "Olives" (the fruit), "Sugar
cane", "Grapes". Both our sources agree the labels are the raw crop -- FAOSTAT and Eurostat
match within ~5-10% for the same crop-year, so this is not a data error and the PERCENTAGE shock
we compute is valid either way (a crop that loses 30% of its fruit loses ~30% of the oil that
fruit would have made). Modelling the raw crop is in fact correct: the crop in the field is what
the weather damages.

What was wrong is that NOTHING said so. A reader sees "Olive oil -34%" and reasonably assumes
tonnes of oil. For most crops the basis is a units question (5 kg olives -> 1 kg oil). For wine
grapes it is a POPULATION question: FAO "Grapes" includes table and drying grapes, not only wine
grapes -- a caveat worth stating plainly, not just a conversion factor.

So: a `measured_basis` column, populated per crop, surfaced wherever the number shows. No number
changes; the label stops implying something it does not measure.
"""
from alembic import op
import sqlalchemy as sa

revision = "measured_basis_20260717"
down_revision = "validation_volume_claim_20260717"
branch_labels = None
depends_on = None

# our commodity name -> the physical quantity its yield labels actually count
BASIS = {
    "Cocoa":       "Cocoa beans (the crop) — directly the traded bean, no conversion.",
    "Coffee":      "Green coffee (the crop) — directly the traded green bean.",
    "Olive oil":   "Olives, the fruit (FAOSTAT/Eurostat), NOT pressed oil. ~5 kg fruit per 1 kg "
                   "oil; the % shock carries over, the tonnage does not.",
    "Cane sugar":  "Sugar cane (the crop), NOT refined sugar. ~8-9 kg cane per 1 kg sugar.",
    "Sugar beet":  "Sugar beet (the crop, root), NOT refined sugar.",
    "Almonds":     "Almonds in shell, NOT shelled kernels. ~2 kg in-shell per 1 kg kernel.",
    "Wine grapes": "Grapes (FAOSTAT/Eurostat) — INCLUDES table and drying grapes, not wine "
                   "grapes alone. A population caveat, not just a conversion.",
    "Citrus":      "Citrus fruit, fresh (the crop).",
    "Durum wheat": "Durum wheat grain (the crop).",
    "Palm oil":    "Oil palm fresh fruit bunches (FAOSTAT 'Oil palm fruit'), NOT crude palm oil. "
                   "~5 kg FFB per 1 kg oil.",
    "Soybean":     "Soybeans (the crop) — directly the traded bean.",
    "Rice":        "Rice, paddy (the crop), NOT milled rice. ~1.5 kg paddy per 1 kg milled.",
    "Maize":       "Maize grain (the crop).",
}


def upgrade():
    op.add_column("sc_commodities", sa.Column("measured_basis", sa.Text()))
    conn = op.get_bind()
    for name, basis in BASIS.items():
        conn.execute(
            sa.text("UPDATE sc_commodities SET measured_basis = :b WHERE name = :n"),
            {"b": basis, "n": name},
        )


def downgrade():
    op.drop_column("sc_commodities", "measured_basis")
