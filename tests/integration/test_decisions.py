"""Forward-risk decisions — crossings, record, audit log. Requires PostgreSQL."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
import services.intelligence.forward_decisions as D

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _actor(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


@pytest.mark.integration
def test_crossings_and_decision_flow():
    with get_session() as s:
        rows = D.crossings(s, BANK_ORG, "banking", "hot_house_3_5c", "2100")
        assert isinstance(rows, list)
        if not rows:
            pytest.skip("no crossings in this demo book for the chosen pathway")
        c = rows[0]
        # every crossing genuinely crosses the line: below High today (or unseen), High+ at the horizon
        assert c["future_score"] >= D.AT_RISK
        assert c["current_score"] is None or c["current_score"] < D.AT_RISK
        assert c["decision"] is None
        maker = _actor(s)
        checker = str(s.execute(text("SELECT user_id FROM users WHERE email='approver@meridian.demo'")).scalar())
        # propose — the decision is 'proposed' pending a second approval
        r = D.decide(s, BANK_ORG, maker, entity_id=c["entity_id"], entity_name=c["entity_name"],
                     scenario="hot_house_3_5c", horizon="2100", action="engage", rationale="test")
        assert r["status"] == "proposed" and r["approval_request_id"]
        hit = next(x for x in D.crossings(s, BANK_ORG, "banking", "hot_house_3_5c", "2100") if x["entity_id"] == c["entity_id"])
        assert hit["decision"]["status"] == "proposed"
        # approve via the same path the approvals router calls → standing + a Kanban card spun (engage is actionable)
        payload = s.execute(text("SELECT payload FROM approval_requests WHERE request_id=:r"), {"r": r["approval_request_id"]}).scalar()
        applied = D.apply_decision(s, BANK_ORG, payload, "approved", checker)
        assert applied["status"] == "approved" and applied["task_id"]
        card = s.execute(text("SELECT source, criticality FROM regulatory_task WHERE task_id=:t"), {"t": applied["task_id"]}).mappings().first()
        assert card["source"] == "decision"
        hit2 = next(x for x in D.crossings(s, BANK_ORG, "banking", "hot_house_3_5c", "2100") if x["entity_id"] == c["entity_id"])
        assert hit2["decision"]["status"] == "approved"
        s.rollback()


@pytest.mark.integration
def test_invalid_action_and_horizon_refused():
    with get_session() as s:
        u = _actor(s)
        with pytest.raises(D.DecisionError):
            D.decide(s, BANK_ORG, u, entity_id="00000000-0000-0000-0000-000000000000", entity_name=None,
                     scenario="disorderly_2c", horizon="2050", action="nonsense", rationale=None)
        with pytest.raises(D.DecisionError):
            D.crossings(s, BANK_ORG, "banking", "disorderly_2c", "current")
        s.rollback()
