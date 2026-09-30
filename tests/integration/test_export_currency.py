"""Multi-currency phase 1c: regulatory packages never sum values across currencies unconverted. The CSRD package and
its XBRL export are retired (the ESRS statement is filed per undertaking, report type esrs_pack)."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory import ecb
from services.reference.fx import rate_for

pytestmark = pytest.mark.integration
END = date.today()


def _customer_with_scores(s):
    return s.execute(text("""
        SELECT cl.customer_id::text FROM customer_locations cl JOIN canonical_scores cs ON cs.h3_cell = cl.h3_cell_r8
        WHERE cl.is_active AND cs.valid_to IS NULL AND cs.time_horizon = 'current'
        GROUP BY cl.customer_id LIMIT 1""")).scalar()


def test_location_values_are_converted_and_unrated_ones_left_out():
    builder = ecb
    with get_session() as s:
        cust = _customer_with_scores(s)
        if not cust:
            pytest.skip("no scored customer locations")
        try:
            first = s.execute(text("""SELECT location_id FROM customer_locations WHERE customer_id = CAST(:c AS uuid) AND is_active
                                      LIMIT 1"""), {"c": cust}).scalar()
            second = s.execute(text("""INSERT INTO customer_locations (customer_id, location_name, latitude, longitude, h3_cell_r8,
                                           h3_cell_r7, asset_type, asset_value, currency)
                                       SELECT customer_id, 'TEST twin', latitude, longitude, h3_cell_r8, h3_cell_r7, asset_type, 1, 'EUR'
                                       FROM customer_locations WHERE location_id = :l RETURNING location_id"""), {"l": first}).scalar()
            locs = [first, second]
            s.execute(text("UPDATE customer_locations SET currency = 'USD', asset_value = 1000000 WHERE location_id = :l"), {"l": locs[0]})
            s.execute(text("UPDATE customer_locations SET currency = 'XTS', asset_value = 5000000 WHERE location_id = :l"), {"l": locs[1]})
            pkg = builder.build(s, cust, date(2000, 1, 1), END)
            fx = pkg["t5_methodology"]["currency"]
            assert pkg["reporting_currency"] == "EUR"
            assert "XTS" in fx["excluded_values"] and "XTS" in fx["note"]
            usd = next(r for r in fx["rates"] if r["currency"] == "USD")
            assert usd["units_per_eur"] == pytest.approx(rate_for(s, "USD", END)["units_per_eur"])
        finally:
            s.rollback()


def test_the_csrd_package_and_its_xbrl_are_retired():
    from fastapi.testclient import TestClient

    from api.main import app
    from ml.regulatory.packager import PackagerError, create_package
    r = TestClient(app).get("/v1/packages/00000000-0000-0000-0000-000000000000/xbrl", params={"lei": "5493001KJTIIGC8Y1R12"})
    assert r.status_code == 410 and "esrs_pack" in r.text
    with pytest.raises(PackagerError, match="retired"):
        create_package("00000000-0000-0000-0000-000000000000", "CSRD", date(2025, 1, 1), date(2025, 12, 31), "maker")
