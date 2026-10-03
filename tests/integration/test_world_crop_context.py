"""The world crop, year by year, as context (services.intelligence.world_crop): for olive oil 2012 the three figures
the decomposition gives (FAOSTAT reported −16.08 %, net −4.06 %, losses only −12.98 %); losses never above net; the
latest years named as not decomposable (the centred trend needs later years); a commodity without a FAOSTAT world
series says so instead of borrowing another crop's; never part of volume at risk (the route only reads)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration


def _id(s, name):
    return s.execute(text("SELECT commodity_id::text FROM sc_commodities WHERE name = :n"), {"n": name}).scalar()


def test_the_world_crop_is_shown_as_it_happened(api):
    who = _login(api, "analyst@terra.demo", "Demo!analyst1")
    r = api.get(f"/v1/supply/commodity/{_id(api.s, 'Olive oil')}/world-crop", headers=who)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["available"] and "not a forecast" in d["basis"]
    y = {x["year"]: x for x in d["years"]}
    assert (y[2012]["reported_pct"], y[2012]["net_pct"], y[2012]["losses_pct"]) == (-16.08, -4.06, -12.98)
    assert y[2012]["coverage_pct"] > 90
    done = [x for x in d["years"] if not x["why_not"]]
    assert done and all(x["losses_pct"] <= x["net_pct"] + 1e-9 and x["losses_pct"] <= 0 for x in done)
    last = d["years"][-1]
    assert last["net_pct"] is None and "later years" in last["why_not"]
    assert d["origins"]["rows"] and d["origins"]["year"] == done[-1]["year"]
    assert d["data_to_year"] == d["years"][-1]["year"] and d["loaded_at"]


def test_volume_at_risk_never_reads_the_world_crop_context():
    """Net figures include other origins' good years — volume at risk is damage-only, so its modules never read this."""
    import inspect

    import services.intelligence.supply_cogs as cogs
    src = inspect.getsource(cogs)
    assert "world_crop" not in src and "decomposed_net_shock_pct" not in src


def test_a_commodity_without_a_world_series_says_so(api):
    who = _login(api, "analyst@terra.demo", "Demo!analyst1")
    for name in ("Citrus", "Durum wheat"):
        d = api.get(f"/v1/supply/commodity/{_id(api.s, name)}/world-crop", headers=who).json()
        assert not d["available"] and name in d["reason"] and d["years"] == []
    assert api.get("/v1/supply/commodity/not-an-id/world-crop", headers=who).status_code in (404, 422)
