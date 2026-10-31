"""The filer a test prepares an entity-scoped report for (services.governance.report_filers, E349). A demo organisation
that records its undertakings never files Pillar 3 ESG or its EU Taxonomy KPIs as a whole: Pillar 3 through its group,
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


def taxonomy_filer_in_session(s, org_id: str) -> str:
    """The group, stated to report its EU Taxonomy KPIs for the group for the reporting period (without HTTP) — the filer
    the report's KRI set is then on; while no undertaking states its role, no one files the report (E351)."""
    from services.governance.filings import reporting_period_end
    g = group(s, org_id)
    state_role_in_session(s, org_id, g, reporting_period_end(s, org_id))
    return g


def year_without_roles(s, org_id: str) -> date:
    """A reporting period for which no undertaking of the organisation states its CSRD reporting role, set as the
    organisation's reporting period inside the test's rolled-back transaction: the configured year-end, or the latest
    earlier one with no role stated. A test of the 'no one files this report yet' case builds that case itself, whatever
    roles the demo data states (E352): csrd_reporting_role is append-only, so a stated role is never taken back."""
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, org_id)
    stated = {r[0] for r in s.execute(text("SELECT DISTINCT period_end FROM csrd_reporting_role WHERE org_id = CAST(:o AS uuid)"),
                                      {"o": org_id})}
    while pe in stated:
        pe = pe.replace(year=pe.year - 1)
    s.execute(text("""INSERT INTO org_reporting_settings (org_id, reporting_period_end) VALUES (CAST(:o AS uuid), :pe)
                      ON CONFLICT (org_id) DO UPDATE SET reporting_period_end = EXCLUDED.reporting_period_end"""),
              {"o": org_id, "pe": pe})
    assert reporting_period_end(s, org_id) == pe
    return pe


def state_role_in_session(s, org_id: str, entity_id: str, period_end: date, role: str = "consolidated") -> None:
    """The same, without the HTTP layer: two users of the organisation as maker and checker."""
    from services.governance.csrd_roles import apply_decision, request_role
    users = s.execute(text("SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) ORDER BY email LIMIT 2"),
                      {"o": org_id}).scalars().all()
    req = request_role(s, org_id, users[0], entity_id=entity_id, period_end=period_end, role=role)
    payload = {"entity_id": entity_id, "period_end": period_end.isoformat(), "role": role}
    apply_decision(s, org_id, req["approval_request_id"], payload, "approved", users[1])


def half_year_without_statements(s, org_id: str) -> date:
    """A half-year for which the organisation states no Pillar 3 size class or listing (services.governance.crr_filers),
    set as its reporting period (the first half of the financial year) inside the test's rolled-back transaction: the
    first half of FY2026 — the EBA's module ESGDIS 2.1.0 starts on 31 March 2026 — or the first later one with nothing
    stated. A test of the 'not stated yet' case builds that case itself, whatever the demo data states (E354, as E352's
    year_without_roles does for CSRD roles)."""
    from services.governance.reporting_settings import upsert_reporting_settings
    stated = {r[0] for r in s.execute(text("""SELECT DISTINCT reporting_period_end FROM provided_datapoint
        WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_p3esg'
          AND datapoint_key IN ('large_institution', 'listed_institution')"""), {"o": org_id})}
    h = date(2026, 6, 30)
    while h in stated:
        h = h.replace(year=h.year + 1)
    upsert_reporting_settings(s, org_id, {"reporting_period_end": h.isoformat(), "reporting_period_kind": "half_year"}, None)
    return h
