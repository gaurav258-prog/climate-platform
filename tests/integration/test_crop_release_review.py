"""E148: a FAOSTAT crop-production file lands only after two platform operators review it — end to end through the HTTP
API, in one rolled-back transaction, on a small file in the publisher's format under a test source name (so the real
store and any real release are untouched):

  stage     the file is read and compared with the store: a year held with other production → revised (the value held
            before kept); a year not held → added; same figures, other derived yield → recomputed; nothing written
  review    a customer cannot see or act on releases; the operator proposes with what was reviewed; the proposer cannot
            approve; the second operator approves → the rows land; replaced values stay in the release (append-only)
  schedule  the same file is not staged twice; while a release is open the scheduled check does not fetch at all
"""
from __future__ import annotations

import csv
import io
import zipfile

import pytest
from sqlalchemy import text

from services.reference import crop_releases as R
from services.reference import faostat_crops as F
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
SRC = "FAOSTAT QCL test (E148)"


def _zip(rows: list[tuple[int, str, str, int, float]]) -> bytes:
    """(area code, item, element, year, value) rows → the publisher's zip layout."""
    m49 = {107: "'384", 99999: "'159", 5000: "'001"}         # Côte d'Ivoire; an aggregate ('China', not a country); World
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Area Code", "Area Code (M49)", "Area", "Item", "Element", "Year", "Unit", "Value"])
    for code, item, element, year, value in rows:
        w.writerow([code, m49.get(code, "'000"), "x", item, element, year, "t" if element == "Production" else "ha", value])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("Production_Crops_Livestock_E_All_Data_(Normalized).csv", buf.getvalue().encode("utf-8-sig"))
    return out.getvalue()


@pytest.fixture
def source(api, monkeypatch):
    """A test source name, and the platform policy at two people — whatever the live database states (the demo
    states one approver, E150) — inside the test's rolled-back transaction."""
    from services.governance.platform_policy import PLATFORM_ORG
    monkeypatch.setattr(F, "source", lambda: SRC)
    api.s.execute(text("""UPDATE approval_policy SET human_approvers = 2
                          WHERE org_id = CAST(:o AS uuid) AND action_key = 'reference.release_land'"""), {"o": PLATFORM_ORG})
    return SRC


