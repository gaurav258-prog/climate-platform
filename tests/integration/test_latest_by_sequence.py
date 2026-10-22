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


# The write-once tables, from the schema itself: a row-level trigger that refuses both UPDATE and DELETE (tgtype bits:
# 1 row, 2 before, 8 delete, 16 update).
WRITE_ONCE = """
    SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_proc p ON p.oid = t.tgfoid
    WHERE NOT t.tgisinternal AND c.relnamespace = 'public'::regnamespace AND (t.tgtype & 3) = 3
      AND p.prosrc ~* 'RAISE\\s+EXCEPTION'
    GROUP BY c.relname HAVING bool_or((t.tgtype & 8) <> 0) AND bool_or((t.tgtype & 16) <> 0)"""


def test_a_write_once_table_read_for_its_latest_row_is_a_history_read_by_its_sequence(session_rolled_back):
    """E216: validation_run is write-once, yet four readers took its latest run by created_at — the history list is kept
    by hand, and nobody had added it. The write-once tables come from the schema, so a new one is caught the first time
    code takes its latest row by a timestamp; once listed, tests/unit/test_history_order.py holds it to its sequence."""
    from tests.unit.test_history_order import HISTORY, latest_by_time
    tables = set(session_rolled_back.execute(text(WRITE_ONCE)).scalars())
    assert {"validation_run", "regulatory_filing_event", "site_period_values"} <= tables
    bad = [f"{where}: {t} ORDER BY {o}" for t, where, o in latest_by_time(tables) if t not in HISTORY]
    assert not bad, f"add these to HISTORY (with a seq column) and read them by seq: {bad}"


def test_any_table_read_for_its_latest_row_is_a_history_read_by_its_sequence(session_rolled_back):
    """E312: risk_decision — the decision log, whose latest row per exposure is the standing call — took that row by
    decided_at. A decision's status changes, so the table is not write-once and the test above never listed it. Every
    table now counts: a read for its latest row by a timestamp is a listed history, read by its sequence. The ten tables
    E312 left on a worklist were each fixed or shown to need no order (E315), and the worklist is gone."""
    from tests.unit.test_history_order import HISTORY, latest_by_time
    tables = set(session_rolled_back.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).scalars())
    bad = sorted({f"{where}: {t} ORDER BY {o}" for t, where, o in latest_by_time(tables) if t not in HISTORY})
    assert not bad, f"add these to HISTORY (with a seq column) and read them by seq: {bad}"


def test_every_listed_history_carries_a_sequence(session_rolled_back):
    from tests.unit.test_history_order import HISTORY
    with_seq = set(session_rolled_back.execute(text("""
        SELECT table_name FROM information_schema.columns
        WHERE table_schema = 'public' AND (is_identity = 'YES' OR column_default LIKE 'nextval(%')""")).scalars())
    assert not [t for t in HISTORY if t not in with_seq]


def test_the_latest_validation_run_is_the_last_written_even_in_one_transaction(session_rolled_back):
    """Two runs for one model recorded in one transaction share created_at; the second is the latest."""
    from services.validation.engine import latest_skill_for_model
    s = session_rolled_back
    mid = s.execute(text("SELECT model_id::text FROM model_registry LIMIT 1")).scalar()
    for grade in ("weak", "strong"):
        s.execute(text("""INSERT INTO validation_run (run_id, model_id, hazard_type, kind, method, target_source, n_samples,
                                                      metrics, skill_grade, passed_gate, created_at)
                          VALUES (gen_random_uuid(), CAST(:m AS uuid), 'probe', 'rank', 'in_sample', 'probe', 9, '{}', :g,
                                  false, '2099-01-01T00:00:00Z')"""), {"m": mid, "g": grade})
    assert latest_skill_for_model(s, mid)["skill_grade"] == "strong"
