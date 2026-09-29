"""Values the institution supplies into a template cell — one mechanism (provided_data), per reporting period.

  * only a cell the governing spec has and the binding marks as supplied ('input:cell') is accepted, with its period
  * a new value supersedes only the same cell's value for the same period — another year's value is untouched
  * a filing freezes only its own period's attested values, and the form shows the frozen value
Runs inside a rolled-back transaction."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.governance import provided_data as P
from services.governance.filing_annex import build_annex
from tests.integration.test_intake_pipeline import BANK_ORG
from tests.unit.test_pillar3_grids import BOOK

pytestmark = pytest.mark.integration


@pytest.fixture()
def s(session_rolled_back):
    return session_rolled_back


def _uid(s, email):
    return s.execute(text("SELECT user_id::text FROM users WHERE email = :e"), {"e": email}).scalar()


def test_only_a_suppliable_cell_of_the_governing_spec_is_accepted(s):
    a = _uid(s, "admin@meridian.demo")
    with pytest.raises(P.ProvidedError, match="reporting period"):
        P.submit(s, BANK_ORG, a, framework="bank_p3esg", datapoint_key="T10.1.c", value_num=5.0)
    with pytest.raises(P.ProvidedError, match="not a value the institution supplies"):
        P.submit(s, BANK_ORG, a, framework="bank_p3esg", datapoint_key="T7.4.a", value_num=5.0, reporting_period_end="2025-12-31")
    with pytest.raises(P.ProvidedError, match="has no row"):
        P.submit(s, BANK_ORG, a, framework="bank_p3esg", datapoint_key="T10.99.c", value_num=5.0, reporting_period_end="2025-12-31")
    out = P.submit(s, BANK_ORG, a, framework="bank_p3esg", datapoint_key="T10.1.c", value_num=1250000.0,
                   reporting_period_end="2025-12-31")
    assert out["status"] == "pending"


def test_supersede_and_freeze_are_per_period(s):
    a, b = _uid(s, "admin@meridian.demo"), _uid(s, "approver@meridian.demo")
    for pe, v in (("2024-12-31", 100.0), ("2025-12-31", 200.0), ("2025-12-31", 250.0)):
        r = P.submit(s, BANK_ORG, a, framework="bank_p3esg", datapoint_key="T10.2.c", value_num=v, reporting_period_end=pe)
        P.attest(s, BANK_ORG, {"provided_id": r["provided_id"]}, "approved", b)
    live = {(x["reporting_period_end"], x["value_num"]) for x in P.provided_list(s, BANK_ORG, "bank_p3esg")
            if x["datapoint_key"] == "T10.2.c" and x["status"] == "attested"}
    assert live == {("2024-12-31", 100.0), ("2025-12-31", 250.0)}            # 2025's 200 superseded; 2024 untouched
    fy25 = {x["key"]: x["value"] for x in P.attested_values(s, BANK_ORG, "bank_p3esg", "2025-12-31")}
    assert fy25.get("provided.T10.2.c") == 250.0
    assert P.attested_values(s, BANK_ORG, "bank_p3esg", "2023-12-31") == []
    # the form shows the value frozen into the filing, keyed to the spec cell
    payload = {"assets": BOOK, "_spec": {"version": "its_2024_3172"},
               "_provided_attested": P.attested_values(s, BANK_ORG, "bank_p3esg", "2025-12-31")}
    t10 = next(x for x in build_annex("bank_p3esg", {}, [], payload)["sections"] if x.get("key") == "t10")
    cell = next(c for r in t10["rows"] if r["type"] == "row" for c in r["cells"] if c.get("key") == "T10.2.c")
    assert cell["supply"] == {"framework": "bank_p3esg", "key": "T10.2.c"} and "250" in cell["text"]