def test_a_release_lands_only_after_two_operators_review_it(api, source, monkeypatch):
    s = api.s
    for yr, prod, area, yld in ((2020, 1000.0, 500.0, 2.0), (2021, 1100.0, 500.0, 2.2222)):    # held: CI cocoa
        s.execute(text("""INSERT INTO crop_yield_observations (commodity, country, season_year, production_tonnes,
                          area_harvested_ha, yield_tonnes_ha, source) VALUES ('Cocoa', 'CI', :y, :p, :a, :yl, :s)"""),
                  {"y": yr, "p": prod, "a": area, "yl": yld, "s": SRC})
    data = _zip([(107, "Cocoa beans", "Production", 2020, 1000.0), (107, "Cocoa beans", "Area harvested", 2020, 400.0),
                 (107, "Cocoa beans", "Production", 2021, 1100.0), (107, "Cocoa beans", "Area harvested", 2021, 500.0),
                 (107, "Cocoa beans", "Production", 2022, 900.0), (107, "Cocoa beans", "Area harvested", 2022, 450.0),
                 (99999, "Cocoa beans", "Production", 2022, 5.0),            # an aggregate, not a country: not read
                 (107, "Not a crop we map", "Production", 2022, 5.0)])
    out = R.stage(s, data, last_modified="Wed, 01 Oct 2026 00:00:00 GMT")
    assert out["staged"] and out["status"] == "staged"
    sm = out["summary"]
    assert (sm["rows_in_file"], sm["added"], sm["revised"], sm["recomputed"], sm["unchanged"]) == (3, 1, 1, 1, 0)
    assert sm["by_commodity"]["Cocoa"]["years_new"] == [2022]
    rid = out["release_id"]
    held = s.execute(text("SELECT count(*) FROM crop_yield_observations WHERE source = :s"), {"s": SRC}).scalar()
    assert held == 2                                                       # staging wrote nothing to the store

    customer = _login(api, "admin@terra.demo", "Demo!admin1")
    assert api.get("/v1/ops/reference-releases", headers=customer).status_code == 403
    assert api.post(f"/v1/ops/reference-releases/{rid}/propose", headers=customer, json={"reason": "x" * 12}).status_code == 403

    ops, ops2 = _login(api, "ops@tellumen.io", "Demo!ops1"), _login(api, "ops2@tellumen.io", "Demo!ops2")
    lst = api.get("/v1/ops/reference-releases", headers=ops).json()
    assert lst["feed"]["awaiting_review"]["release_id"] == rid and lst["releases"][0]["release_id"] == rid
    detail = api.get(f"/v1/ops/reference-releases/{rid}", headers=ops).json()
    rows = {(r["season_year"], r["change"]): r for r in detail["rows"]}
    assert rows[(2020, "revised")]["held_before"]["area_harvested_ha"] == 500.0 and rows[(2020, "revised")]["area_harvested_ha"] == 400.0
    assert (2022, "added") in rows and (2021, "recomputed") in rows
    only = api.get(f"/v1/ops/reference-releases/{rid}?change=recomputed", headers=ops).json()["rows"]
    assert [(r["season_year"], r["change"]) for r in only] == [(2021, "recomputed")]
    assert api.get(f"/v1/ops/reference-releases/{rid}?change=deleted", headers=ops).status_code == 422

    assert api.post(f"/v1/ops/reference-releases/{rid}/propose", headers=ops, json={"reason": "short"}).status_code == 409
    p = api.post(f"/v1/ops/reference-releases/{rid}/propose", headers=ops, json={"reason": "checked the CI 2020 area revision"})
    assert p.status_code == 200, p.text
    req = p.json()["approval_request_id"]
    own = api.post(f"/v1/approvals/{req}/decide", headers=ops, json={"decision": "approved"})
    assert own.status_code in (403, 422)                                   # the proposer never approves
    d = api.post(f"/v1/approvals/{req}/decide", headers=ops2, json={"decision": "approved", "reason": "agreed"})
    assert d.status_code == 200, d.text
    landed = dict(s.execute(text("""SELECT season_year, CAST(area_harvested_ha AS FLOAT) FROM crop_yield_observations
                                    WHERE source = :s"""), {"s": SRC}).all())
    assert landed == {2020: 400.0, 2021: 500.0, 2022: 450.0}
    rel = api.get("/v1/ops/reference-releases", headers=ops2).json()
    assert rel["releases"][0]["status"] == "landed" and rel["releases"][0]["decided_by"] == "ops2@tellumen.io"
    assert rel["feed"]["awaiting_review"] is None
    with pytest.raises(Exception, match="append-only"):
        with s.begin_nested():
            s.execute(text("UPDATE crop_yield_release_rows SET production_tonnes = 1 WHERE release_id = CAST(:r AS uuid)"), {"r": rid})

    again = R.stage(s, data)
    assert not again["staged"] and again["release_id"] == rid              # the same file is not staged twice


def test_while_a_release_is_open_the_schedule_does_not_fetch(api, source, monkeypatch):
    s = api.s
    first = R.stage(s, _zip([(107, "Cocoa beans", "Production", 2030, 10.0)]))
    assert first["staged"]
    with pytest.raises(R.ReleaseError, match="still open"):
        R.stage(s, _zip([(107, "Cocoa beans", "Production", 2031, 10.0)]))

    def no_fetch(*a, **k):
        raise AssertionError("fetched while a release is open")
    monkeypatch.setattr(F, "published", no_fetch)
    monkeypatch.setattr(F, "download", no_fetch)
    out = R.refresh(s)
    assert not out["staged"] and "awaiting review" in out["reason"]
    ops = _login(api, "ops@tellumen.io", "Demo!ops1")
    r = api.post(f"/v1/ops/reference-releases/{first['release_id']}/reject", headers=ops, json={"reason": "test file, not a release"})
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert s.execute(text("SELECT count(*) FROM crop_yield_observations WHERE source = :s"), {"s": SRC}).scalar() == 0


