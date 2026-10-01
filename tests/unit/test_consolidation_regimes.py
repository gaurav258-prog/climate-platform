"""A group filing consolidates by the rule of the text that governs it — never a switch or a platform default (E75).
data/reference/consolidation/regimes.json declares, per framework, the regime and quotes it."""
from __future__ import annotations

import pytest

from services.governance.entities import consolidation_regimes, regime_for

REG = consolidation_regimes()


def test_every_group_framework_is_governed_by_a_declared_regime():
    from services.governance.filings import GROUP_FRAMEWORKS
    assert set(REG["frameworks"]) == GROUP_FRAMEWORKS          # no rule for a framework that never reads one
    for fw in GROUP_FRAMEWORKS:
        assert REG["regimes"][regime_for(fw)]["refs"], fw
    with pytest.raises(ValueError, match="no consolidation regime"):
        regime_for("no_such_framework")


def test_every_regime_has_the_three_methods_and_quotes():
    for name, r in REG["regimes"].items():
        assert set(r["factors"]) == {"full", "proportional", "equity"}, name
        assert set(r["factors"].values()) <= {"full", "proportional", "excluded"}, name
        assert r["refs"] and all(x["ref"] and x["quote"] for x in r["refs"]), name


def test_the_platform_offers_no_equity_switch():
    from services.calc_settings import INTERPRETATION_SCHEMA
    assert "equity_consolidation" not in INTERPRETATION_SCHEMA


def test_every_quote_is_in_the_official_texts():
    """Word for word in the stored official texts (data/sources/legal) — checked on every run."""
    from services.reference import legal_texts
    missing = [x["ref"] for r in REG["regimes"].values() for x in r["refs"] if not legal_texts.contains(x["quote"])]
    assert not missing, missing


def test_the_rule_file_passes_its_own_sign_off_checks():
    """What the engineering sign-off requires (services.regspec.rules.check) holds for the file as committed."""
    from services.regspec import rules
    assert rules.check(REG) == []


def test_the_check_names_each_kind_of_problem():
    import copy

    from services.regspec import rules
    bad = copy.deepcopy(REG)
    bad["frameworks"]["bank_tcfd"]["declaration"]["reading"] = ""
    bad["frameworks"]["bank_p3esg"]["refs"] = ["ESRS 1 §62"]
    bad["frameworks"]["bank_p3esg"]["declaration"] = {"reading": "x", "declared_by": "x", "declared": "2026-01-01"}
    bad["regimes"]["crr_prudential"]["refs"][0]["quote"] = "a sentence no act contains"
    del bad["frameworks"]["reit_taxonomy"]
    errs = " | ".join(rules.check(bad))
    for part in ("bank_tcfd: a declared reading needs", "bank_p3esg: cites a ref", "bank_p3esg: a rule set by the text",
                 "not found word for word", "reit_taxonomy: can be filed for a group but has no consolidation rule"):
        assert part in errs, part


def test_a_declared_reading_carries_no_confirmation_of_its_own():
    """Confirmation is the file's sign-off on the change route, never a field someone types into the file."""
    for fw, e in REG["frameworks"].items():
        if e["basis"] == "declared":
            assert set(e["declaration"]) == {"declared_by", "declared", "reading"}, fw
