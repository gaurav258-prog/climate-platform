"""The insurer climate filing must render a NatCat / underwriting annex (EIOPA · IFRS S2), NOT the
bank located annex (Green Asset Ratio + PCAF financed emissions). Regression for the builder that
routed `insurer_climate` to the bank `_located_annex`. Pure — a synthetic frozen snapshot, no DB."""
from services.governance.filing_annex import _insurer_annex, build_annex

_PAYLOAD = {
    "rollup": {
        "n_policies": 3, "n_priced": 3,
        "total_sum_insured_eur": 100_000_000,
        "total_expected_annual_loss_eur": 4_000_000,
        "total_gross_premium_eur": 6_000_000,
        "portfolio_loss_ratio_pct": 66.7,
        "by_bucket": {
            "VH": {"count": 1, "sum_insured_eur": 40_000_000, "eal_eur": 3_000_000},
            "H": {"count": 1, "sum_insured_eur": 30_000_000, "eal_eur": 900_000},
            "L": {"count": 1, "sum_insured_eur": 30_000_000, "eal_eur": 100_000},
        },
    },
    "by_hazard": {
        "flood": {"exposed_value_eur": 40_000_000, "n_exposed": 1, "max_score": 88.0},
        "wildfire": {"exposed_value_eur": 30_000_000, "n_exposed": 1, "max_score": 72.0},
    },
    "policies": [
        {"headline_bucket": "VH", "sum_insured_eur": 40_000_000, "region": "Andalusia"},
        {"headline_bucket": "H", "sum_insured_eur": 30_000_000, "region": "Valencia"},
        {"headline_bucket": "L", "sum_insured_eur": 30_000_000, "region": "Madrid"},
    ],
}


def _titles(sections):
    return " ".join(s["title"] for s in sections).lower()


def test_insurer_annex_is_natcat_not_bank_gar_pcaf():
    secs = _insurer_annex({}, _PAYLOAD)
    t = _titles(secs)
    # The insurer form is NatCat/underwriting…
    assert "natcat" in t
    assert "sum insured at risk by peril" in t
    # …and must NOT carry the bank located-annex sections.
    assert "green asset ratio" not in t
    assert "financed emissions" not in t
    assert "pcaf" not in t


def test_insurer_annex_surfaces_the_real_figures():
    secs = _insurer_annex({}, _PAYLOAD)
    summary = secs[0]
    # sum insured at risk (High+VH) = 40m + 30m = 70m of 100m = 70.0%
    at_risk_row = summary["rows"][1]["cells"]
    assert at_risk_row[2]["text"] == "70.0%"
    # by-peril section lists both perils, flood first (larger exposure)
    peril_sec = next(s for s in secs if "by peril" in s["title"].lower())
    assert peril_sec["rows"][0]["cells"][0]["text"] == "Flood"
    # by-geography aggregates only High+ policies (Madrid is Low → excluded)
    geo_sec = next(s for s in secs if "geography" in s["title"].lower())
    regions = [r["cells"][0]["text"] for r in geo_sec["rows"]]
    assert "Madrid" not in regions and "Andalusia" in regions


def test_build_annex_routes_insurer_to_insurer_builder():
    out = build_annex("insurer_climate", {}, [], payload=_PAYLOAD)
    assert out is not None
    t = " ".join(s["title"] for s in out["sections"]).lower()
    assert "natcat" in t and "green asset ratio" not in t


def test_insurer_annex_empty_payload_is_safe():
    # No book → the summary template still renders (official rows appear with "—", like the REIT
    # annex), but the data-driven peril/band/geography sections do not, and nothing is fabricated.
    secs = _insurer_annex({}, {})
    assert len(secs) == 1
    assert "natcat" in secs[0]["title"].lower()
    # an unknown total sum insured renders "—", never a fabricated number
    total_si = secs[0]["rows"][0]["cells"]
    assert total_si[1]["text"] == "—"
