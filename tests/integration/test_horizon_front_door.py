"""Horizon, the front door (services/intelligence/front_door.py, api/routers/tasks.py). Requires PostgreSQL.

Guards for what the front door got wrong (E218-E223, rows A-F in order):
  A  it read a legacy copy of each financial book (bank_assets, insurance_policies, …) that only four demo tenants still
     had — 32 of 36 financial tenants saw an empty globe, the other four a stale one with its own scoring rule
  B  it counted "at elevated risk" against a typed 50 instead of the organisation's stated at-risk level
  C  raw codes reached the screen (a taxonomy status 'not_eligible', role keys, entity kinds)
  D  a supervisor landed on an empty globe asking it to add assets, with filing checks it does not have
  E  the task feed re-implemented the readiness checks and contradicted them (an EORI task for a bank)
  F  an agricultural hazard held only on the current climate vanished from every future year
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import text

from core import messages
from core.db.session import get_session
from services.geo.org_assets import (  # the books the one reader covers
    _ENGINE_VERTICALS,
    org_asset_points,
)
from services.intelligence import front_door as fd

ROOT = Path(__file__).resolve().parents[2]
_LEGACY = ("bank_assets", "insurance_policies", "assetmgmt_holdings", "realestate_properties")
_SNAKE = re.compile(r"^[a-z][a-z0-9]*_[a-z0-9_]+$")
pytestmark = pytest.mark.integration


def _org(s, name: str) -> tuple[str, str]:
    r = s.execute(text("SELECT org_id::text, type FROM organizations WHERE name = :n"), {"n": name}).first()
    if r is None:
        pytest.skip(f"demo tenant {name} is not seeded")
    return r[0], r[1]


def _client_for(email: str, pw: str):
    from fastapi.testclient import TestClient

    from api.main import app
    from tests.integration.conftest import _login
    c = TestClient(app, raise_server_exceptions=True)
    return c, _login(c, email, pw)


def test_the_front_door_reads_no_legacy_book():
    """A: the reader and its router name none of the retired per-sector tables."""
    for f in ("services/intelligence/front_door.py", "api/routers/tasks.py"):
        src = (ROOT / f).read_text()
        assert not [t for t in _LEGACY if re.search(rf"\b{t}\b", src)], f


@pytest.mark.parametrize("name", ["Meridian Bank (demo)", "Banco do Tejo (demo)", "Iberia Mutual (demo)",
                                  "Baltic Mutual (demo)", "Seine Capital (demo)", "Thames Estates (demo)"])
def test_the_globe_is_the_shared_book_with_the_engines_headline(name):
    """A: every located exposure of the shared book is on the globe, and today's score is the engine's headline — the
    number Portfolio and the supervisor's map show for the same asset."""
    with get_session() as s:
        org, typ = _org(s, name)
        located = s.execute(text("""SELECT count(*) FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND source = 'own'
                                    AND vertical = ANY(:v) AND latitude IS NOT NULL AND longitude IS NOT NULL"""),
                            {"o": org, "v": list(_ENGINE_VERTICALS)}).scalar()
        view = fd.book(s, org, typ, "disorderly_2c")
        assert located > 0 and view["n_assets"] == located
        engine = {p["id"]: p["score"] for p in org_asset_points(s, org, "baseline", "current")}
        for a in view["assets"]:
            assert a["score"][0] == (round(engine[a["id"]], 1) if engine[a["id"]] is not None else None)
            assert a["ref"] == a["id"].split(":", 1)[1]           # the id Decisions and Portfolio use


