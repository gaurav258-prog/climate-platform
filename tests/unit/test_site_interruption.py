"""Business interruption at own sites on the company's stated downtime share (E69): no curve of the platform's own;
an unstated share is a named gap and the total over it a gap; no throughput / no score is not assessed. Pure."""
from datetime import date

from services.intelligence.site_interruption import bi_at_risk, sites_bi
from services.money.params import Method

STATED = {("method.bi_downtime_share", "any/H"): 0.03, ("method.bi_downtime_share", "flood/VH"): 0.08}


def _m(v=STATED):
    return Method.of(v, date(2025, 12, 31))


def test_the_share_is_the_perils_own_else_any_by_band():
    assert bi_at_risk(_m(), 1_000_000, "flood", 80)["bi_at_risk_eur"] == 80_000          # flood/VH stated
    assert bi_at_risk(_m(), 1_000_000, "drought", 60)["bi_at_risk_eur"] == 30_000        # any/H
    assert "method.bi_downtime_share (drought/VH)" in bi_at_risk(_m(), 1_000_000, "drought", 80)["gap"]


def test_not_assessed_is_not_a_zero_and_a_gap_makes_the_total_a_gap():
    assert bi_at_risk(_m(), None, "flood", 80) == {"bi_at_risk_eur": None, "reason": "no_throughput"}
    assert bi_at_risk(_m(), 1e6, None, None)["reason"] == "unscored"
    sites = [{"throughput_eur": 1e6, "top_hazard": "flood", "hazard_score": 80},
             {"throughput_eur": 1e6, "top_hazard": "drought", "hazard_score": 60}]
    assert sites_bi(_m(), sites) == {"bi_at_risk_eur": 110_000}
    sites.append({"throughput_eur": 1e6, "top_hazard": "wildfire", "hazard_score": 90})
    out = sites_bi(_m(), sites)
    assert out["bi_at_risk_eur"] is None and "wildfire/VH" in out["gap"] and sites[2]["bi_gap"]
