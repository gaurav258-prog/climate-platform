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


@pytest.fixture(autouse=True)
def _raw_in_tmp(tmp_path, monkeypatch):
    """Raw publisher data a test 'downloads' is kept in a temporary folder, never in the checkout."""
    monkeypatch.setattr(R, "RAW_ROOT", tmp_path / "raw_releases")


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
    feed = next(f for f in lst["feeds"] if f["source"] == "faostat")
    assert feed["awaiting_review"]["release_id"] == rid and lst["releases"][0]["release_id"] == rid
    assert {f["source"] for f in lst["feeds"]} >= {"faostat", "eurostat"}
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
    assert next(f for f in rel["feeds"] if f["source"] == "faostat")["awaiting_review"] is None
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


def test_eurostat_is_read_for_countries_only_with_its_own_definitions():
    """E153: a second reviewed source — Eurostat's JSON-stat read into the same rows: thousands → absolutes, Greece
    'EL' → GR, aggregates (EU27_2020) not read, the published yield kept, year-on-year from production."""
    import json as _json

    from services.reference import eurostat_crops as E

    def doc(values):
        geos, times = ["EL", "EU27_2020"], ["2023", "2024"]
        return {"id": ["geo", "time"], "size": [2, 2],
                "dimension": {"geo": {"category": {"index": {g: i for i, g in enumerate(geos)}}},
                              "time": {"category": {"index": {t: i for i, t in enumerate(times)}}}},
                "value": {str(k): v for k, v in values.items()}}
    data = _json.dumps({"C1120|prod": doc({0: 1000.0, 1: 800.0, 2: 9000.0, 3: 8500.0}),
                        "C1120|area": doc({0: 300.0, 1: 290.0}),
                        "C1120|yield": doc({0: 3.3333, 1: 2.7586})}).encode()
    rows = {(r["country"], r["season_year"]): r for r in E.parse(data, {"EL": "GR", "GR": "GR"})}
    assert set(rows) == {("GR", 2023), ("GR", 2024)}                      # the EU27 aggregate is not a country
    r = rows[("GR", 2024)]
    assert (r["commodity"], r["production_tonnes"], r["area_harvested_ha"], r["yield_tonnes_ha"], r["yoy_change_pct"]) == \
           ("Durum wheat", 800000.0, 290000.0, 2.7586, -20.0)


def test_usda_fas_is_read_by_its_units_table_and_genc_codes():
    """E155: FAS rows — FIPS country codes matched through GENC (ISO alpha-3), units converted only by the reference
    table (1000 MT, 1000 60 kg bags), the European Union entity not a country, an unknown unit refused."""
    import json as _json

    from services.reference import fas_psd as U

    def doc(unit_prod=8, extra=()):
        return _json.dumps({"countries": [{"countryCode": "BR", "gencCode": "BRA"}, {"countryCode": "E4", "gencCode": None}],
                            "data": {"0711100|2024": [
                                {"countryCode": "BR", "marketYear": "2024", "attributeId": 28, "unitId": 2, "value": 1000.0},
                                {"countryCode": "BR", "marketYear": "2024", "attributeId": 4, "unitId": 4, "value": 2.0},
                                {"countryCode": "E4", "marketYear": "2024", "attributeId": 28, "unitId": 2, "value": 5.0},
                                *extra]}}).encode()
    rows = U.parse(doc(), {"BRA": "BR"})
    assert [(r["commodity"], r["country"], r["season_year"], r["production_tonnes"], r["area_harvested_ha"], r["yield_tonnes_ha"])
            for r in rows] == [("Coffee", "BR", 2024, 60000.0, 2000.0, 30.0)]
    with pytest.raises(U.FetchError, match="refused"):
        U.parse(doc(extra=({"countryCode": "BR", "marketYear": "2023", "attributeId": 28, "unitId": 999, "value": 1.0},)),
                {"BRA": "BR"})


def _nass(desc, level, state, year, value, load, period="YEAR", unit=None, where=None):
    return {"short_desc": desc, "agg_level_desc": level, "state_alpha": state, "year": year, "Value": value,
            "load_time": load, "reference_period_desc": period, "location_desc": where or state,
            "unit_desc": unit or desc.rsplit(" ", 1)[-1] if "MEASURED IN" in desc else unit or "ACRES"}