def test_at_risk_follows_the_stated_level(monkeypatch):
    """B: an asset is at risk at a stop when its score is at or above the stated level; no level, no count — the gap."""
    from services.money.params import Method
    with get_session() as s:
        org, typ = _org(s, "Meridian Bank (demo)")
        real = Method.get
        monkeypatch.setattr(Method, "get", lambda self, key, member=None: 70.0 if key == "method.at_risk_level" else real(self, key, member))
        view = fd.book(s, org, typ, "hot_house_3_5c")
        assert view["at_risk"]["level"] == 70.0 and view["at_risk"]["message"]["code"] == "horizon.at_risk.basis"
        for i in range(len(fd.stops("hot_house_3_5c"))):
            flagged = [a for a in view["assets"] if a["at_risk"][i]]
            assert all(a["score"][i] is not None and a["score"][i] >= 70.0 for a in flagged)
            assert all(a["score"][i] is None or a["score"][i] < 70.0 for a in view["assets"] if not a["at_risk"][i])
            assert view["at_risk"]["by_stop"][i]["n"] == len(flagged)
        monkeypatch.setattr(Method, "get", lambda self, key, member=None: None if key == "method.at_risk_level" else real(self, key, member))
        view = fd.book(s, org, typ, "hot_house_3_5c")
        assert view["at_risk"]["by_stop"] is None and view["at_risk"]["gap"] == "not stated: method.at_risk_level"
        assert view["at_risk"]["message"]["code"] == "horizon.at_risk.not_stated"
        assert all(f is None for a in view["assets"] for f in a["at_risk"])


def _shown(globe: dict, tasks: list[dict], entities: list[dict]) -> list[str]:
    """Every piece of text the front door puts on screen or in a pop-up."""
    def msg(m):
        return [m["label"], *m["detail"].values()] if m else []
    out = [globe["noun"], globe["scenario"]["name"], *[x["name"] for x in globe["scenarios"]], *[x["label"] for x in globe["stops"]],
           *[r["name"] for r in globe["my_scope"]["roles"]], *msg(globe["at_risk"]["message"])]
    for a in globe["assets"]:
        out += [a["kind_name"], a["region"], *[f["label"] for f in a["facts"]], *[f["text"] for f in a["facts"] if f.get("text")],
                *a["adaptations"], *msg(a["notice"])]
    for c in globe["readiness"]["checks"]:
        out += [*msg(c["message"]), c["fix_label"] or ""]
    for t in tasks:
        out += [*msg(t["message"]), *msg(t["due"]), t["action"]["label"]]
    out += [e["kind_name"] for e in entities]
    return [x for x in out if x]


@pytest.mark.parametrize("email,pw", [("admin@meridian.demo", "Demo!admin1"), ("admin@iberia.demo", "Demo!admin1"),
                                      ("admin@nordkap.demo", "Demo!admin1"), ("admin@stellar.demo", "Demo!admin1"),
                                      ("admin@terra.demo", "Demo!admin1"), ("admin@supervisor.demo", "Demo!admin1")])
def test_everything_the_front_door_shows_is_customer_language(email, pw):
    """C: no internal key, snake_case code or engineering word anywhere the front door shows text."""
    c, h = _client_for(email, pw)
    g = c.get("/v1/me/globe", headers=h)
    assert g.status_code == 200, g.text
    tasks = c.get("/v1/me/tasks", headers=h).json()["tasks"]
    ents = c.get("/v1/me/entities", headers=h).json()["entities"]
    bad = [x for x in _shown(g.json(), tasks, ents) if messages.INTERNAL.search(x) or _SNAKE.match(x)]
    assert bad == []


def test_a_supervisor_sees_its_population_by_region_never_a_site():
    """D: the supervisor's front door is its population rolled up to regions, with its own figures — no site
    coordinates, no filing-identity or approver check (it files nothing and decides no approvals)."""
    c, h = _client_for("admin@supervisor.demo", "Demo!admin1")
    g = c.get("/v1/me/globe", headers=h).json()
    assert g["audience"] == "supervisor" and g["n_assets"] > 0
    assert {a["kind"] for a in g["assets"]} == {"region"}
    assert {"entities", "filings_expected", "filings_outstanding", "open_requests"} <= set(g["supervisor"])
    assert not {"identity", "second_approver"} & {x["key"] for x in g["readiness"]["checks"]}
    with get_session() as s:
        from api.routers.supervisor import _supervised
        ctx = {"org": {"org_id": s.execute(text("SELECT org_id::text FROM organizations WHERE name='EU Banking Supervisor (demo)'")).scalar()},
               "user": {"id": s.execute(text("SELECT user_id::text FROM users WHERE email='admin@supervisor.demo'")).scalar()},
               "roles": ["supervisor", "risk_analyst", "data_steward", "inspector", "head", "admin"]}
        sites = {(round(p["lat"], 5), round(p["lon"], 5)) for e in _supervised(s, ctx)
                 for p in org_asset_points(s, e["org_id"], "baseline", "current") if p.get("lat") is not None}
    assert not [a for a in g["assets"] if (round(a["lat"], 5), round(a["lon"], 5)) in sites]


