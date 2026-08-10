"""User-selectable horizon resolver + interpolation (services.intelligence.horizon)."""
from services.intelligence.horizon import resolve, labels_needed, lerp, ANCHOR_LABELS


def test_anchor_labels_resolve_exact():
    for lbl in ANCHOR_LABELS:
        p = resolve(lbl)
        assert p["kind"] == "exact" and p["label"] == lbl and p["interpolated"] is False
        assert labels_needed(p) == [lbl]


def test_year_on_anchor_is_exact():
    for year, lbl in [(2025, "current"), (2030, "2030"), (2050, "2050"), (2100, "2100")]:
        p = resolve(str(year))
        assert p["kind"] == "exact" and p["label"] == lbl and p["interpolated"] is False


def test_intermediate_year_interpolates_between_bracketing_anchors():
    p = resolve("2028")                      # +3y from 2025 → 60% of the way current→2030
    assert p["kind"] == "interp" and p["interpolated"] is True
    assert (p["lo"], p["hi"]) == ("current", "2030")
    assert abs(p["w"] - 0.6) < 1e-9
    assert labels_needed(p) == ["current", "2030"]

    p2 = resolve("2075")                     # midpoint 2050→2100
    assert (p2["lo"], p2["hi"]) == ("2050", "2100") and abs(p2["w"] - 0.5) < 1e-9


def test_out_of_range_clamps_to_nearest_anchor():
    assert resolve("1999")["label"] == "current"
    assert resolve("2200")["label"] == "2100"


def test_junk_and_none_fall_back_to_current():
    assert resolve("junk")["label"] == "current"
    assert resolve(None)["label"] == "current"


def test_lerp_blends_and_tolerates_missing_endpoint():
    assert lerp(40.0, 60.0, 0.5) == 50.0
    assert lerp(40.0, 60.0, 0.0) == 40.0
    assert lerp(40.0, 60.0, 1.0) == 60.0
    assert lerp(None, 60.0, 0.5) == 60.0     # one endpoint missing → the other
    assert lerp(40.0, None, 0.5) == 40.0
