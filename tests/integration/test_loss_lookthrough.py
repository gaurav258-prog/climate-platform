"""The holdings look-through of the loss engine (the product owner's decisions of 2026-10-22). Rolled back throughout.

  sites       the issuers' sites are a book of their own; a site states no value, so its figure is the share of the value
              its curve applies to — recorded as a share, never as euros; a head-office proxy is no physical site
  A           the share of the issuer's physical value lost per year: weight × tested share, over the sites whose weight
              counts as value (assets always; another basis only when the organisation states it); a held or untested
              figure, and a curve that gives a building's share only (flood), never carried; the rest named
  B           euros on the holding: A × the issuer's physical asset value × the holding's share of the issuer (its value
              ÷ the enterprise value) — each input missing is a named gap, a holding above the whole company too
  upload      the physical asset value arrives with the holding, in euros or converted at its date's closing rate"""
from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.loss import curves, engine, lookthrough
from tests.integration.test_loss_engine import LAT, LON, _flood_samples, _storm_samples

pytestmark = pytest.mark.integration
ORG = "0bbe0bbe-0000-4000-8000-000000316b01"
FAMILIES = {"loss_curve_family_storm": "eberenz_2021_rmsf", "loss_curve_family_flood": "jrc_huizinga_2017"}


def _manager(s, elections: dict | None = None) -> str:
    if not {"eberenz_2021_rmsf", "jrc_huizinga_2017"} <= set(curves.families()):
        pytest.skip("the cyclone and JRC families are not built on this machine")
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (:o, 'look-through test', "
                   "'asset_manager', 'US')"), {"o": ORG})
    s.execute(text("""INSERT INTO org_calc_settings (org_id, interpretation, updated_at)
                      VALUES (CAST(:o AS uuid), CAST(:i AS jsonb), now())"""),
              {"o": ORG, "i": json.dumps({**FAMILIES, **(elections or {})})})
    return ORG


def _elect(s, **elections) -> None:
    s.execute(text("""UPDATE org_calc_settings SET interpretation = interpretation || CAST(:i AS jsonb)
                      WHERE org_id = CAST(:o AS uuid)"""), {"o": ORG, "i": json.dumps(elections)})


def _holding(s, sites: list[dict], mv: float = 2_000_000.0, isin: str = "US00LOOK0001") -> tuple[str, str, str]:
    """A fund holding one company's security; the company's sites as given. Returns (fund, issuer, position)."""
    fund = s.execute(text("""INSERT INTO funds (org_id, name, fund_type, sfdr_classification, base_currency)
                             VALUES (:o, :n, 'fund', 'article_8', 'EUR') RETURNING fund_id::text"""),
                     {"o": ORG, "n": f"look-through fund {isin}"}).scalar()
    issuer = s.execute(text("""INSERT INTO issuers (name, issuer_type, country, source) VALUES ('Gulf Plants Inc',
                               'corporate', 'US', 'manual') RETURNING issuer_id::text""")).scalar()
    sec = s.execute(text("""INSERT INTO securities (isin, name, issuer_id, asset_class, currency)
                            VALUES (:i, 'Gulf Plants', CAST(:iss AS uuid), 'equity', 'USD') RETURNING security_id::text"""),
                    {"i": isin, "iss": issuer}).scalar()
    pos = s.execute(text("""INSERT INTO fund_positions (fund_id, security_id, market_value_eur, as_of_date)
                            VALUES (CAST(:f AS uuid), CAST(:s AS uuid), :mv, '2026-09-30') RETURNING position_id::text"""),
                    {"f": fund, "s": sec, "mv": mv}).scalar()
    for x in sites:
        s.execute(text("""INSERT INTO issuer_facilities (issuer_id, name, facility_type, latitude, longitude, country,
                                                         materiality_weight, weight_basis, source)
                          VALUES (CAST(:i AS uuid), :name, :type, :lat, :lon, :country, :w, :basis, :source)"""),
                  {"i": issuer, "name": "site", "type": "plant", "lat": LAT, "lon": LON, "country": "US", "w": 1.0,
                   "basis": "assets", "source": "manual", **x})
    return fund, issuer, pos


