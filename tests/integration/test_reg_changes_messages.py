"""The Regulatory outlook and the change pipeline send their explanations as catalogue messages, never as sentences
written where they arise, and their figures are counted on the right population (UI standard, product owner
2026-10-16). Through the HTTP API, in one rolled-back transaction: nothing is left behind.

  - every explanation (a change's phase, its date check, a detected or draft change, a field's readiness, an alert, an
    early signal, the version register's check) is a code from data/reference/messages.en.json with its label and detail;
    no change title carries a register code (a CELEX number) and no alert carries a day count frozen when it was raised
  - a change whose date has passed is counted as taken effect, not as ahead
  - a retired report is not in force for anyone: not listed, not counted, not in the version register
  - the data a change asks for is counted on the records the regulation covers (EUDR: the plots of EUDR-covered
    commodities, the same plots its scope counts)
  - refusals (a change register error, a refused sign-off) are catalogue errors
  - the platform operator, whose page the change pipeline is, can read its board and the specification register
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from core import messages
from services.governance.filings import FRAMEWORKS
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
EXPLAINED = {"note", "rule", "reason", "basis_note", "message", "phase_message", "verified", "data_message", "standing", "checked", "not_read"}
CELEX = re.compile(r"\b3\d{4}[A-Z]\d{3,4}\b")                     # a register code, e.g. 32022R2453


def _is_message(m) -> bool:
    if not isinstance(m, dict) or m.get("code") not in messages.catalogue():
        return False
    r = messages.render(m["code"], **(m.get("params") or {}))
    return m["label"] == r["label"] and bool(m["detail"].get("what"))


def _explanations(body, path=""):
    """Every value under an explanation key, anywhere in the response (a message's own params are its values)."""
    if isinstance(body, dict) and {"code", "label", "detail"} <= set(body):
        return
    if isinstance(body, dict):
        for k, v in body.items():
            if k in EXPLAINED and v is not None:
                yield f"{path}.{k}", v
            yield from _explanations(v, f"{path}.{k}")
    elif isinstance(body, list):
        for i, v in enumerate(body):
            yield from _explanations(v, f"{path}[{i}]")


def _all_messages(body) -> list[str]:
    return [p for p, v in _explanations(body) if not _is_message(v)]


def test_the_outlook_explains_in_catalogue_messages_and_counts_by_date(api):
    for email in ("admin@meridian.demo", "admin@oranje.demo"):
        h = _login(api, email, "Demo!admin1")
        o = api.get("/v1/reg-changes/outlook", headers=h).json()
        assert not _all_messages(o), _all_messages(o)
        today = date.today().isoformat()
        for c in o["coming"]:
            assert _is_message(c["phase_message"]) and not CELEX.search(c["title"]), c["title"]
            assert c["phase"] == ("undated" if not c["date"] else "in_force" if c["date"] < today else "dated"), c
            if c["source"] in ("detected", "draft"):
                assert _is_message(c["message"]) and c["title"] == c["name"], c
            for f in c["data_fields"]:
                assert _is_message(f["message"]) and "detail" not in f, f
        s = o["summary"]
        assert s["n_ahead"] == sum(1 for c in o["coming"] if c["phase"] != "in_force")
        assert s["n_took_effect"] == sum(1 for c in o["coming"] if c["phase"] == "in_force")
        assert s["n_ahead"] + s["n_took_effect"] == s["n_coming"]
        # a retired report is no longer owed: not in force, not in the version register
        retired = {fw for fw, m in FRAMEWORKS.items() if m.get("retired")}
        assert not retired & {f["framework"] for f in o["in_force"]}
        v = api.get("/v1/reg-changes/versions", headers=h).json()
        assert not retired & {f["framework"] for f in v["frameworks"]} and not _all_messages(v), _all_messages(v)
        for f in v["frameworks"]:
            for a in f["acts"]:
                assert a["role_label"] and all(r["relation_label"] for r in a["replaced_by"]), a
        sig = api.get("/v1/reg-changes/signals", headers=h).json()
        assert _is_message(sig["message"]) and not _all_messages(sig) and "note" not in sig
        assert all(x["jurisdiction_name"] and x["authority"] for x in sig["signals"])
        al = api.get("/v1/reg-changes/alerts", headers=h).json()["alerts"]
        for a in al:
            assert _is_message(a["message"]) and a["name"], a
            if a["effective_date"]:
                assert a["days"] == (date.fromisoformat(a["effective_date"]) - date.today()).days


def test_the_data_a_change_asks_for_is_counted_on_the_records_it_covers(api):
    """EUDR: the plots of EUDR-covered commodities — the population its scope counts — not every sourcing plot."""
    h = _login(api, "admin@oranje.demo", "Demo!admin1")
    o = api.get("/v1/reg-changes/outlook", headers=h).json()
    eudr = next((c for c in o["coming"] if c["framework"] == "eudr_dds" and c["data_fields"]), None)
    if eudr is None or not (eudr.get("impact") or {}).get("scope"):
        pytest.skip("no EUDR change with plots on file for the demo agri organisation")
    plots = eudr["impact"]["scope"]["n"]
    counted = [f for f in eudr["data_fields"] if f["total"] is not None and f["field"].lower().startswith(("plot", "country", "legality", "supplier"))]
    assert counted and all(f["total"] == plots for f in counted), (plots, [(f["field"], f["total"]) for f in counted])


def test_refusals_are_catalogue_errors(api):
    h = _login(api, "admin@meridian.demo", "Demo!admin1")
    r = api.post("/v1/reg-changes", headers=h, json={"title": "   "})
    assert r.status_code == 409 and r.json()["error"]["error"] == "regchange.error.title", r.text
    board = api.get("/v1/reg-changes/board", headers=h).json()
    platform = next((c for st in board["stages"] for c in st["changes"] if c["is_platform"]), None)
    if platform is not None:
        r = api.post(f"/v1/reg-changes/{platform['change_id']}/advance", headers=h, json={"stage": "analysis"})
        assert r.status_code == 409 and r.json()["error"]["error"] == "regchange.error.not_yours", r.text
    r = api.post("/v1/reg-changes/00000000-0000-4000-8000-000000000000/advance", headers=h, json={"stage": "nowhere"})
    assert r.json()["error"]["error"] == "regchange.error.stage", r.text

    ops = _login(api, "ops@tellumen.io", "Demo!ops1")
    spec = api.get("/v1/regspec", headers=ops).json()["specs"][0]
    r = api.post(f"/v1/regspec/{spec['framework']}/{spec['version']}/sign", headers=ops,
                 json={"role": "regulatory", "sha256": "0" * 64})
    assert r.status_code == 409 and r.json()["error"]["error"] == "regchange.spec.error.changed", r.text
    r = api.post("/v1/regspec/no_such/version/sign", headers=ops, json={"role": "regulatory", "sha256": "0" * 64})
    assert r.status_code == 404 and r.json()["error"]["error"] == "regchange.spec.error.not_found", r.text
    for body in (r.json(),):
        assert body["error"]["message"] == messages.label("regchange.spec.error.not_found")


def test_the_operator_reads_the_pipeline_and_every_specification_is_named_in_words(api):
    """The change pipeline is the platform operator's page: its board and the specification register read for them
    (they hold platform.admin, not a customer's report permission). Every family is named, never by its key."""
    ops = _login(api, "ops@tellumen.io", "Demo!ops1")
    assert api.get("/v1/reg-changes/board", headers=ops).status_code == 200
    specs = api.get("/v1/regspec", headers=ops).json()["specs"]
    assert specs
    for s in specs:
        assert s["name"] and s["name"] != s["framework"] and "_" not in s["name"], s["name"]
        assert s["applies"]["basis_label"] and len(s["needs_labels"]) == len(s["needs"])
        assert all(g["role_label"] for g in s["signed"] + s["voided_by_edit"])
        if s["diff"]:
            assert s["diff"]["kind_label"] and all(t["title"] for t in s["diff"]["added"] + s["diff"]["changed"] + s["diff"]["removed"])
        for c in s["coverage_by_template"]:
            assert c["title"] and not re.search(r"\.(rows|columns|items)\.", c["code"]), c     # per template, never a cell key
        if s["checks"] and s["checks"]["failing"]:
            assert _is_message(s["checks"]["message"])
