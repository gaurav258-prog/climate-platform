"""Board pack: the pure rules — summary, last-filing text, statements, and the PDF render with an attestation record."""
from services.governance.board_pack import (
    SECTIONS,
    STATEMENTS,
    _last,
    canonical_json,
    render_pdf,
    sha256,
    summary,
)


def _content():
    return {"pack": {"title": "Board climate-risk pack — Test Bank", "organisation": "Test Bank", "sector": "bank", "period_from": "2026-06-01", "period_to": "2026-09-01",
                     "generated_at": "2026-09-09T10:00:00+00:00", "generated_by": "Mara", "basis": {"scenario": "baseline", "horizon": "current"}, "sections": SECTIONS, "sha256": "abc"},
            "appetite": {"frameworks": [{"framework": "bank_tcfd", "label": "TCFD", "supported": True, "regulator": "EBA",
                                         "kpis": [{"key": "share_at_risk", "label": "Share at risk", "value": 12.5, "fmt": "pct", "status": "amber", "amber": 10, "red": 20, "direction": "higher_worse", "kind": "computed", "hint": None},
                                                  {"key": "ghg", "label": "Financed emissions", "value": None, "fmt": "num", "status": None, "amber": None, "red": None, "direction": None, "kind": "integrated", "hint": None}],
                                         "breaches": 1}, {"framework": "sfdr_pai", "supported": False, "reason": "not in scope"}],
                         "counts": {"indicators": 2, "graded": 1, "red": 0, "amber": 1}, "note": "n"},
            "breaches": {"episodes": [{"framework": "bank_tcfd", "kri_key": "share_at_risk", "label": "Share at risk", "severity": "amber", "direction": "higher_worse", "onset_value": 11.0, "peak_value": 12.5,
                                       "threshold": 10.0, "onset_at": "2026-07-01T00:00:00", "cleared_at": None, "acknowledged_at": None}], "n_open": 1, "n_unacknowledged": 1},
            "filings": {"requirements": [{"framework": "bank_tcfd", "label": "TCFD", "regulator": "EBA", "due_label": "annual", "last_filed": "FY2025 · accepted · 2026-03-01", "n_filings": 1}],
                        "filed_in_period": [], "due_next": [{"framework": "bank_p3esg", "period_label": "FY2026", "due_date": "2026-12-31", "source": "regulation"}], "never_filed": 0},
            "controls": {"readiness": {"passed": 2, "total": 3, "failing": [{"key": "lei", "label": "LEI recorded", "hint": "Add the LEI in Settings."}]}, "exceptions": {"open": 0, "top": []}},
            "decisions": {"n": 0, "n_confirmed": 0, "rows": []},
            "supervision": {"supervisors": [{"regulator": "EU Banking Supervisor", "jurisdiction": "EU/SSM", "acknowledged_at": None, "site_access": False}], "requests": {"n": 0, "open": 0, "overdue": 0, "rows": []}, "remittances": []},
            "regulatory_change": {"n": 0, "rows": [], "note": "n"},
            "models": {"active": [{"hazard": "flood", "version": "v3", "algorithm": "gbm", "r2_oos": 0.52, "status": "active", "approved_by": "x", "activated_at": "2026-01-01T00:00:00"}], "events_in_period": [], "gate": "g"},
            "method": {"engine": "e", "appetite": "a", "attestation": "t", "honesty": "h"}}


def test_summary_counts_what_the_board_asks_first():
    s = summary(_content())
    assert s == {"red": 0, "amber": 1, "indicators": 2, "breaches_open": 1, "never_filed": 0, "due_next": 1, "exceptions_open": 0, "readiness": "2/3",
                 "decisions": 0, "requests_open": 0, "reg_changes": 0, "models_active": 1}


def test_last_filing_is_readable_text():
    assert _last(None) is None
    assert _last({"period_label": "FY2025", "status": "accepted", "updated_at": "2026-03-01T12:00:00"}) == "FY2025 · accepted · 2026-03-01"
    assert _last("FY2024") == "FY2024"


def test_hash_is_canonical_and_statements_fixed():
    c = _content(); assert sha256(c) == sha256({k: c[k] for k in reversed(list(c))}) and canonical_json(c)[:1] == b"{"
    assert set(STATEMENTS) == {"reviewed", "reviewed_with_reservations"}


def test_pdf_renders_with_and_without_attestations():
    plain = render_pdf(_content(), [])
    signed = render_pdf(_content(), [{"full_name": "Pieter", "capacity": "Chair", "statement": "reviewed_with_reservations", "comment": "see minutes", "attested_at": "2026-09-09T21:49:00"}])
    assert plain[:5] == b"%PDF-" and signed[:5] == b"%PDF-" and len(signed) > len(plain) - 500
