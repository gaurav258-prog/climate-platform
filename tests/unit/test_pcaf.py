"""PCAF attribution — the one formula every vertical that claims a PCAF-attributed figure shares."""
from services.scoring.pcaf import attributed_financed_emissions, attribution_factor


def test_factor_is_exposure_over_evic():
    assert attribution_factor(1_000_000, 10_000_000) == 0.1


def test_factor_capped_at_one():
    assert attribution_factor(9_000_000, 1_000_000) == 1.0


def test_factor_none_without_evic():
    assert attribution_factor(1_000_000, None) is None
    assert attribution_factor(1_000_000, 0) is None
    assert attribution_factor(1_000_000, -5) is None


def test_factor_none_without_exposure():
    assert attribution_factor(None, 1_000_000) is None


def _asset(ghg1, ghg2, ghg3, outstanding, evic=None):
    return {"ghg1": ghg1, "ghg2": ghg2, "ghg3": ghg3, "outstanding_loan_balance_eur": outstanding, "evic_eur": evic}


def test_covered_loan_is_weighted_by_attribution_factor():
    rows = [_asset(100, 50, 200, outstanding=5_000_000, evic=50_000_000)]   # af = 0.1
    r = attributed_financed_emissions(rows, exposure_key="outstanding_loan_balance_eur", evic_key="evic_eur")
    assert r["attributed"] == {"scope1": 10, "scope2": 5, "scope3": 20}
    assert r["n_evic_covered"] == 1 and r["evic_coverage_pct"] == 100.0
    assert r["not_covered_total"] == 0


def test_loan_without_evic_is_excluded_from_attributed_and_shown_separately():
    rows = [_asset(100, 50, 200, outstanding=5_000_000, evic=None)]
    r = attributed_financed_emissions(rows, exposure_key="outstanding_loan_balance_eur", evic_key="evic_eur")
    assert r["attributed"] == {"scope1": 0, "scope2": 0, "scope3": 0}
    assert r["not_covered"] == {"scope1": 100, "scope2": 50, "scope3": 200}
    assert r["n_evic_covered"] == 0 and r["evic_coverage_pct"] == 0.0


def test_mixed_book_never_mixes_covered_and_not_covered():
    rows = [_asset(100, 0, 0, outstanding=1_000_000, evic=10_000_000),    # af=0.1 -> attributed 10
            _asset(200, 0, 0, outstanding=1_000_000, evic=None)]           # excluded, shown separately
    r = attributed_financed_emissions(rows, exposure_key="outstanding_loan_balance_eur", evic_key="evic_eur")
    assert r["attributed_total"] == 10 and r["not_covered_total"] == 200
    assert r["n_evic_covered"] == 1 and r["n_counterparties_with_emissions"] == 2
    assert r["evic_coverage_pct"] == 50.0


def test_a_stated_zero_is_a_figure_and_no_statement_is_coverage_not_zero():
    """E76: a counterparty that states 0 has emissions data (zero); one that states nothing is not counted as zero —
    it shows in the coverage (counterparties and share of exposure with emissions)."""
    rows = [_asset(0, 0, 0, outstanding=1_000_000, evic=10_000_000),
            _asset(None, None, None, outstanding=3_000_000, evic=None)]
    r = attributed_financed_emissions(rows, exposure_key="outstanding_loan_balance_eur", evic_key="evic_eur")
    assert r["n_counterparties"] == 2 and r["n_counterparties_with_emissions"] == 1
    assert r["exposure_with_emissions_pct"] == 25.0 and r["attributed_total"] == 0
    none = attributed_financed_emissions([rows[1]], exposure_key="outstanding_loan_balance_eur", evic_key="evic_eur")
    assert none["n_counterparties_with_emissions"] == 0 and none["evic_coverage_pct"] is None


def test_a_scope_not_stated_is_not_counted_and_a_scope_nobody_states_has_no_total():
    from services.scoring.pcaf import gross_emissions
    rows = [_asset(100, 50, None, outstanding=1, evic=None), _asset(10, None, None, outstanding=1, evic=None)]
    g = gross_emissions(rows)
    assert (g["scope1"], g["scope2"], g["scope3"], g["total"]) == (110, 50, None, 160)
    assert g["n_stating"] == {"scope1": 2, "scope2": 1, "scope3": 0} and g["n_with_emissions"] == 2
    assert gross_emissions([_asset(None, None, None, 1)])["total"] is None


def test_attribution_capped_even_when_outstanding_exceeds_evic():
    rows = [_asset(1000, 0, 0, outstanding=9_000_000, evic=1_000_000)]   # af would be 9x -> capped at 1.0
    r = attributed_financed_emissions(rows, exposure_key="outstanding_loan_balance_eur", evic_key="evic_eur")
    assert r["attributed"]["scope1"] == 1000
