"""IFRS S2 ¶16(a) — actual incurred NatCat losses: pure rollup + honest-gap invariants."""
from services.governance.ifrs_s2_incurred import summarize_incurred_losses


def _row(peril, ps, pe, gross, net=None):
    return {"loss_id": "x", "period_start": ps, "period_end": pe, "peril": peril,
            "gross_incurred_loss_eur": gross, "net_incurred_loss_eur": net,
            "source": "client", "reported_at": None}


def test_not_yet_supplied_when_no_records():
    r = summarize_incurred_losses([])
    assert r["status"] == "not_yet_supplied"
    assert r["by_peril"] == [] and r["by_period"] == []
    assert "IFRS S2" in r["regulation"] and "16(a)" in r["regulation"]


def test_not_yet_supplied_is_never_a_silent_zero():
    # the honest-gap state must be a distinct status, not a 0 total masquerading as data
    r = summarize_incurred_losses([])
    assert "total_gross_incurred_loss_eur" not in r or r.get("total_gross_incurred_loss_eur") != 0


def test_rollup_by_peril_sums_gross_and_net():
    rows = [_row("flood", "2025-01-01", "2025-12-31", 1_000_000, 800_000),
            _row("flood", "2025-01-01", "2025-12-31", 500_000, None),
            _row("windstorm", "2025-01-01", "2025-12-31", 2_000_000, 1_900_000)]
    r = summarize_incurred_losses(rows)
    assert r["status"] == "supplied"
    assert r["total_gross_incurred_loss_eur"] == 3_500_000
    flood = next(p for p in r["by_peril"] if p["peril"] == "flood")
    assert flood["gross_incurred_loss_eur"] == 1_500_000
    assert flood["net_incurred_loss_eur"] == 800_000     # only the record that supplied net is summed
    assert flood["n_records"] == 2
    windstorm = next(p for p in r["by_peril"] if p["peril"] == "windstorm")
    assert windstorm["net_incurred_loss_eur"] == 1_900_000
    # sorted by gross descending
    assert [p["peril"] for p in r["by_peril"]] == ["windstorm", "flood"]


def test_total_net_none_when_nothing_ever_supplied_net():
    rows = [_row("flood", "2025-01-01", "2025-12-31", 1_000_000, None)]
    r = summarize_incurred_losses(rows)
    assert r["total_net_incurred_loss_eur"] is None
    assert r["by_peril"][0]["net_incurred_loss_eur"] is None


def test_rollup_by_period_groups_across_perils():
    rows = [_row("flood", "2025-01-01", "2025-12-31", 1_000_000),
            _row("windstorm", "2025-01-01", "2025-12-31", 500_000),
            _row("flood", "2024-01-01", "2024-12-31", 300_000)]
    r = summarize_incurred_losses(rows)
    periods = {p["period_start"]: p for p in r["by_period"]}
    assert periods["2025-01-01"]["gross_incurred_loss_eur"] == 1_500_000
    assert set(periods["2025-01-01"]["perils"]) == {"flood", "windstorm"}
    # newest period first
    assert r["by_period"][0]["period_start"] == "2025-01-01"


def test_modeled_figures_surfaced_alongside_when_provided():
    rows = [_row("flood", "2025-01-01", "2025-12-31", 1_000_000)]
    modeled = {"total_expected_annual_loss_eur": 900_000, "standard_formula_natcat_scr_eur": 12_000_000}
    r = summarize_incurred_losses(rows, modeled=modeled)
    assert r["modeled"] == modeled
    assert "comparison_note" in r


def test_modeled_key_present_even_when_none_so_the_section_is_never_dropped():
    r = summarize_incurred_losses([], modeled=None)
    assert "modeled" in r      # key always present, even if the caller has nothing to compare
    r2 = summarize_incurred_losses([_row("flood", "2025-01-01", "2025-12-31", 1)], modeled=None)
    assert "modeled" in r2
