"""The undertaking's own ESRS figures through the HTTP API (Terra Foods, one of its legal entities), rolled back:

  catalogue   what the governing version asks for depends on the financial year: FY2025 (as amended by 2025/1416)
              has the renewable-energy split, FY2027 (2026/1563) the direct biogenic CO2 instead; FY2026 follows the
              organisation's Art. 2 election
  submission  per undertaking and year, keyed by concept; a quantity has no currency; an amount must state one and is
              converted by the period's rule (net revenue at the year's average, total assets at the closing rate);
              a percentage over 100 and a concept the version does not print are refused
  breakdown   Scope 3 per GHG Protocol category: one live value per category, a category that does not exist refused
  attested    after the second person, the values come back with their currency, EUR amount and member
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from services.intake.money import convert_amount
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"


def _post(api, h, **body):
    return api.post("/v1/provided", headers=h, json={"framework": "esrs", "reporting_period_end": "2025-12-31", **body})


def test_esrs_figures_per_undertaking_and_year_in_their_own_currency(api):
    maker = _login(api, "analyst@terra.demo", "Demo!analyst1")
    checker = _login(api, "approver@terra.demo", "Demo!approve1")
    ent = api.s.execute(text("""SELECT entity_id::text FROM reporting_entities WHERE org_id = CAST(:o AS uuid)
                                AND parent_entity_id IS NOT NULL ORDER BY name LIMIT 1"""), {"o": TERRA}).scalar()

    cat = lambda pe: {d["key"]: d for d in api.get(f"/v1/provided/catalog?framework=esrs&period_end={pe}",   # noqa: E731
                                                   headers=maker).json()["datapoints"]}
    fy25, fy27 = cat("2025-12-31"), cat("2027-12-31")
    assert "e1.energy.renewable.fuel" in fy25 and "e1.energy.renewable.fuel" not in fy27
    assert "e1.ghg.biogenic_co2" in fy27 and "e1.ghg.biogenic_co2" not in fy25
    assert fy25["fs.net_revenue"]["currency_required"] and not fy25["e1.ghg.scope1.gross"]["currency_required"]
    assert fy25["e1.ghg.scope3.by_category"]["members"]["1"] == "Purchased goods and services"
    assert "e1.physrisk.assets.amount" not in fy25            # computed by the platform, never provided

    ok = lambda r: r.status_code == 201 and r.json()["approval_request_id"]      # noqa: E731
    s1 = _post(api, maker, datapoint_key="e1.ghg.scope1.gross", value_num=12500, reporting_entity_id=ent)
    assert ok(s1), s1.text
    assert _post(api, maker, datapoint_key="e1.ghg.scope1.gross", value_num=1, currency="EUR", reporting_entity_id=ent).status_code == 400
    assert _post(api, maker, datapoint_key="e1.ghg.scope1.eu_ets_pct", value_num=120, reporting_entity_id=ent).status_code == 400
    assert _post(api, maker, datapoint_key="fs.net_revenue", value_num=5e8, reporting_entity_id=ent).status_code == 400
    assert _post(api, maker, datapoint_key="e1.ghg.biogenic_co2", value_num=10, reporting_entity_id=ent).status_code == 400
    rev = _post(api, maker, datapoint_key="fs.net_revenue", value_num=5_000_000_000, currency="SEK", reporting_entity_id=ent)
    assets = _post(api, maker, datapoint_key="fs.total_assets", value_num=900_000_000, currency="USD", reporting_entity_id=ent)
    c1 = _post(api, maker, datapoint_key="e1.ghg.scope3.by_category", breakdown_member="1", value_num=80000, reporting_entity_id=ent)
    c4 = _post(api, maker, datapoint_key="e1.ghg.scope3.by_category", breakdown_member="4", value_num=9000, reporting_entity_id=ent)
    assert all(ok(r) for r in (rev, assets, c1, c4)), [r.text for r in (rev, assets, c1, c4)]
    assert _post(api, maker, datapoint_key="e1.ghg.scope3.by_category", breakdown_member="16", value_num=1,
                 reporting_entity_id=ent).status_code == 400
    assert _post(api, maker, datapoint_key="e1.ghg.scope3.by_category", value_num=1, reporting_entity_id=ent).status_code == 400
    for r in (s1, rev, assets, c1, c4):
        d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                     json={"decision": "approved", "reason": "agreed to the GHG inventory and the ledger"})
        assert d.status_code == 200, d.text

    from services.governance.provided_data import attested_values
    got = {v["key"]: v for v in attested_values(api.s, TERRA, "esrs", "2025-12-31", reporting_entity_id=ent)}
    assert got["provided.e1.ghg.scope1.gross"]["value"] == 12500 and got["provided.e1.ghg.scope1.gross"]["currency"] is None
    sek = convert_amount(api.s, 5_000_000_000, "SEK", date(2025, 12, 31), flow=True, org_id=TERRA)       # the year's average
    usd = convert_amount(api.s, 900_000_000, "USD", date(2025, 12, 31), flow=False, org_id=TERRA)        # the closing rate
    assert (got["provided.fs.net_revenue"]["currency"], got["provided.fs.net_revenue"]["value_eur"]) == ("SEK", sek["eur"])
    assert got["provided.fs.total_assets"]["value_eur"] == usd["eur"]
    assert got["provided.e1.ghg.scope3.by_category@1"]["value"] == 80000 and got["provided.e1.ghg.scope3.by_category@4"]["member"] == "4"
    # the organisation's own values are a different undertaking's: none of these is read for it
    assert not attested_values(api.s, TERRA, "esrs", "2025-12-31", reporting_entity_id=None)
