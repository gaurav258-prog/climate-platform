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
    assert EE.intensity("24.10")["code"] == "C24"
    thin = [r["nace_code"] for r in csv.DictReader((REF / "nace_energy_intensity.csv").open()) if r["thin"]]
    for code in thin:                                                                        # too few countries → section figure
        assert EE.intensity(code[1:3])["code"] == code[0]
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


def test_a_company_gets_its_own_countrys_sector_figure_else_the_labelled_european_one():
    pl, eu = EE.intensity("35.11", "PL"), EE.intensity("35.11")
    assert pl["basis"].startswith("PL national figure") and pl["value"] > eu["value"]                   # coal-heavy Polish power
    us = EE.intensity("24.10", "US")                                                         # no national figure → European
    assert us["value"] == EE.intensity("24.10")["value"] and "no national figure for US" in us["basis"]
    assert "European countries" in us["basis"]


def test_a_basis_change_is_explained_in_plain_words_in_the_rts_explanation_column():
    from ml.regulatory.sfdr_pai import _basis_change_note, _explanation
    ind = {"number": 5, "method": "estimated", "coverage_pct": 100.0, "source": "x", "input_required": None}
    ind["change_note"] = _basis_change_note({"method": "partial", "coverage_pct": 7.7}, ind)
    text = _explanation(ind, 2025)
    assert "Not directly comparable with last year" in text and "7.7% → 100.0%" in text and "estimates" in text


def test_pai6_is_complete_when_every_high_impact_holding_reports():
    """E136: PAI 6 applies only to holdings in a high impact climate sector — a software holding (NACE J) must not keep
    it 'partial' forever; coverage stays a share of fund value for the EET."""
    from ml.regulatory.sfdr_pai import esg_short_pct
    from services.fund_energy import energy_pais
    rows = [_row(nace_code="24.10", energy_int=1.5), _row(nace_code="62.01", issuer_id="y")]
    pai6 = energy_pais(rows, 2.0, energy_facts(rows))["pai_6"]
    assert (pai6["coverage_pct"], pai6["eligible_pct"], pai6["estimated_pct"]) == (50.0, 50.0, 0.0)
    assert esg_short_pct(pai6) == 0.0
    rows.append(_row(nace_code="24.10", issuer_id="z"))                                       # no figure → estimated
    pai6 = energy_pais(rows, 3.0, energy_facts(rows))["pai_6"]
    assert esg_short_pct(pai6) == pytest.approx(33.3, abs=0.1)
    assert esg_short_pct({"coverage_pct": 80.0}) == 20.0                                      # whole-fund indicators