def test_usda_nass_reads_states_and_sets_aside_forecasts_withheld_and_other_states():
    """E157: NASS rows — the national figure (region '') and each state (ISO 3166-2 'US-IA'); bushels converted by the
    crop's stated weight, acres to hectares; a 'YEAR' figure loaded with an identical forecast is the season in
    progress, a withheld '(D)' is not a number, 'OTHER STATES' is not a state, an area with no production estimate is
    not a year read — each set aside and counted, never read."""
    import json as _json

    from services.reference import nass_quickstats as N
    P, A = "CORN, GRAIN - PRODUCTION, MEASURED IN BU", "CORN, GRAIN - ACRES HARVESTED"
    data = _json.dumps({"data": {
        f"{P}|year": [_nass(P, "NATIONAL", "US", "2024", "1,000,000", "2025-01-12 12:00:00.000", where="US TOTAL"),
                      _nass(P, "STATE", "IA", "2024", "100,000", "2025-01-12 12:00:00.000"),
                      _nass(P, "STATE", "IA", "2025", "120,000", "2026-01-12 12:00:00.000"),
                      _nass(P, "STATE", "IA", "2026", "130,000", "2026-09-11 12:00:00.000"),
                      _nass(P, "STATE", "NV", "2025", "(D)", "2026-01-12 12:00:00.000"),
                      _nass(P, "STATE", "OT", "2025", "5,000", "2026-01-12 12:00:00.000", where="OTHER STATES")],
        f"{P}|forecast": [_nass(P, "STATE", "IA", "2026", "130,000", "2026-09-11 12:00:00.000", "YEAR - SEP FORECAST")],
        f"{A}|year": [_nass(A, "STATE", "IA", "2025", "1,000", "2026-01-12 12:00:00.000"),
                      _nass(A, "STATE", "IA", "2026", "1,100", "2026-06-30 12:00:00.000")],   # June Acreage, no estimate
        f"{A}|forecast": []}}).encode()
    locs = {"US": "US", "IA": "US-IA", "NV": "US-NV"}
    rows = {(r["region_code"], r["season_year"]): r for r in N.parse(data, locs)}
    assert set(rows) == {("", 2024), ("US-IA", 2024), ("US-IA", 2025)}
    bu = 56 * 0.45359237 / 1000                                            # a bushel of corn: 56 lb
    r = rows[("US-IA", 2025)]
    assert (r["country"], r["production_tonnes"], r["area_harvested_ha"]) == \
           ("US", round(120000 * bu, 1), round(1000 * 0.40468564224, 1))
    assert r["yield_tonnes_ha"] == round(120000 * bu / (1000 * 0.40468564224), 4) and r["yoy_change_pct"] == 20.0
    assert N.set_aside(data, locs) == {"area without a production estimate for the year": 1,
                                       "not a state of the region reference (OTHER STATES)": 1,
                                       "not given as a number ((D))": 1,
                                       "season in progress — 'YEAR' repeats NASS's forecast": 1}
    assert N.stamp(data) == "2026-09-11 12:00:00.000"


def test_usda_nass_refuses_an_unknown_unit_and_never_shows_its_key(monkeypatch):
    """E157: a unit outside data/reference/nass_quickstats.json is refused; the Quick Stats key travels in the query
    string, so an error never carries the request — its text is rebuilt and the original is not chained."""
    import json as _json

    import requests

    from core.config import settings
    from services.reference import nass_quickstats as N
    P = "CORN, GRAIN - PRODUCTION, MEASURED IN BU"
    data = _json.dumps({"data": {f"{P}|year": [_nass(P, "STATE", "IA", "2025", "1", "t", unit="BOXES")],
                                 f"{P}|forecast": []}}).encode()
    with pytest.raises(N.FetchError, match="refused"):
        N.parse(data, {"IA": "US-IA"})
    monkeypatch.setattr(settings, "NASS_API_KEY", "SECRET-KEY-123")

    def boom(url, params=None, **kw):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}?key={dict(params)['key']}")
    monkeypatch.setattr(N.requests, "get", boom)
    with pytest.raises(N.FetchError) as e:
        N._count([("short_desc", P)])
    assert "SECRET-KEY-123" not in str(e.value) and e.value.__suppress_context__ and e.value.__cause__ is None


