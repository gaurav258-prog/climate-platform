"""A KRI set of a report with filer rules is on one filer's book (E351), end to end through the HTTP API, inside one
rolled-back transaction:

  default   the board opens on the report at the head of the group, on its consolidated figures (Pillar 3: "at the
            highest level of consolidation in the EU", EBA Q&A 2023_6708); another filer is chosen by name
  equal     a KRI for a filer's scope equals the figure that filer's filing printed — bank (Pillar 3 Template 5, EU
            Taxonomy GAR), insurer (modelled 1-in-200), REIT (Taxonomy-eligible turnover)
  trend     the filed history holds that filer's filings only
  drills    each drill-down sums to the figure it explains, on the same book
  gaps      no filer for the year, or a filer that is none, is a notice — never the whole book
  unchanged an organisation with one reporting entity keeps the whole book and every filing
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.governance import kri_t5
from tests.integration.conftest import login as _login
from tests.integration.filers import group, state_role_in_session, year_without_roles
from tests.integration.money_method import state_method
from tests.integration.test_e2e_s2701 import IBERIA, IBERIA_RE, _users
from tests.integration.test_intake_pipeline import BANK_ORG
from tests.integration.test_pillar3_report import _new_filing, _payload

pytestmark = pytest.mark.integration
KRI = "/v1/reg-tasks/kri"


def _entity(s, org_id: str, name: str) -> str:
    return s.execute(text("SELECT entity_id::text FROM reporting_entities WHERE org_id = CAST(:o AS uuid) AND name = :n"),
                     {"o": org_id, "n": name}).scalar_one()


def _file(api, maker, framework: str, entity_id: str, role: str | None = None) -> str:
    """A new filing of the report for the scope (a live one of the same entity set aside first)."""
    api.s.execute(text("""UPDATE regulatory_filing SET status = 'superseded' WHERE framework = :fw
                          AND entity_id = CAST(:e AS uuid) AND status NOT IN ('superseded', 'withdrawn')"""),
                  {"fw": framework, "e": entity_id})
    q = f"&filing_role={role}" if role else ""
    pf = api.get(f"/v1/filings/preflight?framework={framework}&entity_id={entity_id}{q}", headers=maker).json()
    g = api.post("/v1/filings", headers=maker, json={"framework": framework, "confirm_token": pf["confirm_token"],
                                                     "entity_id": entity_id, **({"filing_role": role} if role else {})})
    assert g.status_code == 201, g.text
    return g.json()["filing_id"]


def _scopes(s, ids: list[str]) -> set[tuple]:
    return set(s.execute(text("""SELECT entity_id::text, filing_role FROM regulatory_filing
                                 WHERE filing_id = ANY(CAST(:ids AS uuid[]))"""), {"ids": ids}).all())


def _figure(h: dict, key: str):
    return next((f["value"] for f in h.get("figures") or [] if f["key"] == key), None)


def test_pillar3_kris_are_the_groups_and_equal_its_filing(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    s = api.s
    fid = _new_filing(api, maker)
    grp, p = group(s, BANK_ORG), _payload(s, fid)
    r = api.get(f"{KRI}?framework=bank_p3esg", headers=maker).json()
    assert r["supported"] and r["filer"] == {"entity_id": grp, "name": "Meridian Financial Group", "role": "consolidated",
                                             "label": "Meridian Financial Group (group)", "default": True}
    # the only filer: no subsidiary is stated a large institution — so no other filer is offered
    assert len(r["filers"]) == 1 and r["basis"]["filer"]["code"] == "kri.filer.scope.head_alone"
    assert "highest level of consolidation" in r["scope"]["detail"]["why"]
    # the live book is the group's consolidated one — Meridian Leasing at 60 % — not every entity in full
    kpi = {k["key"]: k for k in r["kpis"]}
    assert kpi["total_value"]["value"] == pytest.approx(p["rollup"]["total_value_eur"], abs=1)
    from services.governance.kri import _live_snapshot
    from services.governance.reporting_settings import get_settings
    st = get_settings(s, BANK_ORG)
    whole = _live_snapshot(s, BANK_ORG, "bank_p3esg", st["scenario"], st["horizon"])
    assert whole["rollup"]["total_value_eur"] > kpi["total_value"]["value"] + 1
    # every Template 5 KRI equals the cell the group's filing printed
    h = next(x for x in r["history"] if x["filing_id"] == fid)
    rows = [k for k in r["kpis"] if k.get("group") == kri_t5.GROUP]
    assert rows and any(k["value"] for k in rows)
    assert {k["key"]: k["value"] for k in rows} == {f["key"]: f["value"] for f in h["figures"] if f.get("group") == kri_t5.GROUP}
    # the trend: the group's filings only — never the whole organisation's or a subsidiary's
    assert _scopes(s, [x["filing_id"] for x in r["history"]]) <= {(grp, "consolidated"), (grp, None)}


def test_the_drill_downs_sum_to_the_figure_they_explain(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    s = api.s
    p = _payload(s, _new_filing(api, maker))
    book = [a for a in p["assets"] if (a.get("value_eur") or 0) > 0]
    r = api.get(f"{KRI}?framework=bank_p3esg", headers=maker).json()
    kpi = {k["key"]: k for k in r["kpis"]}

    cov = api.get(f"{KRI}/detail?framework=bank_p3esg&kri=coverage", headers=maker).json()["composition"]
    assert sum(i["value"] for i in cov["items"]) == p["rollup"]["n_assets"]               # scored + not yet scored
    drv = api.get(f"{KRI}/detail?framework=bank_p3esg&kri=total_value", headers=maker).json()["drivers"]
    assert drv["total_count"] == len(book)
    top = max(r["by_hazard"], key=lambda h: h["value"])
    ents = api.get(f"{KRI}/hazard?framework=bank_p3esg&hazard={top['hazard']}", headers=maker).json()["entities"]
    if len(ents) < 100:                                                            # the drill lists 100 at most
        assert sum(e["value"] or 0 for e in ents) == pytest.approx(top["value"], rel=1e-9, abs=1)
    fwd = api.get(f"{KRI}/detail?framework=bank_p3esg&kri=forward_share", headers=maker).json()
    if kpi["forward_share"]["value"] is not None:
        assert fwd["composition"]["items"][-1]["value"] == kpi["forward_share"]["value"]
        assert fwd["projection"]["points"][-1]["value"] == kpi["forward_share"]["value"]
    # a figure the engine computes for the whole organisation only is a gap on one filer's figures, never a number
    el = kpi["expected_loss"]
    assert el["value"] is None and el["missing"]["code"] == "kri.filer.whole_book_only"


def test_a_chosen_filer_has_its_own_figures_and_filings(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    s = api.s
    pe = year_without_roles(s, BANK_ORG)
    state_method(s, BANK_ORG, pe)
    # no undertaking states its reporting role for the year: no one files the EU Taxonomy KPIs — said, not the whole book
    r = api.get(f"{KRI}?framework=bank_tcfd", headers=maker).json()
    assert not r["supported"] and r["notice"]["code"] == "kri.filer.none" and "kpis" not in r
    grp, ag = group(s, BANK_ORG), _entity(s, BANK_ORG, "Meridian Bank AG")
    state_role_in_session(s, BANK_ORG, grp, pe)
    state_role_in_session(s, BANK_ORG, ag, pe, "individual")
    r = api.get(f"{KRI}?framework=bank_tcfd", headers=maker).json()
    assert r["filer"]["entity_id"] == grp and [f["label"] for f in r["filers"]] == ["Meridian Bank AG", "Meridian Financial Group (group)"]
    assert r["basis"]["filer"]["code"] == "kri.filer.scope.head" and r["scope"]["detail"]["next"]

    fid = _file(api, maker, "bank_tcfd", ag)
    mine = api.get(f"{KRI}?framework=bank_tcfd&entity_id={ag}", headers=maker).json()
    assert mine["filer"]["entity_id"] == ag and not mine["filer"]["default"]
    assert mine["basis"]["filer"]["code"] == "kri.filer.scope.chosen"
    h = next(x for x in mine["history"] if x["filing_id"] == fid)
    for key in ("gar", "gar_capex", "gar_coverage"):                     # the live KPI equals the one its filing printed
        live = next(k for k in mine["kpis"] if k["key"] == key)["value"]
        assert live == _figure(h, key), key
    assert _scopes(s, [x["filing_id"] for x in mine["history"]]) <= {(ag, "solo"), (ag, None)}
    assert fid not in {x["filing_id"] for x in r["history"]}                     # the group's trend holds none of it
    # a drill reads the chosen filer's book
    drv = api.get(f"{KRI}/detail?framework=bank_tcfd&kri=total_value&entity_id={ag}", headers=maker).json()["drivers"]
    n_ag = s.execute(text("""SELECT count(*) FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND vertical = 'banking'
                             AND reporting_entity_id = CAST(:e AS uuid) AND primary_value_eur > 0"""),
                     {"o": BANK_ORG, "e": ag}).scalar()
    assert drv["total_count"] == n_ag
    # an entity that files no EU Taxonomy KPIs for the year is no filer to show
    leasing = _entity(s, BANK_ORG, "Meridian Leasing GmbH")
    nf = api.get(f"{KRI}?framework=bank_tcfd&entity_id={leasing}", headers=maker).json()
    assert not nf["supported"] and nf["notice"]["code"] == "kri.filer.not_found" and len(nf["filers"]) == 2


def test_insurer_kris_follow_the_filer(api):
    maker, _, admin = _users(api)
    s = api.s
    from services.governance.filings import reporting_period_end
    state_method(s, IBERIA, reporting_period_end(s, IBERIA))
    r = api.get(f"{KRI}?framework=insurer_solvency", headers=admin).json()
    assert r["filer"]["label"] == "Iberia Mutual Group (group)" and r["filer"]["default"]
    assert {f["label"] for f in r["filers"]} == {"Iberia Mutual Group (group)", "Iberia Mutual Seguros", "Iberia Re"}
    fid = _file(api, maker, "insurer_solvency", IBERIA_RE)
    p = _payload(s, fid)
    mine = api.get(f"{KRI}?framework=insurer_solvency&entity_id={IBERIA_RE}&role=solo", headers=admin).json()
    kpi = {k["key"]: k for k in mine["kpis"]}
    assert kpi["sum_insured"]["value"] == pytest.approx(p["rollup"]["total_sum_insured_eur"], rel=1e-9)
    h = next(x for x in mine["history"] if x["filing_id"] == fid)
    if "natcat_scr" in kpi:
        assert kpi["natcat_scr"]["value"] == _figure(h, "natcat_scr")
    assert _scopes(s, [x["filing_id"] for x in mine["history"]]) <= {(IBERIA_RE, "solo"), (IBERIA_RE, None)}
    assert fid not in {x["filing_id"] for x in r["history"]}


def test_reit_kris_are_the_groups(api):
    maker = _login(api, "admin@stellar.demo", "Demo!admin1")
    s = api.s
    org = s.execute(text("SELECT org_id::text FROM organizations WHERE name = 'Stellar Logistics REIT (demo)'")).scalar_one()
    pe = year_without_roles(s, org)
    state_method(s, org, pe)
    assert api.get(f"{KRI}?framework=reit_taxonomy", headers=maker).json()["notice"]["code"] == "kri.filer.none"
    grp = group(s, org)
    state_role_in_session(s, org, grp, pe)
    fid = _file(api, maker, "reit_taxonomy", grp)
    r = api.get(f"{KRI}?framework=reit_taxonomy", headers=maker).json()
    assert r["filer"]["entity_id"] == grp and r["basis"]["filer"]["code"] == "kri.filer.scope.head_alone"
    h = next(x for x in r["history"] if x["filing_id"] == fid)
    assert next(k for k in r["kpis"] if k["key"] == "taxonomy")["value"] == _figure(h, "taxonomy")
    assert _scopes(s, [x["filing_id"] for x in r["history"]]) <= {(grp, "consolidated"), (grp, None)}


def test_an_organisation_with_one_entity_keeps_the_whole_book(api):
    s = api.s
    org = s.execute(text("SELECT org_id::text FROM organizations WHERE name = 'Hibernia Bank (demo)'")).scalar_one()
    assert s.execute(text("SELECT count(*) FROM reporting_entities WHERE org_id = CAST(:o AS uuid)"), {"o": org}).scalar() == 1
    from services.governance.kri import _live_snapshot, kri
    from services.governance.reporting_settings import get_settings
    r = kri(s, org, "bank_tcfd")
    assert r["supported"] and "filer" not in r and "filer" not in r["basis"]
    st = get_settings(s, org)
    whole = _live_snapshot(s, org, "bank_tcfd", st["scenario"], st["horizon"])
    assert next(k for k in r["kpis"] if k["key"] == "total_value")["value"] == whole["rollup"]["total_value_eur"]
    filed = s.execute(text("""SELECT count(*) FROM regulatory_filing f JOIN report_snapshots rs ON rs.snapshot_id = f.snapshot_id
                              WHERE f.org_id = CAST(:o AS uuid) AND f.framework = 'bank_tcfd'"""), {"o": org}).scalar()
    assert len(r["history"]) == filed


def test_appetite_bands_are_set_per_report_even_before_it_has_a_filer(api):
    """Settings → KRI appetite lists a report's indicators while no one files it yet — without a value, since any value
    would be no filer's."""
    admin = _login(api, "admin@meridian.demo", "Demo!admin1")
    year_without_roles(api.s, BANK_ORG)
    assert api.get(f"{KRI}?framework=bank_tcfd", headers=admin).json()["notice"]["code"] == "kri.filer.none"
    r = api.get("/v1/admin/kri-appetite?framework=bank_tcfd", headers=admin).json()
    assert r["supported"] and r["framework"] == "bank_tcfd" and r["kpis"]
    assert {k["key"] for k in r["kpis"]} >= {"pct_at_risk", "coverage"}
    assert all(k["value"] is None and k["status"] is None for k in r["kpis"])
