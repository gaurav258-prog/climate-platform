"""KRI appetite thresholds — grading a KRI against per-org RAG bands. Requires PostgreSQL."""
import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance.kri import kri
from services.governance import kri_thresholds as KT

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def test_grade_pure():
    hi = {"amber": 15, "red": 30, "direction": "higher_worse"}
    assert KT.grade(10, hi) == "ok"
    assert KT.grade(20, hi) == "amber"
    assert KT.grade(35, hi) == "red"
    lo = {"amber": 80, "red": 60, "direction": "lower_worse"}
    assert KT.grade(90, lo) == "ok"
    assert KT.grade(75, lo) == "amber"
    assert KT.grade(55, lo) == "red"
    assert KT.grade(None, hi) is None
    assert KT.grade(50, None) is None
    assert KT.grade("x", hi) is None      # non-numeric never grades


@pytest.mark.integration
def test_platform_defaults_grade_live_kpis():
    with get_session() as s:
        d = kri(s, BANK_ORG, "bank_tcfd")
        assert d["supported"]
        kb = {k["key"]: k for k in d["kpis"]}
        # the platform default bands must attach to pct_at_risk (higher_worse 15/30) and coverage (lower_worse 80/60)
        assert kb["pct_at_risk"].get("amber") == 15 and kb["pct_at_risk"].get("direction") == "higher_worse"
        assert kb["coverage"].get("direction") == "lower_worse"
        # ungraded KRIs (no band) carry no status
        assert kb["total_value"].get("status") is None
        assert "breaches" in d
        s.rollback()


@pytest.mark.integration
def test_org_override_beats_default_and_regrades():
    with get_session() as s:
        # force an org band that a healthy coverage still trips → red, proving the override is applied
        KT.set_threshold(s, BANK_ORG, None, "bank_tcfd", "pct_at_risk", {"amber": 1, "red": 2, "direction": "higher_worse"})
        d = kri(s, BANK_ORG, "bank_tcfd")
        p = next(k for k in d["kpis"] if k["key"] == "pct_at_risk")
        assert p["amber"] == 1 and p["red"] == 2
        assert p["status"] == "red" and p["breached"] is True and d["breaches"] >= 1
        # clearing both edges leaves the KRI ungraded again
        KT.set_threshold(s, BANK_ORG, None, "bank_tcfd", "pct_at_risk", {"amber": None, "red": None})
        d2 = kri(s, BANK_ORG, "bank_tcfd")
        p2 = next(k for k in d2["kpis"] if k["key"] == "pct_at_risk")
        assert p2.get("status") is None
        s.rollback()