def _site_results(s, run_id: str) -> dict:
    return {(r["asset_id"], r["peril"]): dict(r) for r in s.execute(text("""
        SELECT r.*, r.asset_id::text AS asset_id, f.name FROM loss_results r
        JOIN issuer_facilities f ON f.facility_id = r.asset_id WHERE r.run_id = CAST(:r AS uuid)"""), {"r": run_id}).mappings()}


def _two_site_company(s, monkeypatch, standing: str = "published"):
    """A plant (60% of the company's assets) and an office weighted by revenue (40%) on a cyclone coast, the office
    seeing stronger winds; both in flood maps. Every figure's curve treated as `standing`."""
    org = _manager(s)
    fund, issuer, pos = _holding(s, [{"name": "Plant", "w": 0.6},
                                     {"name": "Office", "type": "office", "lat": LAT + 0.01, "w": 0.4, "basis": "revenue"}])
    _storm_samples(s, at_100=40.0)
    _storm_samples(s, lat=LAT + 0.01, at_100=55.0)
    _flood_samples(s)
    _flood_samples(s, lat=LAT + 0.01)
    monkeypatch.setattr(engine, "standing", lambda f, c, cv=None, p=None: standing)
    run = engine.run(s, org, "issuer_sites")
    return org, fund, issuer, pos, run


def test_a_site_figure_is_the_share_of_its_value_never_euros(session_rolled_back, monkeypatch):
    s = session_rolled_back
    org, fund, issuer, pos, run = _two_site_company(s, monkeypatch)
    res = _site_results(s, run["run_id"])
    plant = next(r for (a, p), r in res.items() if r["name"] == "Plant" and p == "storm")
    assert plant["asset_kind"] == "issuer_site" and plant["gap"] is None
    assert plant["eal_eur"] is None and plant["exposed_value_eur"] is None and plant["loss_at_rp"] is None
    curve = next(c for c in curves.families()["eberenz_2021_rmsf"]["curves"] if c["key"] == plant["curve_key"])
    assert plant["ratio_at_rp"]["100"]["central"] == pytest.approx(curves.ratio(curve["points"], 40.0 / 0.88), abs=1e-12)
    assert 0 < plant["eal_ratio_low"] <= plant["eal_ratio"] <= plant["eal_ratio_high"] <= 1
    inputs = s.execute(text("SELECT inputs FROM loss_runs WHERE run_id = CAST(:r AS uuid)"), {"r": run["run_id"]}).scalar()
    assert "issuer site" in inputs["value_basis"]
    with pytest.raises(ValueError):                              # a projected share: not assessed (yet)
        engine.run(s, org, "issuer_sites", "disorderly_2c", "2050")


def test_the_issuers_share_lost_is_the_weighted_sum_of_tested_shares(session_rolled_back, monkeypatch):
    s = session_rolled_back
    org, fund, issuer, pos, run = _two_site_company(s, monkeypatch)
    res = _site_results(s, run["run_id"])
    share = {r["name"]: r["eal_ratio"] for (a, p), r in res.items() if p == "storm"}
    a = lookthrough.issuers(s, org, [issuer])["issuers"][issuer]
    assert a["why"] is None and a["share"] == pytest.approx(0.6 * share["Plant"])     # the office's revenue weight: no
    assert a["covered"] == pytest.approx(0.6) and a["counted"] == pytest.approx(0.6)
    office = next(x for x in a["sites"] if x["name"] == "Office")
    assert not office["counts"] and office["why"]["code"] == "lookthrough.site.basis_not_accepted"
    assert "revenue" in office["why"]["label"]
    plant = next(x for x in a["sites"] if x["name"] == "Plant")
    flood = next(h for h in plant["hazards"] if h["peril"] == "flood")
    assert flood["share"] is None and flood["why"]["code"] == "lookthrough.site.building_only"   # decided 2026-10-22
    _elect(s, loss_site_weight_revenue=lookthrough.COUNTS)      # the organisation states revenue weights count
    a = lookthrough.issuers(s, org, [issuer])["issuers"][issuer]
    assert a["share"] == pytest.approx(0.6 * share["Plant"] + 0.4 * share["Office"])
    assert a["share_low"] <= a["share"] <= a["share_high"] and a["covered"] == pytest.approx(1.0)
    assert a["hazards"]["storm"]["covered"] == pytest.approx(1.0) and a["hazards"]["flood"]["covered"] == 0


