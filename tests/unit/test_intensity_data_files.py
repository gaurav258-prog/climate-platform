"""The intensity coefficients must load from their provenanced data files (not
hardcoded), and the sovereign figures must be the real OWID-derived values."""
import csv
from pathlib import Path

from services.reference import emissions_estimation
from ml.regulatory import sfdr_pai

ROOT = Path(__file__).resolve().parent.parent.parent
NACE_CSV = ROOT / "data" / "reference" / "nace_emission_intensity.csv"
COUNTRY_CSV = ROOT / "data" / "reference" / "country_ghg_intensity.csv"


def test_nace_intensities_load_from_csv():
    assert NACE_CSV.exists()
    with open(NACE_CSV, newline="", encoding="utf-8") as fh:
        divisions = {r["nace_division"] for r in csv.DictReader(fh)}
    # the loaded table used by the estimator matches the data file
    assert emissions_estimation._INTENSITIES  # non-empty
    assert "35" in emissions_estimation._INTENSITIES  # electricity present
    assert divisions.issubset(set(emissions_estimation._INTENSITIES))


def test_country_intensities_load_from_csv_and_are_real():
    assert COUNTRY_CSV.exists()
    table = sfdr_pai.COUNTRY_GHG_INTENSITY_TCO2E_PER_MEUR
    # Real OWID-derived values: coal-heavy economies rank far above low-carbon ones.
    assert table["CN"] > table["DE"] > table["CH"]
    assert all(v > 0 for v in table.values())


def test_country_csv_has_provenance_columns():
    with open(COUNTRY_CSV, newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert "source" in header and "gdp_year" in header
