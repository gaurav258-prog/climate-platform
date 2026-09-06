"""REIT EU Taxonomy Article 8 KPIs — the invariants that keep it honest and correct."""
from services.governance.reit_taxonomy import art8_kpis


def _props():
    return [
        {"annual_noi_eur": 100, "taxonomy_status": "eligible", "epc_rating": "A", "headline_bucket": "L",
         "taxonomy_reasoning": {"minimum_safeguards_verified": True}},
        {"annual_noi_eur": 100, "taxonomy_status": "eligible", "epc_rating": "D", "headline_bucket": "VH",
         "taxonomy_reasoning": {"minimum_safeguards_verified": False}},
        {"annual_noi_eur": 50, "taxonomy_status": "not_eligible", "epc_rating": None, "headline_bucket": "M",
         "taxonomy_reasoning": {}},
    ]


def test_turnover_eligible_pct_is_noi_weighted():
    k = art8_kpis(_props())["turnover_kpi"]
    assert k["total_eur"] == 250
    elig = next(r for r in k["rows"] if r["row"] == "Taxonomy-eligible turnover")
    assert elig["eur"] == 200 and elig["pct"] == 80.0   # 200 of 250


def test_alignment_is_never_asserted():
    k = art8_kpis(_props())["turnover_kpi"]
    aligned = next(r for r in k["rows"] if r["row"] == "of which Taxonomy-aligned")
    assert aligned["eur"] == 0 and aligned["pct"] == 0.0
    assert "not asserted" in aligned["note"].lower()


def test_alignment_evidence_is_over_eligible_turnover():
    ev = art8_kpis(_props())["turnover_kpi"]["alignment_evidence"]
    # of €200 eligible: €100 EPC A/B, €100 low-hazard (DNSH favourable), €100 safeguards-verified
    assert ev["substantial_contribution_epc_ab_pct"] == 50.0
    assert ev["climate_adaptation_dnsh_favourable_pct"] == 50.0
    assert ev["minimum_safeguards_verified_pct"] == 50.0


def test_capex_opex_declared_not_fabricated():
    k = art8_kpis(_props())
    assert k["capex_kpi"]["status"] == "declared_customer_data"
    assert k["opex_kpi"]["status"] == "declared_customer_data"


def test_empty_book_is_safe():
    k = art8_kpis([])
    assert k["n_properties"] == 0 and k["turnover_kpi"]["total_eur"] == 0
