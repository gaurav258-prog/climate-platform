"""A site's year-end values (ESRS E1: the carrying amount of assets at the reporting date, the year's net revenue) through
the intake pipeline, in one rolled-back transaction:

  sites file      two sites with the customer's own ids, when they were held, their area — via the company_sites sector
  year-end file   per site and period: the carrying amount (closing rate of the period end) and the year's net revenue
                  (average rate of the year) in any currency — landed as append-only statements
  next file       a changed carrying amount is a NEW statement; the live value is the latest, the first is kept
  refused rows    an unknown site, a period the site was not held, a closed period, a negative amount — each with its
                  reason, nothing written
"""
from __future__ import annotations

import uuid
from datetime import date

import pandas as pd
import pytest
from sqlalchemy import text

from services.intake import pipeline
from services.intake.money import convert_amount

pytestmark = pytest.mark.integration


def _manufacturer(s):
    return s.execute(text("""SELECT o.org_id::text, u.user_id::text FROM organizations o JOIN users u ON u.org_id = o.org_id
                             WHERE o.type = 'manufacturer' AND u.role = 'admin' ORDER BY o.name LIMIT 1""")).one()


def _csv(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode()


def test_year_end_values_land_as_statements_converted_by_the_rules_of_the_period(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _manufacturer(s)
    a, b, gone = f"YE-{tag}-A", f"YE-{tag}-B", f"YE-{tag}-C"
    sites = [{"site_name": f"TEST-YE-{tag}-{r}", "latitude": 39.47 + i / 100, "longitude": -0.37, "external_ref": r,
              "held_from": "2019-01-01", "site_area_ha": 12.5, "held_until": "2025-06-30" if r == gone else None}
             for i, r in enumerate((a, b, gone))]
    out = pipeline.submit(s, org_id, "company_sites", _csv(sites), f"{tag}-sites.csv", user_id=user_id)
    assert out["state"] == "imported", out.get("controls", {}).get("gate")
    got = s.execute(text("""SELECT external_ref, area_ha, held_from::text, held_until::text FROM sc_company_sites
                            WHERE org_id = CAST(:o AS uuid) AND external_ref LIKE :t ORDER BY external_ref"""),
                    {"o": org_id, "t": f"YE-{tag}-%"}).all()
    assert [tuple(r) for r in got] == [(a, 12.5, "2019-01-01", None), (b, 12.5, "2019-01-01", None),
                                       (gone, 12.5, "2019-01-01", "2025-06-30")]

    pe = "2025-12-31"
    # a file with rows that cannot land: held for a second person, nothing written, every refused row with its reason
    bad = [{"site_ref": f"NOPE-{tag}", "book_date": pe, "carrying_amount_eur": 1, "currency": "EUR"},
           {"site_ref": gone, "book_date": pe, "carrying_amount_eur": 1, "currency": "EUR"},
           {"site_ref": a, "book_date": pe, "carrying_amount_eur": 7, "currency": "EUR"}]
    out = pipeline.submit(s, org_id, "site_year_end_values", _csv(bad), f"{tag}-bad.csv", user_id=user_id,
                          reason="checking what is refused and why")
    assert out["state"] == "awaiting_approval", out
    rejected = {e["row"]: " ".join(e["problems"]) for e in out["errors"]}
    assert "is not one of your sites" in rejected[2] and "was not held on 2025-12-31" in rejected[3] and 4 not in rejected
    assert not s.execute(text("SELECT 1 FROM site_period_values WHERE org_id = CAST(:o AS uuid) AND batch_id = CAST(:b AS uuid)"),
                         {"o": org_id, "b": out["batch_id"]}).first()

    values = [{"site_ref": a, "book_date": pe, "carrying_amount_eur": 1_000_000, "net_revenue_eur": 3_000_000, "currency": "EUR"},
              {"site_ref": b, "book_date": pe, "carrying_amount_eur": 2_000_000, "net_revenue_eur": 5_000_000, "currency": "USD"}]
    out = pipeline.submit(s, org_id, "site_year_end_values", _csv(values), f"{tag}-ye.csv", user_id=user_id)
    assert out["state"] == "imported", out.get("controls", {}).get("gate")

    live = {(r[0], r[1]): (float(r[2]), float(r[3]), r[4]) for r in s.execute(text("""
        SELECT c.external_ref, v.measure, v.amount, v.amount_eur, v.currency FROM v_site_period_values_live v
        JOIN sc_company_sites c ON c.site_id = v.site_id WHERE v.org_id = CAST(:o AS uuid) AND c.external_ref LIKE :t"""),
        {"o": org_id, "t": f"YE-{tag}-%"}).all()}
    assert live[(a, "carrying_amount")] == (1_000_000, 1_000_000, "EUR")
    usd_bs = convert_amount(s, 2_000_000, "USD", date(2025, 12, 31), flow=False, org_id=org_id)    # IAS 21: closing rate
    usd_fl = convert_amount(s, 5_000_000, "USD", date(2025, 12, 31), flow=True, org_id=org_id)     # the year's average
    assert live[(b, "carrying_amount")] == (2_000_000, usd_bs["eur"], "USD")
    assert live[(b, "net_revenue")] == (5_000_000, usd_fl["eur"], "USD")

    # finance restates nothing, it corrects before the close: the new figure is a new statement, the first is kept
    fix = [{"site_ref": a, "book_date": pe, "carrying_amount_eur": 1_100_000, "net_revenue_eur": 3_000_000, "currency": "EUR"}]
    out = pipeline.submit(s, org_id, "site_year_end_values", _csv(fix), f"{tag}-ye2.csv", user_id=user_id,
                          reason="impairment booked after the first run (+10 %)")
    assert out["state"] == "imported", out.get("controls", {}).get("gate")
    hist = s.execute(text("""SELECT amount FROM site_period_values v JOIN sc_company_sites c ON c.site_id = v.site_id
                             WHERE c.external_ref = :r AND v.measure = 'carrying_amount' ORDER BY v.seq"""), {"r": a}).scalars().all()
    assert [float(x) for x in hist] == [1_000_000, 1_100_000]

    # the period closes (four eyes); a value for it is then refused at check time, with its reason
    other = s.execute(text("SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) AND user_id <> CAST(:u AS uuid) LIMIT 1"),
                      {"o": org_id, "u": user_id}).scalar()
    ent = s.execute(text("SELECT entity_id::text FROM sc_company_sites WHERE external_ref = :r"), {"r": a}).scalar()
    s.execute(text("""INSERT INTO reporting_period_close (org_id, reporting_entity_id, period_end, requested_by, approved_by)
                      VALUES (CAST(:o AS uuid), CAST(:e AS uuid), :pe, CAST(:m AS uuid), CAST(:c AS uuid))"""),
              {"o": org_id, "e": ent, "pe": pe, "m": user_id, "c": other})
    late = [{"site_ref": a, "book_date": pe, "carrying_amount_eur": 1_200_000, "currency": "EUR"},
            {"site_ref": b, "book_date": "2026-06-30", "carrying_amount_eur": -5, "currency": "EUR"}]
    with pytest.raises(pipeline.IntakeError) as e:
        pipeline.submit(s, org_id, "site_year_end_values", _csv(late), f"{tag}-ye3.csv", user_id=user_id)
    problems = " ".join(p for err in e.value.body.get("errors", []) for p in err["problems"])
    assert "is closed for this undertaking" in problems and "can't be negative" in problems