def test_an_untested_or_failed_figure_is_never_carried(session_rolled_back, monkeypatch):
    s = session_rolled_back
    org, fund, issuer, pos, run = _two_site_company(s, monkeypatch, standing="untested")
    a = lookthrough.issuers(s, org, [issuer])["issuers"][issuer]
    assert a["share"] is None and a["why"]["code"] == "lookthrough.gap.no_tested_figure"
    plant = next(x for x in a["sites"] if x["name"] == "Plant")
    assert {h["why"]["code"] for h in plant["hazards"] if h["peril"] != "coastal_flood"} == {"lookthrough.site.untested"}
    monkeypatch.setattr(engine, "standing", lambda f, c, cv=None, p=None: "held")
    engine.run(s, org, "issuer_sites")
    a = lookthrough.issuers(s, org, [issuer])["issuers"][issuer]
    assert a["why"]["code"] == "lookthrough.gap.no_tested_figure" and a["not_carried"].get("lookthrough.site.held") == 2


def test_what_stops_the_share_is_named(session_rolled_back, monkeypatch):
    s = session_rolled_back
    org = _manager(s)
    _, nothing, _ = _holding(s, [], isin="US00LOOK0002")
    _, hq, _ = _holding(s, [{"name": "Registered headquarters", "type": "hq", "w": 1.0, "basis": "equal", "source": "osm"}],
                        isin="US00LOOK0003")
    _, over, _ = _holding(s, [{"w": 0.7}, {"w": 0.5, "lat": LAT + 0.01}], isin="US00LOOK0004")
    _, equal, _ = _holding(s, [{"w": 1.0, "basis": "equal"}], isin="US00LOOK0005")

    def why() -> dict:
        return {i: v["why"]["code"] for i, v in lookthrough.issuers(s, org, [nothing, hq, over, equal])["issuers"].items()}
    assert why()[over] == "lookthrough.gap.no_run"                       # no run of the issuers' sites yet
    _storm_samples(s)
    _storm_samples(s, lat=LAT + 0.01)
    monkeypatch.setattr(engine, "standing", lambda f, c, cv=None, p=None: "published")
    run = engine.run(s, org, "issuer_sites")
    assert why() == {nothing: "lookthrough.gap.no_sites", hq: "lookthrough.gap.head_office_only",
                     over: "lookthrough.gap.weights_exceed", equal: "lookthrough.gap.no_weighted_site"}
    proxy = [r for r in _site_results(s, run["run_id"]).values() if r["name"] == "Registered headquarters"]
    assert {r["gap_code"] for r in proxy} == {"loss.gap.head_office_only"}   # never sampled, never a figure
    _elect(s, **{lookthrough.switch(b): lookthrough.COUNTS for b in lookthrough.STATED_BASES})
    assert why()[equal] == "lookthrough.gap.no_weighted_site"            # an equal weight never counts