def test_a_region_outside_the_region_reference_is_refused(api, monkeypatch):
    """E157: a release whose reading names a region the reference does not hold is refused before anything is kept."""
    from services.reference.yield_sources import YieldSource
    ys = YieldSource(key="test", feed_key="test", label=lambda: "Region test (E157)", url=lambda: "x",
                     countries=lambda s: {}, reader=lambda c: "test-reader", published=lambda lm, et: {},
                     download=lambda: b"", parse=lambda d, c: [
                         {"commodity": "Maize", "country": "US", "region_code": "US-ZZ", "season_year": 2025,
                          "production_tonnes": 1.0, "area_harvested_ha": 1.0, "yield_tonnes_ha": 1.0,
                          "yoy_change_pct": None, "note": ""}])
    with pytest.raises(R.ReleaseError, match="US-ZZ"):
        R.stage(api.s, b"region test", source=ys)
    assert api.s.execute(text("SELECT count(*) FROM crop_yield_releases WHERE source = 'Region test (E157)'")).scalar() == 0


def test_eurostat_regional_reads_nuts2_and_sums_wheat_from_its_two_parts():
    """E158: apro_cpshr — a NUTS-2 region of NUTS 2021 is read (country from the code: EL → GR); wheat is common wheat
    + durum (both parts published, else set aside); a single-code crop keeps Eurostat's published yield; national,
    NUTS-1, extra-regio and other-NUTS-version codes are set aside and counted."""
    import json as _json

    from services.reference import eurostat_regional as E

    def doc(values: dict[tuple[str, str], float]):
        geos = ["EL", "EL5", "EL52", "ELZZ", "FR21", "ES61"]
        times = ["2023", "2024"]
        gi, ti = {g: i for i, g in enumerate(geos)}, {t: i for i, t in enumerate(times)}
        return {"id": ["geo", "time"], "size": [len(geos), len(times)],
                "dimension": {"geo": {"category": {"index": gi}}, "time": {"category": {"index": ti}}},
                "value": {str(gi[g] * len(times) + ti[t]): v for (g, t), v in values.items()}}
    everywhere = {(g, "2024"): 10.0 for g in ("EL", "EL5", "EL52", "ELZZ", "FR21")}
    data = _json.dumps({
        "C1110|prod": doc({**everywhere, ("EL52", "2023"): 8.0, ("ES61", "2024"): 50.0}),
        "C1110|area": doc({("EL52", "2024"): 2.0, ("EL52", "2023"): 2.0, ("ES61", "2024"): 10.0}),
        "C1120|prod": doc({("EL52", "2024"): 30.0}),                     # durum 2023 and in ES61 not published
        "C1120|area": doc({("EL52", "2024"): 6.0}),
        "C1120|yield": doc({("EL52", "2024"): 5.0}),
    }).encode()
    regions_ = {"EL52": "GR", "ES61": "ES"}
    assert E.stamp(data) is None and E.stamp(_json.dumps({"C1110|prod": {**doc({}), "updated": "2026-09-08"},
                                                          "C1120|prod": {**doc({}), "updated": "2026-03-01"}}).encode()) \
        == "2026-09-08"                                         # Eurostat's own stamp, read from the data
    rows = {(r["commodity"], r["region_code"], r["season_year"]): r for r in E.parse(data, regions_)}
    assert set(rows) == {("Wheat", "EL52", 2024), ("Durum wheat", "EL52", 2024)}
    w = rows[("Wheat", "EL52", 2024)]
    assert (w["country"], w["production_tonnes"], w["area_harvested_ha"], w["yield_tonnes_ha"]) == ("GR", 40000.0, 8000.0, 5.0)
    assert rows[("Durum wheat", "EL52", 2024)]["yield_tonnes_ha"] == 5.0          # published, one code
    aside = E.set_aside(data, regions_)
    assert aside["a summed crop with a part not published for the region and year"] == 2     # EL52 2023, ES61 2024
    assert aside["a NUTS-1 figure (regional series are read at NUTS-2)"] >= 1
    assert aside["extra-regio (not a territory)"] >= 1
    assert aside["not a NUTS 2021 region (a region of an earlier or later NUTS version)"] >= 1
    assert aside["a national or aggregate figure (national series are read from apro_cpsh1)"] >= 1


def test_eurostat_is_asked_again_while_it_prepares_a_large_answer(monkeypatch):
    """E158: a 413 'ASYNCHRONOUS_RESPONSE' is Eurostat preparing the data — asked again after a pause, a bounded number
    of times; never read as data."""
    from services.reference import eurostat_crops as E

    class Resp:
        def __init__(self, code, body):
            self.status_code, self.text, self._body = code, body, body

        def json(self):
            return {"updated": self._body}
    answers = [Resp(413, '{"error":[{"label":"ASYNCHRONOUS_RESPONSE. Please try again later."}]}'), Resp(200, "2026-09-08")]
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: answers.pop(0))
    monkeypatch.setattr(E.time, "sleep", lambda s: None)
    assert E.fetch("https://x", {})["updated"] == "2026-09-08"
    monkeypatch.setattr(E.requests, "get", lambda *a, **k: Resp(413, "ASYNCHRONOUS_RESPONSE"))
    with pytest.raises(E.FetchError, match="still preparing"):
        E.fetch("https://x", {}, attempts=3)


