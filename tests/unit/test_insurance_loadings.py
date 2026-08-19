"""Insurance expense/profit loadings are institution interpretation switches — they load the gross premium
and default to the shipped 0.25 / 0.05. Pure — no DB."""
from ml.scoring.insurance_pricing import price_policy


def test_default_loadings_reproduce_shipped_premium():
    d = price_policy(80, 10_000_000, hazard="flood")
    # gross = EAL / (1 - 0.25 - 0.05) = EAL / 0.70
    assert abs(d["gross_premium_eur"] - d["expected_annual_loss_eur"] / 0.70) < 1.0


def test_higher_expense_ratio_raises_the_premium():
    base = price_policy(80, 10_000_000, hazard="flood")
    loaded = price_policy(80, 10_000_000, hazard="flood", expense_ratio=0.35, profit_margin=0.05)
    assert loaded["gross_premium_eur"] > base["gross_premium_eur"]
    # same EAL underneath — only the loading changed
    assert abs(loaded["expected_annual_loss_eur"] - base["expected_annual_loss_eur"]) < 1.0


def test_degenerate_total_load_is_guarded():
    # expense+profit ≥ 1.0 would divide by ≤0; the floor keeps the premium finite
    d = price_policy(80, 10_000_000, hazard="flood", expense_ratio=0.8, profit_margin=0.5)
    assert d["gross_premium_eur"] > 0 and d["gross_premium_eur"] < float("inf")