@pytest.mark.parametrize("email,pw", [("admin@meridian.demo", "Demo!admin1"), ("admin@stellar.demo", "Demo!admin1"),
                                      ("admin@terra.demo", "Demo!admin1")])
def test_the_task_feed_says_what_the_checklist_says(email, pw):
    """E: every failing readiness check is a task for an administrator, in the same words; no task claims a check
    fails that the checklist passes."""
    c, h = _client_for(email, pw)
    checks = {x["key"]: x for x in c.get("/v1/me/globe", headers=h).json()["readiness"]["checks"]}
    tasks = {t["key"]: t for t in c.get("/v1/me/tasks", headers=h).json()["tasks"]}
    for k, chk in checks.items():
        if chk["ok"]:
            assert k not in tasks, f"a task for the passing check {k}"
        elif chk["fix_href"]:
            assert tasks[k]["message"] == chk["message"] and tasks[k]["action"]["href"] == chk["fix_href"]
    assert not set(tasks) & {"identity_incomplete", "golden_source_stale", "plots_polygon", "first_run"}   # the old copies


def test_an_agricultural_hazard_held_on_todays_climate_carries_forward():
    """F: a hazard stored only on the current climate (it does not vary by scenario) keeps its value in every future
    year, as the financial engine's scenario-flat rule does — it never silently drops out of the headline."""
    from core.hazard_relevance import is_headline_eligible
    with get_session() as s:
        org, _ = _org(s, "Terra Foods (demo)")
        rows = s.execute(text("""SELECT plot_id::text AS id, hazard_type, scenario, physical_risk_score AS score, model_version
                                 FROM v_sc_plot_physical_risk WHERE org_id = CAST(:o AS uuid)"""), {"o": org}).mappings().all()
        varying = {(r["id"], r["hazard_type"]) for r in rows if r["scenario"] == "disorderly_2c"}
        flat_max: dict[str, float] = {}
        for r in rows:
            if (r["scenario"] == "baseline" and (r["id"], r["hazard_type"]) not in varying and r["score"] is not None
                    and is_headline_eligible(r["hazard_type"], "agriculture", r["model_version"])):
                flat_max[r["id"]] = max(flat_max.get(r["id"], 0.0), float(r["score"]))
        assert flat_max, "the demo book has hazards held only on the current climate"
        for horizon in ("2030", "2050", "2100"):
            fut = {p["id"].split(":", 1)[1]: p["score"] for p in org_asset_points(s, org, "disorderly_2c", horizon) if p["kind"] == "plot"}
            short = {pid: (fut.get(pid), v) for pid, v in flat_max.items() if fut.get(pid) is None or fut[pid] < v}
            assert short == {}, horizon


def test_every_role_and_entity_kind_has_a_customer_name():
    """C: the names the front door gives a role or a reporting entity's kind exist for everything the data holds."""
    with get_session() as s:
        roles = s.execute(text("""SELECT DISTINCT r.name, o.type FROM roles r JOIN organizations o ON o.org_id = r.org_id""")).all()
        kinds = s.execute(text("SELECT DISTINCT kind FROM reporting_entities")).scalars().all()
    for name, typ in roles:
        assert fd.role_names(typ, [name])[0]["name"]
    for k in kinds:
        assert messages.name("entity_kind", k)