def test_euros_on_the_holding_are_the_share_times_physical_value_times_its_part(session_rolled_back, monkeypatch):
    s = session_rolled_back
    org, fund, issuer, pos, run = _two_site_company(s, monkeypatch)
    out = lookthrough.holdings(s, org, [fund])
    h = out["positions"][0]
    assert h["eur"] is None and h["why"]["code"] == "lookthrough.gap.no_physical_value" and out["eur"] is None
    s.execute(text("""INSERT INTO issuer_emissions (issuer_id, org_id, reporting_year, physical_asset_value_eur, source)
                      VALUES (CAST(:i AS uuid), CAST(:o AS uuid), 2025, 300000000, 'client')"""), {"i": issuer, "o": org})
    assert lookthrough.holdings(s, org, [fund])["positions"][0]["why"]["code"] == "lookthrough.gap.no_enterprise_value"
    s.execute(text("""UPDATE issuer_emissions SET evic_eur = 1500000 WHERE issuer_id = CAST(:i AS uuid)"""), {"i": issuer})
    assert lookthrough.holdings(s, org, [fund])["positions"][0]["why"]["code"] == "lookthrough.gap.holding_exceeds_company"
    s.execute(text("""UPDATE issuer_emissions SET evic_eur = 800000000 WHERE issuer_id = CAST(:i AS uuid)"""), {"i": issuer})
    out = lookthrough.holdings(s, org, [fund])
    h = out["positions"][0]
    assert h["why"] is None and h["holding_share"] == pytest.approx(2e6 / 8e8)
    assert h["eur"] == pytest.approx(h["share"] * 3e8 * 2e6 / 8e8)
    assert h["eur_low"] <= h["eur"] <= h["eur_high"]
    assert out["eur"] == pytest.approx(h["eur"]) and out["covered_value_eur"] == pytest.approx(2e6)


def test_the_physical_asset_value_arrives_with_the_holding_at_its_closing_rate():
    from core.errors import UserError
    from services.funds.holding import Holding
    from services.funds.holding import financials_eur as _issuer_financials_eur
    from services.reference.fx import rate_for
    with pytest.raises(UserError) as refused:                     # its currency is never assumed
        Holding(isin="US0000000001", market_value_eur=1e6, physical_asset_value=4e9)
    assert refused.value.code == "filings.holding.financials_currency"
    with pytest.raises(UserError) as twice:
        Holding(isin="US0000000001", market_value_eur=1e6, physical_asset_value=4e9, physical_asset_value_eur=3e9,
                financials_currency="USD", reporting_year=2025)
    assert twice.value.code == "filings.holding.financials_twice"
    h = Holding(isin="US0000000001", market_value_eur=1e6, physical_asset_value=4e9, financials_currency="USD",
                reporting_year=2025)
    with get_session() as s:
        f = _issuer_financials_eur(s, h)
        assert f["physical_asset_value_eur"] == pytest.approx(round(4e9 * rate_for(s, "USD", date(2025, 12, 31))["rate"], 2))
        assert f["money_source"]["fields"]["physical_asset_value_eur"]["amount"] == 4e9
        assert _issuer_financials_eur(s, Holding(isin="US0000000001", market_value_eur=1e6,
                                                 physical_asset_value_eur=3e9))["physical_asset_value_eur"] == 3e9


def test_the_route_answers_in_customer_words():
    from fastapi.testclient import TestClient

    from api.main import app
    fund = "b5bf373d-b70b-4f65-87fb-11107bf93fa3"                 # Nordkap Global Equity Fund (demo)
    with TestClient(app) as client:
        tok = client.post("/v1/auth/login", json={"email": "admin@nordkap.demo", "password": "Demo!admin1"}).json()
        r = client.get(f"/v1/funds/{fund}/loss-lookthrough", headers={"Authorization": f"Bearer {tok['access_token']}"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["positions"] and all(p["why"] is None or p["why"]["label"] for p in d["positions"])
    assert d["accepted_bases"][0] == {"basis": "assets", "name": "assets"}
    assert all(set(w) >= {"code", "label", "detail", "count"} for w in d["why"])
