"""The NFIP-claims curve tests (data/reference/loss_protocol.json published_curve_test, corrected 2026-10-23, and
published_curve_test_commercial): a curve is built and tested only from claims inside its countries (E325 — the first
runs took US outlying areas and claims with no state into US curves), the code applies each registration's occupancy
codes and pass rule, a curve that publishes no range passes or fails on its event totals alone, and the event-total
share is stored as the registered words say and counted in whole numbers (E326: 0.67 for 'two thirds' failed 6 of 9)."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from services.loss import claims, curves, measured, published_test, registry
from services.reference import us_areas

OUTSIDE = "outside the curve's countries (a US outlying area: its own country)"
NO_STATE = "no state recorded (the claim cannot be placed in a country)"


@pytest.mark.parametrize("code,country", [("CA", "US"), ("DE", "US"), ("dc", "US"), ("PR", "PR"), ("VI", "VI"),
                                          ("GU", "GU"), ("AS", "AS"), ("MP", "MP"), ("UN", None), ("", None),
                                          (None, None)])
def test_a_postal_state_code_reads_to_its_country_never_to_a_like_named_country(code, country):
    """'CA' is California, not Canada; an outlying area is its own ISO 3166-1 country (ISO 3166-2:US)."""
    assert us_areas.country(code) == country


def test_the_reference_holds_iso_3166_2_us_fifty_states_one_district_six_outlying_areas():
    assert len(us_areas.STATES_AND_DC) == 51 and "DC" in us_areas.STATES_AND_DC
    assert us_areas.OUTLYING_AREAS == {"AS", "GU", "MP", "PR", "UM", "VI"}
    assert not us_areas.STATES_AND_DC & us_areas.OUTLYING_AREAS
    m49 = json.loads((registry.REF / "un_m49_regions.json").read_text(encoding="utf-8"))
    northern_america = m49["regions"]["021"]
    assert "US" in northern_america["countries"] and not us_areas.OUTLYING_AREAS & set(northern_america["countries"])


def _claims_file(tmp_path, monkeypatch):
    rows = [  # state, occupancy, depth (in), damage, value, event
        ("TX", 1, 24, 50_000, 200_000, "A"), ("TX", 11, 12, 10_000, 100_000, "A"), ("PR", 1, 24, 40_000, 80_000, "A"),
        ("VI", 11, 24, 40_000, 80_000, "A"), ("GU", 1, 24, 1_000, 80_000, "A"), ("", 1, 24, 1_000, 80_000, "A"),
        ("UN", 1, 24, 1_000, 80_000, "A"), ("FL", 18, 24, 30_000, 300_000, "A"), ("FL", 17, 24, 3_000, 30_000, "A"),
        ("PR", 6, 24, 30_000, 300_000, "A"),
    ]
    df = pd.DataFrame(rows, columns=["state", "occupancyType", "exteriorWaterDepth", "buildingDamageAmount",
                                     "buildingPropertyValue", "floodEvent"])
    df["damage_ratio"] = df["buildingDamageAmount"] / df["buildingPropertyValue"]
    path = tmp_path / "claims.parquet"
    df.to_parquet(path)
    monkeypatch.setattr(claims, "OUT", path)


def test_claims_outside_the_curves_countries_are_set_aside_and_counted(tmp_path, monkeypatch):
    """E325: a US curve reads the 50 states and DC only; Puerto Rico, the Virgin Islands and Guam are their own
    countries (in the Latin America and Oceania curves' regions), and a claim with no state cannot be placed."""
    _claims_file(tmp_path, monkeypatch)
    df, aside, n = measured._claims(countries=["US"])
    assert n == 10 and len(df) + sum(aside.values()) == n
    assert sorted(df["state"]) == ["TX", "TX"] and set(df["country"]) == {"US"}
    assert aside[NO_STATE] == 2 and aside[OUTSIDE] == 4
    df, aside, _n = measured._claims([4, 6, 18, 19], ["BM", "CA", "GL", "PM", "US"], "non-residential")
    assert list(df["state"]) == ["FL"] and df["occupancyType"].tolist() == [18]
    assert aside["not a non-residential building (FEMA occupancy code)"] == 3      # TX 1, TX 11, FL 17 (mobile home)


def test_the_code_applies_each_registered_rule():
    proto = measured.protocol()
    for key, R in published_test.RULES.items():
        rule = proto[key]
        assert R["curve"] in rule["curve"]
        assert "50 states or the District of Columbia" in (rule.get("claims", "") + json.dumps(rule))
        curve = next(c for f in curves.families().values() for c in f["curves"] if c["key"] == R["curve"])
        assert R["range"] == bool(curve.get("sd"))
    com = proto["published_curve_test_commercial"]
    assert com["occupancy_codes"] == published_test.RULES["published_curve_test_commercial"]["codes"] == [4, 6, 18, 19]
    for code, name in ((4, "'Non-residential building'"), (6, "'Non Residential - Business'"),
                       (18, "'A non-residential building'"), (19, "'a non-residential unit within a multi-unit building'"),
                       (17, "left out")):
        assert f"{code} " in com["claims"] and name in com["claims"]
    assert "alone" in com["pass"] and "not applicable" in com["range"]
    assert "50 states or the District of Columbia" in proto["measured_curves"]["countries"]["rule"]


def test_a_curve_without_a_range_passes_or_fails_on_its_event_totals_alone(monkeypatch):
    curve = {"key": "jrc_huizinga_2017:commercial:021", "countries": ["US"], "spread": "none published",
             "points": [[0.0, 0.0], [1.0, 0.5], [2.0, 1.0]]}
    fam = {"curves": [curve]}
    monkeypatch.setattr(curves, "families", lambda: {"jrc_huizinga_2017": fam})
    depth_in = 1.0 / published_test.INCH                                        # 1 m → ratio 0.5
    rows = []
    for ev, recorded in (("A", 50.0), ("B", 52.0), ("D", 48.0), ("C", 90.0)):  # predicted 50 each: C outside ±30%
        rows += [{"floodEvent": ev, "exteriorWaterDepth": depth_in, "buildingPropertyValue": 100.0 / 500,
                  "buildingDamageAmount": recorded / 500, "damage_ratio": 0.0, "country": "US"}] * 500
    monkeypatch.setattr(measured, "_claims", lambda *_a: (pd.DataFrame(rows), {}, len(rows)))
    r = published_test.test("jrc_huizinga_2017", curve["key"], "published_curve_test_commercial")
    assert r["events_tested"] == 4 and r["events_within_tolerance"] == 3
    assert r["passed"] is True and r["passed_band"] is None and "not applicable" in r["range_test"]
    with pytest.raises(ValueError):                                            # a registration for another curve
        published_test.test("jrc_huizinga_2017", curve["key"], "published_curve_test")


def test_every_recorded_claims_test_read_only_its_curves_countries():
    """The guard on what is recorded (E325): each curve tested on NFIP claims, and the measured family, record the
    countries they read — inside the curve's countries — and count the claims set aside as outside them."""
    fams = curves.families()
    seen = 0
    for key, R in published_test.RULES.items():
        fam_key = R["curve"].split(":")[0]
        curve = next(c for c in fams[fam_key]["curves"] if c["key"] == R["curve"])
        t = curve.get("test") or {}
        if t.get("protocol") != key:
            continue
        seen += 1
        assert set(t["countries"]) <= set(curve["countries"]) and OUTSIDE in t["set_aside"], R["curve"]
    m = fams.get("nfip_measured")
    if m is not None:
        seen += 1
        d = m["derivation"]
        assert d.get("countries") == m["curves"][0]["countries"] == ["US"] and OUTSIDE in d["set_aside"]
    assert seen


WORDS = {"half": (1, 2), "two thirds": (2, 3), "three quarters": (3, 4)}


def test_the_event_share_is_stored_as_its_registered_words_say():
    """E326: the share is a whole-number fraction equal to the statement's words — never a rounded decimal."""
    e = measured.protocol()["test"]["event_total"]
    f = e["share_of_events_required"]
    assert isinstance(f, dict) and all(isinstance(f[k], int) and not isinstance(f[k], bool)
                                        for k in ("numerator", "denominator"))
    said = [w for w in WORDS if f"at least {w} of" in e["statement"]]
    assert len(said) == 1 and WORDS[said[0]] == (f["numerator"], f["denominator"])


@pytest.mark.parametrize("within,events,passes", [(6, 9, True), (5, 9, False), (26, 38, True), (25, 38, False),
                                                  (2, 3, True), (0, 0, False)])
def test_two_thirds_is_counted_in_whole_numbers(within, events, passes):
    assert measured.enough_events(within, events) is passes
