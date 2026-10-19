"""The agriculture screens' server, end to end on the demo data (UI standard, 2026-10-16): every refusal the sourcing
plots, own sites, map cells and COGS-at-risk routes send is a catalogue code in customer words — never an exception's
own text — and an edit naming another organisation's entity is refused, not answered with a server error. Inside one
rolled-back transaction."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core import messages
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
ADMIN = ("admin@terra.demo", "Demo!admin1")
ORG = "55555555-5555-4555-8555-555555555555"


def _refused(r, code: str, status: int) -> dict:
    assert r.status_code == status, r.text
    err = r.json()["error"]
    assert err["error"] == code and err["message"], err
    assert not messages.INTERNAL.search(" ".join([err["message"], *err["detail"].values()])), err
    return err


def _site(api) -> str:
    return api.s.execute(text("SELECT site_id::text FROM sc_company_sites WHERE org_id = CAST(:o AS uuid) LIMIT 1"),
                         {"o": ORG}).scalar()


def test_adding_a_plot_or_a_site_is_refused_in_customer_words(api):
    h = _login(api, *ADMIN)
    plot = {"plot_name": "Test plot", "commodity": "Olive oil", "latitude": 37.9, "longitude": -4.8,
            "annual_spend_eur": 1000, "currency": "EUR", "book_date": "2025-12-31"}
    _refused(api.post("/v1/supply/plots", headers=h, json={**plot, "commodity": "Moon cheese"}),
             "agri.location.unknown_commodity", 422)
    # what the sender declared, refused by the intake's own codes (one set of words for every amount entry)
    _refused(api.post("/v1/supply/plots", headers=h, json={**plot, "currency": "XXQ"}), "intake.refused.currency_unknown", 400)
    _refused(api.post("/v1/supply/plots", headers=h, json={**plot, "book_date": "2999-01-01"}),
             "intake.refused.book_date_future", 400)
    site = {"name": "Test site", "latitude": 37.9, "longitude": -4.8}
    _refused(api.post("/v1/supply/sites", headers=h, json={**site, "annual_value_eur": 5}), "agri.location.currency_missing", 422)
    _refused(api.post("/v1/supply/sites", headers=h, json={**site, "annual_value_eur": 5, "currency": "EUR"}),
             "agri.location.book_date_missing", 422)
    _refused(api.post("/v1/supply/sites", headers=h, json={**site, "held_from": "2024-01-01", "held_until": "2023-01-01"}),
             "agri.location.held_order", 422)
    _refused(api.post("/v1/supply/sites", headers=h, json={**site, "entity_id": str(uuid.uuid4())}),
             "agri.location.entity_not_yours", 422)


def test_an_edit_naming_another_organisations_entity_is_refused_not_a_server_error(api):
    """Before: the location service raised its own error while applying the edit and the route did not catch it, so
    the screen read 'Something went wrong' (the test client raises it)."""
    h = _login(api, *ADMIN)
    other = api.s.execute(text("SELECT entity_id::text FROM reporting_entities WHERE org_id <> CAST(:o AS uuid) LIMIT 1"),
                          {"o": ORG}).scalar()
    assert other, "the demo data holds another organisation's entity"
    _refused(api.patch(f"/v1/supply/site/{_site(api)}", headers=h, json={"entity_id": other}),
             "agri.location.entity_not_yours", 422)
    _refused(api.patch(f"/v1/supply/site/{_site(api)}", headers=h, json={}), "agri.location.no_changes", 400)


def test_a_site_with_year_end_values_is_not_deleted(api):
    h = _login(api, *ADMIN)
    site = _site(api)
    api.s.execute(text("""INSERT INTO site_period_values (org_id, site_id, period_end, measure, amount, currency, amount_eur,
                                                          source)
                          VALUES (CAST(:o AS uuid), CAST(:s AS uuid), DATE '2025-12-31', 'net_revenue', 1, 'EUR', 1,
                                  'manual_entry')"""),
                  {"o": ORG, "s": site})
    _refused(api.delete(f"/v1/supply/site/{site}", headers=h), "agri.site.has_year_end_values", 409)
    assert api.s.execute(text("SELECT 1 FROM sc_company_sites WHERE site_id = CAST(:s AS uuid)"), {"s": site}).first()


def test_map_cells_and_unknown_records_are_refused_in_customer_words(api):
    h = _login(api, *ADMIN)
    _refused(api.get("/v1/geo/cells?cells=zzz", headers=h), "agri.map.not_a_cell", 422)
    _refused(api.get("/v1/geo/cells?cells=,", headers=h), "agri.map.cell_count", 422)
    _refused(api.get("/v1/supply/commodity/not-an-id", headers=h), "error.not_found", 404)
    _refused(api.post(f"/v1/supply/commodity/{uuid.uuid4()}/override", headers=_login(api, "analyst@agrifood-authority.demo", "Demo!analyst1"),
                      json={"override_cogs_at_risk_p50_eur": 1, "reason": "x"}), "error.forbidden", 403)


def test_the_cogs_and_site_pages_get_catalogue_words(api):
    h = _login(api, *ADMIN)
    c = api.get("/v1/supply/summary", headers=h).json()["concentration"]
    assert c["method"]["code"] == "agri.concentration.method"
    assert all(f["code"].startswith("agri.concentration.") for f in c["flags"])
    sites = api.get("/v1/supply/sites", headers=h).json()
    assert sites["bi_note"] == messages.render("agri.site.bi_basis")["detail"]["what"]
    plot = api.s.execute(text("SELECT plot_id::text FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid) LIMIT 1"),
                         {"o": ORG}).scalar()
    assert "note" not in api.get(f"/v1/supply/plot/{plot}", headers=h).json()       # the stale 'v0 … see docs/…' note


def test_a_fault_in_the_cell_service_is_never_read_as_a_bad_cell_id(api, monkeypatch):
    """Before: the route caught every error of the cell service and answered '… is not an H3 cell id', so a fault of
    ours (a missing land layer) read as the caller's mistake. A valid id now reaches the service and its fault is ours."""
    import services.geo.cells as cells

    def broken(cell):
        raise RuntimeError("land layer missing")
    monkeypatch.setattr(cells, "cell_shape", broken)
    h = _login(api, *ADMIN)
    with pytest.raises(RuntimeError, match="land layer missing"):
        api.get("/v1/geo/cells?cells=881c84d633fffff", headers=h)
