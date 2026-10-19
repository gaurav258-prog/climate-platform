"""The observed record speaks facts in customer words (UI standard, 2026-10-16; facts only): the Climate track record,
the Underwriting review, the realised-exposure card and the general-ledger reconciliation send catalogue messages (codes
realized.* and ledger.*), names from the catalogue's names blocks and the catalogues' own figures — never a raw reason
code, a sentence written where it arose, a modelled score as a place's observed record, or a check on another peril's
price. End to end through the real API, rolled back."""
from __future__ import annotations

import pytest

from core.messages import INTERNAL, catalogue, names
from tests.integration.conftest import login

IBERIA = ("admin@iberia.demo", "Demo!admin1")          # insurer demo: a located policy book priced on a stated method
MERIDIAN = ("admin@meridian.demo", "Demo!admin1")      # bank demo: a located book and an uploaded ledger
TERRA = ("admin@terra.demo", "Demo!admin1")            # food-manufacturer demo: a sourcing book
IBERIA_ORG = "22222222-2222-4222-8222-222222222222"
WORDS = {"label", "what", "why", "next", "strength", "verdict_name", "scale_name", "peril_name"}
GONE = {"reason", "note", "headline", "method"}       # the old sentence and code fields: none comes back as text


def _as(api, who):
    api.h = login(api, *who)
    return api


