"""Regulatory change-detection logic — the parts that must be correct without any network or DB:
change classification (impact mapping), the customer-deadline arithmetic (regression for the
dropped 4-week window), and the document-signature/pick helpers. Pure unit tests."""
from datetime import datetime, timedelta

from services.regulatory_monitoring.change_detector import (
    RegulatoryChangeDetector,
    _doc_signature,
    _pick_latest,
)


def _detector():
    # db is only touched by the DB-backed methods; the pure methods below never use it.
    return RegulatoryChangeDetector(db=None)


def test_doc_signature_is_stable_and_content_sensitive():
    a = {"title": "CSRD amendment", "content": "Article 8 revised"}
    b = {"title": "CSRD amendment", "content": "Article 8 revised"}
    c = {"title": "CSRD amendment", "content": "Article 9 revised"}
    assert _doc_signature(a) == _doc_signature(b)      # same input → same hash
    assert _doc_signature(a) != _doc_signature(c)      # changed content → changed hash


def test_pick_latest_skips_empty_docs():
    assert _pick_latest([]) is None
    assert _pick_latest([{"title": "", "content": ""}, {}]) is None
    got = _pick_latest([{"title": "", "content": ""}, {"title": "Real doc", "content": "x"}])
    assert got["title"] == "Real doc"


def test_classify_change_flags_output_and_processing_from_keywords():
    d = _detector()
    # An XBRL report-format change touches the output layer; a methodology change touches processing.
    out = d.classify_change({"description": "New XBRL submission report format for disclosure"})
    assert out["affects_output"] is True
    assert "regulatory_filings" in out["affected_outputs"]

    proc = d.classify_change({"description": "Revised stress-test calculation methodology"})
    assert proc["affects_processing"] is True
    assert out["effort_hours"] >= 8  # base effort always present


def test_classify_change_empty_description_is_base_only():
    d = _detector()
    out = d.classify_change({})
    assert out["affects_data_model"] is False
    assert out["affects_processing"] is False
    assert out["affects_output"] is False
    assert out["effort_hours"] == 8


def test_customer_deadline_reserves_the_four_week_window():
    """Regression for the dropped `timedelta(weeks=4)`: with ample lead time the release date must
    be the regulatory deadline minus the 4-week implementation window minus the 7-day test buffer
    (35 days total), not the old deadline-minus-7-days."""
    d = _detector()
    deadline = datetime.now() + timedelta(days=200)
    release = d.calculate_customer_deadline(deadline, dev_effort_hours=8)
    assert (deadline - release).days == 35  # 28-day window + 7-day buffer


def test_customer_deadline_releases_immediately_when_time_is_short():
    """If the regulatory deadline is too close to honour the window, release as soon as dev+test
    finishes (a near-future date), never a date in the past before the deadline."""
    d = _detector()
    deadline = datetime.now() + timedelta(days=10)  # inside the 5-week window
    release = d.calculate_customer_deadline(deadline, dev_effort_hours=8)
    # dev+test for 8h effort ≈ 1.5 days out — released promptly, not at deadline-35d (which is in the past)
    assert release > datetime.now()
    assert release < deadline