def _statcan_zip(rows: list[tuple], released=(2026, 9, 16, 0, 13, 4)) -> bytes:
    """(year, geo, dguid, measure, crop, uom, value, status) → the table's zip, dated as released."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["REF_DATE", "GEO", "DGUID", "Harvest disposition", "Type of crop", "UOM", "UOM_ID", "SCALAR_FACTOR",
                "SCALAR_ID", "VECTOR", "COORDINATE", "VALUE", "STATUS", "SYMBOL", "TERMINATED", "DECIMALS"])
    for y, geo, dguid, measure, crop, uom, value, status in rows:
        w.writerow([y, geo, dguid, measure, crop, uom, "", "units", "0", "", "", value, status, "", "", "0"])
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(zipfile.ZipInfo("32100359.csv", date_time=released), buf.getvalue().encode("utf-8-sig"))
    return out.getvalue()


def test_statcan_reads_canada_and_provinces_and_sets_aside_the_season_in_progress():
    """E160: StatCan 32-10-0359-01 — Canada (DGUID …11124) national, a province by the ISO code Statistics Canada states
    for its SGC code (Saskatchewan 47 → CA-SK), metric units as published (yield kg/ha ÷ 1,000); aggregates of provinces,
    unpublished values ('..', 'F', 'x') and the year of a release before December (model-based, before the November
    survey) set aside."""
    from services.reference import regions
    from services.reference import statcan_crops as C
    P, A, Y = "Production (metric tonnes)", "Harvested area (hectares)", "Average yield (kilograms per hectare)"
    rows = [(2025, "Canada", "2021A000011124", P, "Wheat, durum", "Metric tonnes", "7304979", ""),
            (2025, "Canada", "2021A000011124", A, "Wheat, durum", "Hectares", "2593000", ""),
            (2025, "Canada", "2021A000011124", Y, "Wheat, durum", "Kilograms per hectare", "2817", ""),
            (2025, "Saskatchewan", "2021A000247", P, "Wheat, durum", "Metric tonnes", "5000000", ""),
            (2024, "Saskatchewan", "2021A000247", P, "Wheat, durum", "Metric tonnes", "4000000", "r"),
            (2025, "Manitoba", "2021A000246", P, "Wheat, durum", "Metric tonnes", "", "x"),
            (2025, "Prairie provinces", "2021A00014", P, "Wheat, durum", "Metric tonnes", "7000000", ""),
            (2026, "Canada", "2021A000011124", P, "Wheat, durum", "Metric tonnes", "6417049", "")]
    data = _statcan_zip(rows)
    got = {(r["region_code"], r["season_year"]): r for r in C.parse(data, regions.ca_sgc_codes())}
    assert set(got) == {("", 2025), ("CA-SK", 2025), ("CA-SK", 2024)}
    r = got[("", 2025)]
    assert (r["commodity"], r["country"], r["production_tonnes"], r["area_harvested_ha"], r["yield_tonnes_ha"]) == \
           ("Durum wheat", "CA", 7304979.0, 2593000.0, 2.817)
    assert got[("CA-SK", 2025)]["yoy_change_pct"] == 25.0
    assert C.set_aside(data, regions.ca_sgc_codes()) == {
        "an aggregate of provinces (Prairie provinces)": 1, "not published (suppressed (confidentiality))": 1,
        "season in progress — released before the November survey's final production": 1}
    december = _statcan_zip(rows, released=(2026, 12, 4, 0, 0, 0))     # after the November survey: the year is read
    assert ("", 2026) in {(r["region_code"], r["season_year"]) for r in C.parse(december, regions.ca_sgc_codes())}


def test_canada_provinces_come_from_statistics_canadas_table_b():
    """E160: the 13 provinces and territories with the ISO 3166-2 codes Statistics Canada's SGC 2021 Table B states."""
    from services.reference import regions
    assert len(regions.of_country("CA")) == 13 and regions.ca_sgc_codes()["47"] == "CA-SK"
    assert regions.known("CA-QC") and not regions.known("CA-XX")
