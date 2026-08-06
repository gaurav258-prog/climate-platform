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
        # turn ON 4-eyes for this org (default is OFF — a customer choice), then propose
        s.execute(text("""INSERT INTO approval_policy (org_id, action_key, requires_approval, threshold_eur)
                          VALUES (:o,'risk.decision',TRUE,NULL)
                          ON CONFLICT (org_id, action_key) WHERE org_id IS NOT NULL
                          DO UPDATE SET requires_approval=TRUE, threshold_eur=NULL"""), {"o": BANK_ORG})
        r = D.decide(s, BANK_ORG, maker, entity_id=c["entity_id"], entity_name=c["entity_name"],
                     scenario="hot_house_3_5c", horizon="2100", action="engage", rationale="test", value_eur=c["value_eur"])
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
def test_four_eyes_policy_is_configurable():
    """Off (default) → the decision is approved on the spot + a card spins. On with a threshold → only
    exposures above the line need a second approval."""
    with get_session() as s:
        rows = D.crossings(s, BANK_ORG, "banking", "hot_house_3_5c", "2100")
        if not rows:
            pytest.skip("no crossings")
        c = rows[0]
        maker = _actor(s)
        _pol = lambda req, thr: s.execute(text("""
            INSERT INTO approval_policy (org_id, action_key, requires_approval, threshold_eur)
            VALUES (:o,'risk.decision',:r,:t)
            ON CONFLICT (org_id, action_key) WHERE org_id IS NOT NULL
            DO UPDATE SET requires_approval=:r, threshold_eur=:t"""), {"o": BANK_ORG, "r": req, "t": thr})
        propose = lambda: D.decide(s, BANK_ORG, maker, entity_id=c["entity_id"], entity_name=c["entity_name"],
                                   scenario="hot_house_3_5c", horizon="2100", action="engage", rationale="t",
                                   value_eur=c["value_eur"])
        _pol(False, None); a = propose()
        assert a["status"] == "approved" and a["task_id"]                      # off → applied directly
        _pol(True, (c["value_eur"] or 0) + 1e9); b = propose()
        assert b["status"] == "approved"                                       # on, below the threshold → direct
        _pol(True, 0); d = propose()
        assert d["status"] == "proposed"                                       # on, above the threshold → 4-eyes
        s.rollback()


@pytest.mark.integration
def test_playbook_routes_task_and_notifies():
    """The decision playbook drives what happens on approval: the spun card is auto-assigned + given a due
    date, and a notify email is queued to the owner."""
    with get_session() as s:
        rows = D.crossings(s, BANK_ORG, "banking", "hot_house_3_5c", "2100")
        if not rows:
            pytest.skip("no crossings")
        c = rows[0]
        maker = _actor(s)
        analyst = str(s.execute(text("SELECT user_id FROM users WHERE email='analyst@meridian.demo'")).scalar())
        # 4-eyes OFF so the decision auto-approves and runs the playbook inline; configure engage
        s.execute(text("""INSERT INTO approval_policy (org_id, action_key, requires_approval)
                          VALUES (:o,'risk.decision',FALSE)
                          ON CONFLICT (org_id, action_key) WHERE org_id IS NOT NULL DO UPDATE SET requires_approval=FALSE"""), {"o": BANK_ORG})
        D.set_playbook(s, BANK_ORG, maker, "engage", {"spin_task": True, "assignee_user_id": analyst, "due_days": 7, "notify": True})
        r = D.decide(s, BANK_ORG, maker, entity_id=c["entity_id"], entity_name=c["entity_name"],
                     scenario="hot_house_3_5c", horizon="2100", action="engage", rationale="t", value_eur=c["value_eur"])
        assert r["status"] == "approved" and r["task_id"]
        t = s.execute(text("SELECT assignee_user_id::text, due_date FROM regulatory_task WHERE task_id=:t"), {"t": r["task_id"]}).mappings().first()
        assert t["assignee_user_id"] == analyst and t["due_date"] is not None
        em = s.execute(text("SELECT to_email FROM email_outbox WHERE kind='decision' ORDER BY created_at DESC LIMIT 1")).scalar()
        assert em == "analyst@meridian.demo"
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
