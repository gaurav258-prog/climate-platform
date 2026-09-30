"""The 'latest' of a history table is chosen by a strictly increasing number, not a timestamp (latest_by_sequence_20260930,
error log E52): two statements made in one transaction share now(), and the second must win.

  * asset_conflicts: the live decision on a fact is the last one resolved (resolved_seq), and that order is fixed
  * fx_client_rates: the live own rate for a key is the last one submitted (client_rate_id)
Runs inside a rolled-back transaction."""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from services.intake import observations as O
from services.reference import client_fx
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
TABLE = "portfolio_entities"


def _decide(s, aid: str, resolution: str) -> None:
    """Open a conflict on the asset's country and resolve it — both at now(), the transaction's one instant."""
    cid = s.execute(text("""
        INSERT INTO asset_conflicts (org_id, asset_table, asset_id, field, rule)
        VALUES (CAST(:o AS uuid), :t, CAST(:a AS uuid), 'country', 'test') RETURNING conflict_id::text
    """), {"o": BANK_ORG, "t": TABLE, "a": aid}).scalar()
    s.execute(text("""UPDATE asset_conflicts SET status = 'resolved', resolution = :r, resolved_at = now()
                      WHERE conflict_id = CAST(:c AS uuid)"""), {"r": resolution, "c": cid})


@pytest.mark.parametrize("first, second, ours_live", [("tellumen", "client", False), ("client", "tellumen", True)])
def test_the_second_decision_in_one_transaction_is_the_live_one(session_rolled_back, first, second, ours_live):
    s = session_rolled_back
    aid = str(uuid.uuid4())
    _decide(s, aid, first)
    _decide(s, aid, second)
    times = s.execute(text("SELECT DISTINCT resolved_at FROM asset_conflicts WHERE asset_id = CAST(:a AS uuid)"), {"a": aid}).all()
    assert len(times) == 1                                   # the tie the timestamp could not break
    assert ((aid, "country") in O._taken_from_us(s, TABLE, [aid])) is ours_live


def test_the_order_of_a_decision_is_fixed_once_made(session_rolled_back):
    s = session_rolled_back
    aid = str(uuid.uuid4())
    _decide(s, aid, "client")
    seq = s.execute(text("SELECT resolved_seq FROM asset_conflicts WHERE asset_id = CAST(:a AS uuid)"), {"a": aid}).scalar()
    s.execute(text("UPDATE asset_conflicts SET resolved_seq = resolved_seq + 1000, note = 'x' WHERE asset_id = CAST(:a AS uuid)"),
              {"a": aid})
    assert s.execute(text("SELECT resolved_seq FROM asset_conflicts WHERE asset_id = CAST(:a AS uuid)"), {"a": aid}).scalar() == seq


@pytest.mark.parametrize("second_at", ["now()", "now() - interval '1 minute'"])   # the same instant; a clock stepped back
def test_the_second_own_rate_in_one_transaction_is_the_live_one(session_rolled_back, second_at):
    s = session_rolled_back
    ins = """INSERT INTO fx_client_rates (org_id, ccy, basis, rate_date, units_per_eur, submitted_at)
             VALUES (CAST(:o AS uuid), 'XAU', 'closing', '2026-06-30', :u, {at})"""
    s.execute(text(ins.format(at="now()")), {"o": BANK_ORG, "u": 1.10})
    s.execute(text(ins.format(at=second_at)), {"o": BANK_ORG, "u": 1.20})
    assert client_fx.resolve(s, BANK_ORG, "XAU", date(2026, 6, 30))["units_per_eur"] == pytest.approx(1.20)
    live = [r for r in client_fx.latest_rates(s, BANK_ORG, limit=10_000) if r["ccy"] == "XAU"]
    assert [r["units_per_eur"] for r in live] == [pytest.approx(1.20)]
