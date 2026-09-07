"""The independent lens: rebuild cells from points, then split every gap into parts that add up exactly."""
from services.supervision.lens import cell_key, compare, rebuild_cells


def _pts():
    return [{"value_eur": 100, "score": 80, "lat": 1, "country": "ES", "nace": "C"},
            {"value_eur": 100, "score": 10, "lat": 1, "country": "ES", "nace": "C"},
            {"value_eur": 50, "score": 90, "lat": 1, "country": "DE", "nace": "C"},
            {"value_eur": 50, "score": None, "lat": None, "country": "DE", "nace": "C"}]


def test_rebuild_uses_the_platform_bucket_rule_and_counts_coverage():
    cells = rebuild_cells(_pts(), lambda p: p["country"], lambda p: p["nace"])
    es, de = cells[cell_key("ES", "C")], cells[cell_key("DE", "C")]
    assert es["gross_carrying_amount_eur"] == 200 and es["sensitive_physical_eur"] == 100
    assert de["gross_carrying_amount_eur"] == 100 and de["sensitive_physical_eur"] == 50 and de["n_located"] == 1 and de["n_scored"] == 1


def test_gap_split_adds_up_and_flags_the_dominant_reason():
    rebuilt = rebuild_cells(_pts(), lambda p: p["country"], lambda p: p["nace"])
    submitted = {cell_key("ES", "C"): {"geography": "ES", "sector": "C", "gross_carrying_amount_eur": 150, "sensitive_physical_eur": 15},
                 cell_key("FR", "C"): {"geography": "FR", "sector": "C", "gross_carrying_amount_eur": 40, "sensitive_physical_eur": 20}}
    out = compare(submitted, rebuilt)
    by = {c["key"]: c for c in out["cells"]}
    es = by[cell_key("ES", "C")]
    assert sum(es["gap"].values()) == es["rebuilt_sensitive"] - es["submitted_sensitive"] == 85
    assert es["gap"]["scope"] == 5 and es["gap"]["scoring"] == 80 and es["gap"]["basis"] == 0 and es["gap"]["coverage"] == 0
    assert es["flag"] == "question" and "sensitivity share" in es["reason"]
    assert by[cell_key("FR", "C")]["gap"]["unmatched"] == -20 and by[cell_key("DE", "C")]["gap"]["unmatched"] == 50
    assert out["n_flagged"] == 3 and out["total_gap"] == out["totals"]["rebuilt"] - out["totals"]["submitted"]


def test_basis_term_appears_only_when_bases_differ():
    rebuilt_reg = {cell_key("ES", "C"): {"geography": "ES", "sector": "C", "gross_carrying_amount_eur": 200, "sensitive_physical_eur": 120, "n": 2, "n_located": 2, "n_scored": 2}}
    rebuilt_bank = {cell_key("ES", "C"): {**rebuilt_reg[cell_key("ES", "C")], "sensitive_physical_eur": 80}}
    submitted = {cell_key("ES", "C"): {"geography": "ES", "sector": "C", "gross_carrying_amount_eur": 200, "sensitive_physical_eur": 80}}
    same = compare(submitted, rebuilt_reg)["cells"][0]["gap"]
    diff = compare(submitted, rebuilt_reg, rebuilt_bank)["cells"][0]["gap"]
    assert same["basis"] == 0 and same["scoring"] == 40
    assert diff["basis"] == 40 and diff["scoring"] == 0 and sum(diff.values()) == 40


def test_unlocated_exposure_is_unverifiable_not_a_scoring_gap():
    pts = [{"value_eur": 100, "score": 90, "lat": 1, "country": "ES", "nace": "C"},
           {"value_eur": 100, "score": None, "lat": None, "country": "ES", "nace": "C"}]   # half the cell has no region
    rebuilt = rebuild_cells(pts, lambda p: p["country"], lambda p: p["nace"])
    assert rebuilt[cell_key("ES", "C")]["located_value_eur"] == 100
    submitted = {cell_key("ES", "C"): {"geography": "ES", "sector": "C", "gross_carrying_amount_eur": 200, "sensitive_physical_eur": 100}}
    c = compare(submitted, rebuilt)["cells"][0]
    assert c["rebuilt_share_pct"] == 100.0 and c["coverage_pct"] == 50
    assert c["gap"]["coverage"] == -50 and c["gap"]["scoring"] == 50 and sum(c["gap"].values()) == 0
    assert "50% of this exposure located" in c["reason"]
    none_located = compare(submitted, rebuild_cells([{"value_eur": 200, "score": None, "lat": None, "country": "ES", "nace": "C"}], lambda p: p["country"], lambda p: p["nace"]))["cells"][0]
    assert none_located["flag"] == "question" and "cannot be verified" in none_located["reason"] and none_located["gap"]["coverage"] == -100