def test_the_publisher_figures_are_rounded_as_the_store_rounds_them():
    rows = F.parse(_zip([(107, "Cocoa beans", "Production", 2020, 1563.35), (107, "Cocoa beans", "Area harvested", 2020, 1000.0)]),
                   {"384": "CI"})
    assert rows[0]["production_tonnes"] == 1563.4                          # Postgres numeric(16,1): half away from zero


def test_with_one_approver_stated_the_platform_proposes_and_one_person_approves(api, source):
    """E150: an organisation with a single approver says so; staging then proposes as the platform's system account
    (which can never sign in) and one operator approves — the approvals path still refuses a maker deciding."""
    from services.governance.platform_policy import SYSTEM_USER
    ops = _login(api, "ops@tellumen.io", "Demo!ops1")
    bad = api.put("/v1/ops/reference-releases/policy", headers=ops,
                  json={"action_key": "reference.release_land", "human_approvers": 1, "reason": "x"})
    assert bad.status_code == 422                                          # a reason, in words
    r = api.put("/v1/ops/reference-releases/policy", headers=ops, json={
        "action_key": "reference.release_land", "human_approvers": 1, "reason": "one approver in the organisation today"})
    assert r.status_code == 200 and r.json() == {"action_key": "reference.release_land", "human_approvers": 1, "was": 2}
    pol = {p["action_key"]: p for p in api.get("/v1/ops/reference-releases/policy", headers=ops).json()["policies"]}
    assert pol["reference.release_land"]["human_approvers"] == 1 and set(pol) == {"reference.release_land", "calibration.publish"}
    assert api.post("/v1/auth/login", json={"email": "pipeline@system.tellumen.io", "password": ""}).status_code in (401, 422)

    out = R.stage(api.s, _zip([(107, "Cocoa beans", "Production", 2040, 10.0), (107, "Cocoa beans", "Area harvested", 2040, 5.0)]))
    assert out["status"] == "proposed"
    maker = api.s.execute(text("SELECT maker_user_id::text FROM approval_requests WHERE request_id = CAST(:r AS uuid)"),
                          {"r": out["approval_request_id"]}).scalar()
    assert maker == SYSTEM_USER
    d = api.post(f"/v1/approvals/{out['approval_request_id']}/decide", headers=ops, json={"decision": "approved", "reason": "reviewed"})
    assert d.status_code == 200 and d.json()["applied"]["status"] == "landed"
    assert api.s.execute(text("SELECT count(*) FROM crop_yield_observations WHERE source = :s"), {"s": SRC}).scalar() == 1


def test_an_unchanged_file_is_never_downloaded_twice(api, source, monkeypatch):
    """E152: each check is recorded with the publisher's validators; the next check compares with them — the file is
    downloaded only when the publisher says it changed (a release from disk carries none, which used to mean a 34 MB
    download on every check)."""
    calls = {"head": [], "get": 0}
    data = _zip([(107, "Cocoa beans", "Production", 2050, 10.0), (107, "Cocoa beans", "Area harvested", 2050, 5.0)])

    def head(last_modified, etag):
        calls["head"].append((last_modified, etag))
        same = etag == '"v1"'
        return {"changed": not same, "last_modified": "Wed, 01 Oct 2026 00:00:00 GMT", "etag": '"v1"'}

    def get():
        calls["get"] += 1
        return data
    monkeypatch.setattr(F, "published", head)
    monkeypatch.setattr(F, "download", get)
    first = R.refresh(api.s)
    assert first["staged"] and calls["get"] == 1 and calls["head"][0] == (None, None)
    ops = _login(api, "ops@tellumen.io", "Demo!ops1")
    api.post(f"/v1/ops/reference-releases/{first['release_id']}/reject", headers=ops, json={"reason": "test file, closing it"})
    second = R.refresh(api.s)
    assert not second["staged"] and calls["get"] == 1 and calls["head"][1] == ("Wed, 01 Oct 2026 00:00:00 GMT", '"v1"')
    rows = api.s.execute(text("SELECT changed, downloaded, outcome FROM crop_release_checks WHERE source = :s ORDER BY check_id"),
                         {"s": SRC}).all()
    assert [(r[0], r[1]) for r in rows] == [(True, True), (False, False)]
