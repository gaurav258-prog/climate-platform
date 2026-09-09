"""The mandate registry is configuration: complete, sector-agnostic, tied to the filing frameworks and the EUR-Lex watch list;
criteria never guess — a missing attribute is 'cannot determine'."""
from datetime import date

from services.governance.filings import FRAMEWORKS
from services.regulatory_monitoring.eurlex_detector import FRAMEWORK_CELEX
from services.supervision.mandates import (
    APPLIES,
    CANNOT,
    NOT_APPLICABLE,
    due_date,
    evaluate,
    mandates_for,
    registry,
)
from services.supervision.profiles import registry as profiles

VALID_SECTORS = {k for k in profiles()["sectors"]}


def test_registry_is_complete_and_consistent():
    reg = registry()
    for m in reg["mandates"]:
        assert set(m["sectors"]) <= VALID_SECTORS, m["id"]
        fw = m["deliverable"].get("framework")
        assert fw is None or fw in FRAMEWORKS, (m["id"], fw)
        assert m["act"]["url"] and m["article"]["excerpt"] and m["article"]["ref"]
        assert m["versions"] and all(v["effective_from"] for v in m["versions"])
        for c in m["criteria"].get("all_of", []) + [c for t in m["criteria"].get("tiers", []) for c in t["all_of"]]:
            assert c["attribute"] in reg["attributes"], (m["id"], c["attribute"])
    # every sector a supervisor can work has at least one binding mandate
    for sec in VALID_SECTORS:
        assert any(m["binding"] for m in mandates_for([sec])), sec


def test_watched_acts_overlap_the_eurlex_detector():
    watched = {c for cs in FRAMEWORK_CELEX.values() for c in cs}
    assert any(c in watched for m in registry()["mandates"] for c in m.get("detection_celex", []))


def test_criteria_never_guess():
    m = next(x for x in registry()["mandates"] if x["id"] == "solvency2_qrt_natcat")
    base = {"sector": {"value": "insurer"}, "jurisdiction": {"value": "DE"}}
    assert evaluate(m, base)["status"] == CANNOT and evaluate(m, base)["missing"] == ["gross_written_premium_eur"]
    assert evaluate(m, {**base, "gross_written_premium_eur": {"value": 12e6}})["status"] == APPLIES
    assert evaluate(m, {**base, "gross_written_premium_eur": {"value": 1e6}})["status"] == NOT_APPLICABLE
    assert evaluate(m, {**base, "jurisdiction": {"value": "US"}, "gross_written_premium_eur": {"value": 12e6}})["status"] == NOT_APPLICABLE


def test_tiers_pick_frequency_and_missing_tier_attribute_is_cannot_determine():
    m = next(x for x in registry()["mandates"] if x["id"] == "crr_449a_pillar3_esg")
    base = {"sector": {"value": "bank"}, "jurisdiction": {"value": "ES"}}
    assert evaluate(m, base)["status"] == CANNOT                                       # tier needs total assets + listed
    big = {**base, "total_assets_eur": {"value": 40e9}, "listed": {"value": True}}
    assert evaluate(m, big)["tier"]["frequency"] == "semiannual"
    small = {**base, "total_assets_eur": {"value": 5e9}, "listed": {"value": False}}
    assert evaluate(m, small)["status"] == APPLIES and evaluate(m, small)["tier"]["frequency"] == "annual"


def test_due_rules():
    m = next(x for x in registry()["mandates"] if x["id"] == "solvency2_qrt_natcat")
    assert due_date(m, date(2025, 12, 31)) == date(2026, 4, 8)
    m = next(x for x in registry()["mandates"] if x["id"] == "sfdr_pai_statement")
    assert due_date(m, date(2025, 12, 31)) == date(2026, 6, 30)
    m = next(x for x in registry()["mandates"] if x["id"] == "crr_449a_pillar3_esg")
    assert due_date(m, date(2025, 12, 31)) == date(2026, 4, 28)