def _walk(x, path=""):
    if isinstance(x, dict):
        if {"code", "label", "detail"} <= set(x):
            assert x["code"] in catalogue(), (path, x["code"])
        for k, v in x.items():
            if k in WORDS and isinstance(v, str):
                assert not INTERNAL.search(v), (f"{path}.{k}", v)
            if k in GONE:
                assert not isinstance(v, str), (f"{path}.{k}", v)
            if k == "verdict" and v is not None:                  # a check's reading is a code the names block words
                assert v in names()["realized.verdict"], (f"{path}.{k}", v)
            _walk(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _walk(v, f"{path}[{i}]")


def test_every_word_the_observed_record_sends_is_a_catalogue_word(api):
    _as(api, IBERIA)
    for path in ("/v1/realized-exposure", "/v1/realized-exposure/underwriting-review",
                 "/v1/realized-exposure/track-record?lat=37.5&lon=15.09", "/v1/realized-exposure/track-record?lat=37.95&lon=-8.87",
                 "/v1/gl/reconciliation"):
        r = api.get(path, headers=api.h)
        assert r.status_code == 200, (path, r.text)
        _walk(r.json(), path)
    _as(api, MERIDIAN)
    for path in ("/v1/realized-exposure", "/v1/gl/reconciliation"):
        _walk(api.get(path, headers=api.h).json(), path)


def test_a_storm_reads_in_its_best_track_class(api):
    ev = _as(api, IBERIA).get("/v1/realized-exposure", headers=api.h).json()["events"]
    classes = set(names()["realized.storm_class"].values())
    storms = [e for e in ev if e["kind"] == "storm"]
    assert storms and all(e["strength"] in classes for e in storms)
    assert all(e["strength"] != "Tropical depression" or e["category"] == -1 for e in storms)    # only a real -1 reads so


def test_a_fall_in_national_production_is_called_that_not_a_yield_shock(api):
    # crop_yield_observations.yoy_change_pct is the change in production tonnes (scripts/ingest_crop_yield.py)
    d = _as(api, TERRA).get("/v1/realized-exposure", headers=api.h).json()
    assert d["available"] and d["message"]["code"] == "realized.book.crops" and d["events"]
    assert all(e["kind"] == "crop_shock" and e["strength"] == f"{e['yoy_change_pct']} % production" for e in d["events"])
    assert "yield" not in d["message"]["label"].lower()


def test_a_places_highest_hazard_is_on_a_likelihood_scale_and_kept_apart_from_its_record(api):
    d = _as(api, IBERIA).get("/v1/realized-exposure/track-record?lat=37.5&lon=15.09", headers=api.h).json()
    scored = {h["hazard"]: h for h in d["current_risk"]}
    assert scored, "the Sicily example is scored"
    top = d["headline_current"]
    assert top["scale"] == "intensity" and top["score"] == max(h["score"] for h in scored.values() if h["headline"])
    if "heat_acute" in scored:                                      # today's reading: context, never the highest hazard
        assert not scored["heat_acute"]["headline"] and scored["heat_acute"]["scale_name"] == "Today's reading"
    assert all(h["label"] == names()["hazard"][h["hazard"]] for h in scored.values())
    assert d["realized"]["message"]["code"] == "realized.place.crossed" and d["modelled"]["context"]
    assert "verdict" not in d and "note" not in d             # the old fused sentence and its footnote are gone


def test_every_policy_priced_on_a_catalogued_peril_is_checked_on_that_perils_own_return_period(api):
    from api.routers.insurance import build_disclosure_snapshot
    rv = _as(api, IBERIA).get("/v1/realized-exposure/underwriting-review", headers=api.h).json()
    f = rv["frequency"]
    policies = [p for p in build_disclosure_snapshot(api.s, IBERIA_ORG, "baseline", "current")["policies"]
                if p.get("lat") is not None and p.get("lon") is not None]
    own = {(p["policy_id"], c["hazard"]): c["return_period_years"] for p in policies
           for c in (p.get("pricing") or {}).get("perils") or [] if c["hazard"] in ("storm", "seismic") and c["return_period_years"]}
    assert f["n_checks"] == len(own)                                # every catalogued priced peril, not only the headline
    assert f["n_policies_checked"] == len({pid for pid, _ in own})
    assert f["n_policies_checked"] + f["n_uncatalogued"] + f["n_unpriced"] + f["n_no_return_period"] == rv["n_policies"]
    for c in f["flagged"]:
        assert c["priced_return_period_years"] == own[(c["policy_id"], c["peril"])]
        assert c["verdict"] == "more_often" and c["ratio"] >= 1 + rv["definition"]["verdict_tolerance"]
    for p in f["by_peril"]:
        assert p["n_checks"] == p["n_more_often"] + p["n_in_line"] + p["n_less_often"] + p["n_no_verdict"]
    windows = {s["kind"]: s["years"] for s in rv["sources"]}
    assert set(windows) == {"storm", "earthquake"} and all(0 < y < 200 for y in windows.values())


def test_an_unavailable_review_says_why_in_words(api):
    r = _as(api, MERIDIAN).get("/v1/realized-exposure/underwriting-review", headers=api.h).json()
    assert r == {"available": False, "message": r["message"]} and r["message"]["code"] == "realized.unavailable.insurer_only"
    from services.intelligence.realized_exposure import realized_exposure
    assert realized_exposure(api.s, IBERIA_ORG, "public_sector")["message"]["code"] == "realized.unavailable.sector"


def test_the_ledger_refuses_and_skips_in_catalogue_words(api):
    _as(api, IBERIA)
    assert api.get("/v1/gl/reconciliation", headers=api.h).json()["message"]["code"] == "ledger.none"
    r = api.post("/v1/gl/rows", headers=api.h, json={"rows": [{"account_code": "", "balance": "5"}], "currency": "EUR",
                                                      "book_date": "2026-06-30"})
    assert r.status_code == 422 and r.json()["error"]["error"] == "ledger.error.no_rows"
    assert "Row 2" in r.json()["error"]["detail"]["what"]
    assert api.post("/v1/gl/rows", headers=api.h, json={"rows": []}).json()["error"]["error"] == "ledger.error.empty"
    ok = api.post("/v1/gl/rows", headers=api.h, json={"rows": [{"account_code": "T-1", "account_name": "test", "balance": "10"},
                                                               {"account_code": "T-2", "balance": "abc"}],
                                                      "currency": "EUR", "book_date": "2026-06-30"})
    assert ok.status_code == 201 and ok.json()["rows"] == 1
    (skip,) = ok.json()["skipped"]
    assert skip["row"] == 3 and skip["message"]["code"] == "ledger.row.not_used"
    rec = api.get("/v1/gl/reconciliation", headers=api.h).json()
    assert rec["available"] and rec["message"]["code"] == "ledger.rule"
    assert rec["gl_book_eur"] == round(sum(a["balance_eur"] for a in rec["accounts"] if a["counts"]))   # the rows foot


@pytest.mark.parametrize("who", [IBERIA])
def test_the_dossier_pdf_carries_no_internal_language(api, who):
    r = _as(api, who).get("/v1/realized-exposure/track-record.pdf?lat=37.5&lon=15.09&name=Plant", headers=api.h)
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    from services.intelligence.climate_track_record import track_record
    d = track_record(api.s, 37.5, 15.09, "Plant")
    for m in (d["realized"]["message"], d["modelled"]["message"]):
        assert not INTERNAL.search(" ".join([m["label"], *m["detail"].values()]))
