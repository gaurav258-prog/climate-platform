"""GRC follow-ups: change links come only from configuration; shares expire/revoke/exhaust in order; third-party kinds and CSV."""
from datetime import datetime, timedelta, timezone

from services.governance.assurance_share import status_of
from services.governance.reg_impact_links import links_for, summary_text
from services.intelligence.third_parties import CRITICALITY, KINDS, register_csv


def test_links_are_declared_not_inferred():
    L = links_for("insurer_climate", "insurer")
    assert {s["key"] for s in L["switches"]} == {"pml_return_period", "equity_consolidation"}
    assert L["kris"] and L["template"] and L["template"]["official_form"] and L["n"] >= 5
    assert links_for("insurer_climate", "bank")["switches"] == [{"key": "equity_consolidation", "label": "Equity-method consolidation treatment", "sectors": None}]
    assert links_for("no_such_framework")["n"] == 0
    assert summary_text("bank_tcfd", "bank").startswith("Touches — ") and summary_text("no_such_framework", None).startswith("Touches nothing")


def test_share_status_precedence():
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    base = {"revoked_at": None, "expires_at": now + timedelta(days=1), "max_downloads": None, "n_downloads": 0}
    assert status_of(base, now) == "active"
    assert status_of({**base, "expires_at": now}, now) == "expired"
    assert status_of({**base, "max_downloads": 1, "n_downloads": 1}, now) == "exhausted"
    assert status_of({**base, "revoked_at": now, "expires_at": now}, now) == "revoked"


def test_third_party_registry_and_csv():
    assert "critical_service_provider" in KINDS and CRITICALITY == ("critical", "important", "standard")
    v = {"third_parties": [{"name": "DC", "kind_label": "Data centre", "service": None, "criticality": "critical", "address": None, "country": "DE", "latitude": 50.1, "longitude": 8.7, "h3_cell": "88x", "geocode_precision": "exact",
                            "contract_ref": None, "worst_hazard": None, "max_score": None, "bucket": None, "n_hazards_scored": 0, "created_at": "2026-09-09T20:00:00", "created_by": "Mara"}]}
    lines = register_csv(v).decode("utf-8").splitlines()
    assert len(lines) == 2 and "pending" in lines[1]
