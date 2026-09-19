from __future__ import annotations

import numpy as np

from services.validation.validators import parametric_replay as P

SQ = [(0, 0), (1, 0), (1, 1), (0, 1)]


def test_payout_pct_steps():
    assert P.payout_pct(930, 920, 900) == 0.0
    assert P.payout_pct(920, 920, 900) == 0.3
    assert P.payout_pct(910, 920, 900) == 0.3 + 0.7 * 0.5
    assert P.payout_pct(900, 920, 900) == 1.0 and P.payout_pct(880, 920, 900) == 1.0


def test_clip_segment_cases():
    assert P.clip_segment((-1, 0.5), (2, 0.5), SQ) == (1 / 3, 2 / 3)
    assert P.clip_segment((-1, 2), (2, 2), SQ) is None
    assert P.clip_segment((0.2, 0.2), (0.4, 0.4), SQ) == (0.0, 1.0)
    assert P.clip_segment((0.2, 0.2), (0.4, 0.4), list(reversed(SQ))) == (0.0, 1.0)  # orientation-free


def test_ccp_interpolates_at_entry():
    trk = [(-1.0, 0.5, 1000.0), (2.0, 0.5, 940.0)]      # enters at t=1/3 (p=980), exits t=2/3 (p=960)
    assert abs(P.calculated_central_pressure(trk, SQ) - 960.0) < 1e-9
    assert P.calculated_central_pressure([(5, 5, 900.0), (6, 5, 900.0)], SQ) is None


def test_payout_rate_sums_and_caps():
    subs = [{"id": 1, "poly": SQ, "min1": 950.0, "min2": 900.0},
            {"id": 2, "poly": [(1, 0), (2, 0), (2, 1), (1, 1)], "min1": 950.0, "min2": 900.0}]
    trk = [(0.5, 0.5, 940.0), (1.5, 0.5, 940.0)]
    r = P.payout_rate(trk, subs)
    assert abs(r - min(1.0, 2 * (0.3 + 0.7 * 10 / 50))) < 1e-9
    assert P.payout_rate([(0.5, 0.5, 890.0), (1.5, 0.5, 890.0)], subs) == 1.0


def test_build_subareas_triangle_vs_bbox():
    raw = [{"subarea": 10, "approx_bbox_lon_min": 0, "approx_bbox_lon_max": 1, "approx_bbox_lat_min": 0,
            "approx_bbox_lat_max": 1, "min_cp1_hPa": 920, "min_cp2_hPa": 900}]
    assert len(P.build_subareas(raw)[0]["poly"]) == 3
    assert len(P.build_subareas(raw, triangles=False)[0]["poly"]) == 4
    assert P.build_subareas(raw, shift=(0.5, 0))[0]["poly"][0][0] == 0.5


def test_auc_and_poisson_and_perm():
    assert P.auc_binary([3, 4, 1, 2], [1, 1, 0, 0]) == 1.0
    assert P.auc_binary([1, 1], [1, 0]) == 0.5 and P.auc_binary([1, 2], [1, 1]) is None
    lo, hi = P.poisson_ci(1, 46)
    assert lo < 1 / 46 < hi
    x = np.arange(12.0)
    assert P.perm_p_spearman(x, x, 2000) < 0.01


def test_member_normalisation_and_totals():
    assert P.normalise_member("Excess Rainfall policy - Barbados") is None
    assert P.normalise_member("Tropical Cyclone policy - The Bahamas") == "Bahamas"
    assert P.normalise_member("St Vincent & the Grenadines") == "Saint Vincent and the Grenadines"
    rows = [{"hazard": "tropical_cyclone", "table_idx": "0", "member": "Jamaica", "payout_usd": "10"},
            {"hazard": "tropical_cyclone", "table_idx": "0", "member": "Excess Rainfall - Jamaica", "payout_usd": "5"},
            {"hazard": "tropical_cyclone", "table_idx": "1", "member": "Jamaica", "payout_usd": "7"}]
    assert P.cumulative_tc_payouts(rows) == {"Jamaica": 10.0}
