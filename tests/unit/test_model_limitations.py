"""The limitations registry must formally track the two data-bound gaps we set out to close (water-management,
regional sea-level / subsidence), each with a resolved status, evidence, and an unlock feed — never a vague TODO."""
from __future__ import annotations

from ml.scoring.model_limitations import model_limitations


def _by_id():
    return {it["id"]: it for it in model_limitations()["items"]}


def test_water_management_is_closed_as_tested_rejected():
    w = _by_id()["water_management"]
    assert w["status"] == "tested_rejected"
    assert "LOO" in w["evidence"] and "r²" in w["evidence"]          # the numbers travel with it
    assert w["unlock"] and "0.40" in w["unlock"]                     # the bar it must clear to be wired
    assert w["current_treatment"]                                    # how it's handled honestly today


def test_regional_slr_and_subsidence_are_deferred_with_named_feeds():
    b = _by_id()
    for gid, feed in (("regional_sea_level", "AR6 regional"), ("land_subsidence", "EGMS")):
        it = b[gid]
        assert it["status"] == "deferred_needs_data"
        assert feed in it["unlock"]                                  # names the authoritative feed
        assert it["current_treatment"]                              # states the conservative interim


def test_every_limitation_has_the_required_honesty_fields():
    for it in model_limitations()["items"]:
        for field in ("id", "area", "status", "title", "summary", "evidence", "current_treatment", "unlock"):
            assert it.get(field), f"{it.get('id')} missing {field}"
        assert it["status"] in ("tested_rejected", "deferred_needs_data", "disclosed_scope")


def test_counts_match_items():
    m = model_limitations()
    assert m["n_limitations"] == len(m["items"])
    assert sum(m["counts"].values()) == m["n_limitations"]
