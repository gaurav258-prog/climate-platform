"""The filer a test prepares an entity-scoped report for (services.governance.report_filers, E349). A demo organisation of
two or more reporting entities never files Pillar 3 ESG or its EU Taxonomy KPIs as a whole: Pillar 3 through its group,
on its consolidated situation (CRR Art. 13(1)); the Taxonomy KPIs through each undertaking stated to report for itself or
its group (Directive 2013/34/EU Arts 19a, 29a; Delegated Regulation (EU) 2021/2178 Art. 1(8), (9)).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text


def group(s, org_id: str) -> str:
    """The organisation's group: its top entity with entities below it."""
    return s.execute(text("""
        SELECT e.entity_id::text FROM reporting_entities e
        WHERE e.org_id = CAST(:o AS uuid) AND e.parent_entity_id IS NULL
          AND EXISTS (SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = e.entity_id)
        ORDER BY e.name LIMIT 1"""), {"o": org_id}).scalar_one()


def state_role(api, maker: dict, checker: dict, entity_id: str, period_end: date, role: str = "consolidated", **parent) -> None:
    """The undertaking's reporting role for the year, stated by the maker and approved by the checker (four eyes)."""
    r = api.post("/v1/periods/role", headers=maker, json={"period_end": period_end.isoformat(), "entity_id": entity_id,
                                                          "role": role, **parent})
    assert r.status_code == 202, r.text
    d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                 json={"decision": "approved", "reason": "per the undertaking's management report"})
    assert d.status_code == 200, d.text


def taxonomy_group(api, maker: dict, checker: dict, org_id: str) -> str:
    """The group, stated to report its EU Taxonomy KPIs for the group (Art. 29a) for the reporting period."""
    from services.governance.filings import reporting_period_end
    g = group(api.s, org_id)
    state_role(api, maker, checker, g, reporting_period_end(api.s, org_id))
    return g


def state_role_in_session(s, org_id: str, entity_id: str, period_end: date, role: str = "consolidated") -> None:
    """The same, without the HTTP layer: two users of the organisation as maker and checker."""
    from services.governance.csrd_roles import apply_decision, request_role
    users = s.execute(text("SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) ORDER BY email LIMIT 2"),
                      {"o": org_id}).scalars().all()
    req = request_role(s, org_id, users[0], entity_id=entity_id, period_end=period_end, role=role)
    payload = {"entity_id": entity_id, "period_end": period_end.isoformat(), "role": role}
    apply_decision(s, org_id, req["approval_request_id"], payload, "approved", users[1])
