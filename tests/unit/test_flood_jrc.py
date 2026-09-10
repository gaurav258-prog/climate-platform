"""Flood v3 — JRC river-flood maps: cited depth–damage curve, tile naming, score shape."""
from ml.scoring.flood_jrc import damage_fraction, flood_score, tile_name


def test_depth_damage_is_the_cited_huizinga_curve():
    assert damage_fraction(0.0) == 0.0 and damage_fraction(0.5) == 0.25 and damage_fraction(2.0) == 0.6
    assert damage_fraction(6.0) == 1.0 and damage_fraction(9.0) == 1.0
    assert abs(damage_fraction(0.25) - 0.125) < 1e-9          # linear between points


def test_score_is_floodplain_share_weighted_by_damage():
    assert flood_score(1.0, 2.0) == 60.0 and flood_score(0.5, 2.0) == 30.0 and flood_score(0.0, 5.0) == 0.0
    assert flood_score(1.0, 0.0) == 0.0                       # inundated share with no depth: nothing to damage


def test_tile_names_use_the_top_left_corner_and_w0_for_the_zero_column():
    assert tile_name(45.0, -95.0) == "N50_W100" and tile_name(48.8, 2.3) == "N50_W0"
    assert tile_name(51.5, -0.1) == "N60_W10" and tile_name(-33.9, 151.2) == "S30_E150"
