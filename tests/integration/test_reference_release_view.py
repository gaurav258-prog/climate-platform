"""The reference data releases page in customer words (UI standard, 2026-10-16): what the operator's screen gets is
the release's facts with every explanation a code of the message catalogue — the source by name, the rows set aside
by reason, the calibrations to re-check by place and driver, refusals as {error: code, message, detail} — and the
approval request a proposal opens is titled in customer words. Releases staged before reasons were codes read alike."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core import messages
from services.reference import crop_releases as R
from services.reference import faostat_crops as F
from services.reference import release_view as V
from tests.integration.conftest import login as _login
from tests.integration.test_crop_release_review import _zip

pytestmark = pytest.mark.integration
SRC = "FAOSTAT QCL view test"

# every reason the readers wrote as words before 2026-10-17, as stored releases hold them
LEGACY = {
    "area without a production estimate for the year": ("area_only", {}),
    "an area with no production figure": ("area_only", {}),
    "not given as a number ((D))": ("not_a_number", {"value": "(D)"}),
    "not published (suppressed (confidentiality))": ("not_published", {"why": "suppressed (confidentiality)"}),
    "not a state of the region reference (OTHER STATES)": ("state_group", {"name": "OTHER STATES"}),
    "an aggregate of provinces (Prairie provinces)": ("province_group", {"name": "Prairie provinces"}),
    "NASS's combined counties (OTHER (COMBINED) COUNTIES), not a county": ("combined_counties", {}),
    "not a county of the Census Bureau's 2020 county list (renamed or dissolved since)": ("not_a_county", {}),
    "season in progress — 'YEAR' repeats NASS's forecast": ("season_forecast", {}),
    "season in progress — released before the November survey's final production": ("season_preliminary", {}),
    "a national or aggregate figure (national series are read from apro_cpsh1)": ("national_figure", {}),
    "a NUTS-1 figure (regional series are read at NUTS-2)": ("larger_region", {}),
    "extra-regio (not a territory)": ("extra_regio", {}),
    "not a NUTS 2021 region (a region of an earlier or later NUTS version)": ("other_nuts_version", {}),
    "a summed crop with a part not published for the region and year": ("part_unpublished", {}),
}


def test_reasons_stored_as_words_read_as_the_same_codes():
    got = V.set_aside({why: 1 for why in LEGACY})
    assert all(a["code"] for a in got), [a["label"] for a in got if not a["code"]]
    for why, (reason, params) in LEGACY.items():
        assert V._legacy(why) == ("reference.release.aside." + reason, params), why
    assert not any(messages.INTERNAL.search(a["label"]) for a in got)
    assert V.set_aside([{"code": "reference.release.aside.not_a_number", "params": {"value": "(NA)"}, "rows": 3}]) == [
        {"code": "reference.release.aside.not_a_number", "label": "Not given as a number (NA)", "rows": 3,
         "detail": messages.render("reference.release.aside.not_a_number", value="(NA)")["detail"]}]


def test_places_and_drivers_are_named(session_rolled_back):
    places = V.Places(session_rolled_back)
    assert places("US", "US-IA-19001") == "Adair County, Iowa"
    assert places("US", "US-IA") == "Iowa, United States" and places("FR") == "France"
    assert places("ES", "ES51") == "ES51, Spain"                 # a NUTS 2 region: the official list holds no name
    assert V.driver("soil_water")["label"] == "Soil-water stress"


@pytest.fixture
def faostat(api, monkeypatch):
    from services.governance.platform_policy import PLATFORM_ORG
    monkeypatch.setattr(F, "source", lambda: SRC)
    api.s.execute(text("""UPDATE approval_policy SET human_approvers = 2
                          WHERE org_id = CAST(:o AS uuid) AND action_key = 'reference.release_land'"""), {"o": PLATFORM_ORG})
    return SRC


def test_the_page_reads_customer_words_and_refusals_are_codes(api, faostat):
    out = R.stage(api.s, _zip([(107, "Cocoa beans", "Production", 2050, 10.0),
                               (107, "Cocoa beans", "Area harvested", 2050, 5.0)]))
    rid = out["release_id"]
    ops = _login(api, "ops@tellumen.io", "Demo!ops1")
    page = api.get("/v1/ops/reference-releases", headers=ops).json()
    feed = next(f for f in page["feeds"] if f["source"] == "faostat")
    assert feed["name"] == "FAOSTAT crop production" and feed["about"]["what"] and "note" not in feed
    rel = next(r for r in page["releases"] if r["release_id"] == rid)
    assert rel["source_name"] == "FAOSTAT crop production" and rel["summary"]["set_aside"] == []
    detail = api.get(f"/v1/ops/reference-releases/{rid}?change=added", headers=ops).json()
    assert [(x["place"], x["season_year"]) for x in detail["rows"]] == [("Côte d’Ivoire", 2050)]

    short = api.post(f"/v1/ops/reference-releases/{rid}/propose", headers=ops, json={"reason": "short"})
    assert short.status_code == 409
    err = short.json()["error"]
    assert err["error"] == "reference.release.error.review_note_required" and err["message"] == "Say what you reviewed"
    assert err["detail"]["what"]
    bad = api.get(f"/v1/ops/reference-releases/{rid}?change=deleted", headers=ops)
    assert bad.status_code == 422 and bad.json()["error"]["error"] == "reference.release.error.unknown_change"

    p = api.post(f"/v1/ops/reference-releases/{rid}/propose", headers=ops, json={"reason": "checked the 2050 cocoa row"})
    title = api.s.execute(text("SELECT title FROM approval_requests WHERE request_id = CAST(:r AS uuid)"),
                          {"r": p.json()["approval_request_id"]}).scalar()
    assert title == "Apply the new FAOSTAT crop production release"
    again = api.post(f"/v1/ops/reference-releases/{rid}/propose", headers=ops, json={"reason": "checked the 2050 cocoa row"})
    assert again.status_code == 409
    assert again.json()["error"]["message"] == "This release is no longer awaiting review"

    pol = api.get("/v1/ops/reference-releases/policy", headers=ops).json()["policies"]
    assert {p["label"] for p in pol} == {"Applying a reference data release", "Publishing a crop calibration"}
    refused = api.put("/v1/ops/reference-releases/policy", headers=ops,
                      json={"action_key": "reference.release_land", "human_approvers": 3, "reason": "three people now"})
    assert refused.status_code == 422 and refused.json()["error"]["message"] == "Choose one or two approvers"
