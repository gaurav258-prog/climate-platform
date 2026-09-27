"""The intensity coefficients must load from their provenanced data files (not
hardcoded), and the sovereign figures must be the real OWID-derived values."""
import csv
from pathlib import Path

import pytest

from ml.regulatory import sfdr_pai
from services.reference import emissions_estimation

ROOT = Path(__file__).resolve().parent.parent.parent
NACE_CSV = ROOT / "data" / "reference" / "nace_emission_intensity.csv"
COUNTRY_CSV = ROOT / "data" / "reference" / "country_ghg_intensity.csv"


def test_nace_intensities_load_from_csv():
    assert NACE_CSV.exists()
    with open(NACE_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    divisions = {r["nace_division"] for r in rows}
    table = emissions_estimation._INTENSITIES
    # EXIOBASE values (from the CSV) win in the effective merged table...
    for r in rows:
        assert table[r["nace_division"]] == float(r["intensity_tco2e_per_meur"])
    # ...and the merge keeps full division coverage beyond what EXIOBASE separates
    # (e.g. pharma 21, which EXIOBASE folds into chemicals).
    assert divisions.issubset(set(table))
    assert "21" in table  # pharma, from the interim fallback


def test_exiobase_calibration_sane():
    """Carbon-intensive sectors rank far above light ones — a guard against a
    broken EXIOBASE parse silently shipping garbage coefficients."""
    t = emissions_estimation._INTENSITIES
    assert t["35"] > t["24"] > t["62"]         # electricity > basic metals > software
    assert t["35"] > 500 and t["62"] < 60       # order-of-magnitude sanity
    assert all(v > 0 for v in t.values())


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


def test_country_intensity_is_on_the_rts_basis_and_recomputes_from_its_own_inputs():
    """SFDR PAI 15 = tCO2e per €M GDP: total GHG (CO2e, excl. LULUCF) ÷ GDP at current prices in EUR, same year."""
    with open(COUNTRY_CSV, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert {"ghg_mt_co2e", "gdp_meur", "eur_per_usd", "basis"} <= set(rows[0])
    for r in rows:
        assert "current market prices" in r["basis"] and "CO2e" in r["basis"]
        assert float(r["intensity_tco2e_per_meur"]) == pytest.approx(float(r["ghg_mt_co2e"]) * 1e6 / float(r["gdp_meur"]), rel=2e-3)


def test_a_country_without_a_figure_is_left_out_not_given_a_default():
    from ml.regulatory.sfdr_pai import _sovereign_indicators
    comp = {"sovereign_ghg_intensity": 150.0, "sovereign_coverage_pct": 80.0, "sovereign_uncovered_countries": ["XK"]}
    pai15 = next(i for i in _sovereign_indicators(comp) if i["number"] == 15)
    assert pai15["coverage_pct"] == 80.0 and pai15["method"] == "partial" and "XK" in pai15["input_required"]
