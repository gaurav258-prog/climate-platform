"""Asset-manager holdings-book TCFD form — renders the rich snapshot, not the thin generic fallback."""
from services.governance.filing_form import build_form


def _snap():
    return {
        "rollup": {"n_holdings": 70, "n_scored": 70, "n_flagged": 12, "var_method": "combined",
                   "total_portfolio_value_eur": 1_743_600_000, "total_climate_var_eur": 487_000_000,
                   "portfolio_climate_var_pct": 27.9, "by_bucket": {"VH": {"value_eur": 1_629_000_000}},
                   "top_holdings": [{"name": "ACME plc", "climate_var_eur": 40_000_000, "headline_hazard": "flood"}]},
        "concentration": {"coverage_pct": 100.0, "region_hhi": 0.31, "effective_regions": 3.2,
                          "hazard_hhi": 0.4, "effective_hazards": 2.5, "top_region": "EU", "top_hazard": "flood"},
        "by_hazard": {"flood": {"exposed_value_eur": 500_000_000, "n_exposed": 30}},
    }


def test_am_form_has_rich_sections_not_generic():
    secs = {s["section"] for s in build_form("assetmgmt_tcfd", _snap())}
    assert "Portfolio climate value-at-risk (holdings book)" in secs
    assert "Concentration & diversification" in secs
    assert "Physical-risk exposure by hazard" in secs


def test_am_form_surfaces_var_and_concentration():
    form = build_form("assetmgmt_tcfd", _snap())
    var = next(s for s in form if s["section"].startswith("Portfolio climate"))
    labels = {r["label"] for r in var["rows"]}
    assert "Climate value-at-risk" in labels and "Total portfolio value" in labels
