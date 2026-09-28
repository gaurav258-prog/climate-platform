"""PAI 5/6 company energy facts: reported → vendor → estimated per company; estimates come from cited sector / country
tables that recompute from their own inputs; only likely unit slips are flagged."""
import csv
from pathlib import Path

import pytest

from services.fund_energy import _implausible, energy_facts
from services.reference import energy_estimation as EE

REF = Path(__file__).resolve().parents[2] / "data" / "reference"


def _row(**k):
    base = {"mv": 1.0, "nace_code": "24.10", "country": "DE", "revenue_eur": 2e9, "energy_int": None, "energy_gwh": None,
            "non_renew": None, "nr_cons": None, "nr_prod": None, "issuer_id": "x", "issuer_name": "X"}
    return {**base, **k}


def test_reference_tables_recompute_from_their_inputs():
    rows = list(csv.DictReader((REF / "nace_energy_intensity.csv").open()))
    for r in rows:
        assert float(r["intensity_gwh_per_meur"]) == pytest.approx(float(r["energy_tj"]) / 3.6 / float(r["turnover_meur"]), rel=1e-3)
    by = {r["nace_code"]: float(r["intensity_gwh_per_meur"]) for r in rows}
    # electricity is in the division figures (it used to be missing below section level): machinery ≈ its section's
    # electricity-heavy profile, not fuel-only
    assert by["C28"] > 0.05 and by["C24"] > by["C28"] and by["H51"] > by["H49"]
    rows = {r["country_iso2"]: r for r in csv.DictReader((REF / "country_renewable_shares.csv").open())}
    assert 0 < float(rows["DE"]["renewable_share_energy_pct"]) < 100 and float(rows["NO"]["renewable_share_elec_pct"]) > 90


def test_lookups_use_the_finest_level_published():
    assert EE.intensity("24.10")["code"] == "C24" and EE.intensity("19.20")["code"] == "C"     # C19: 9 countries, 48% → section
    assert EE.intensity("51.10")["value"] > EE.intensity("47.11")["value"]                     # airlines ≫ retail
    assert EE.intensity("62.01") is None and EE.intensity(None) is None                       # not a high-impact sector
    assert EE.non_renewable_production("FR")["value"] > 50                                    # nuclear is non-renewable


def test_a_real_figure_always_wins_and_estimates_are_labelled():
    f = energy_facts([_row(energy_int=0.5, nr_cons=30)])[0]
    assert f["intensity"][:2] == (0.5, "reported") and f["cons"][:2] == (30, "reported")
    f = energy_facts([_row(energy_gwh=1000)])[0]                                             # 1000 GWh ÷ €2,000M
    assert f["intensity"][:2] == (0.5, "reported")
    f = energy_facts([_row()])[0]
    assert f["intensity"][1] == "estimated" and "Eurostat" in f["intensity"][2] and f["cons"][1] == "estimated"
    assert f["prod"] is None                                                                  # not an energy producer
    assert energy_facts([_row(nace_code="35.11", country="FR")])[0]["prod"][1] == "estimated"


def test_only_likely_unit_slips_are_flagged():
    assert _implausible("energy_intensity", 790, 0.79) and _implausible("energy_intensity", 0.00079, 0.79)
    assert _implausible("energy_intensity", 2.4, 0.79) is None                                # 3× — plausible
    assert _implausible("non_renewable_consumption", 0.6, 76)                                 # fraction for a %
    assert _implausible("non_renewable_consumption", 18, 76) is None                          # buys green power — fine


def test_pai5_counts_each_company_once():
    from services.fund_energy import energy_pais
    rows = [_row(nace_code="35.11", country="DE", nr_cons=10, nr_prod=90), _row(nace_code="24.10", nr_cons=50)]
    out = energy_pais(rows, 2.0, energy_facts(rows))["pai_5"]
    assert out["value"] == pytest.approx((90 + 50) / 2)                                       # producer → production share
