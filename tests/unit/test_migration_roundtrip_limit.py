"""E335: the migration round-trip stops and fails once it runs longer than its limit — the gate holds the machine's
shared lock while it runs, and one run held every other session's gate for 3.5 hours."""
from __future__ import annotations

import time

from scripts import check_migration_roundtrip as R


def test_within_the_limit_the_run_carries_on_and_past_it_stops_naming_where(monkeypatch):
    monkeypatch.setattr(R, "LIMIT_S", 60.0)
    assert R._over_time(time.time() - 10, "the upgrade to x") is None
    why = R._over_time(time.time() - 61, "the downgrade of register_sites_20261023")
    assert why and "the downgrade of register_sites_20261023" in why and "60s limit" in why


def test_the_limit_defaults_to_thirty_minutes():
    import os
    assert "MIGCHECK_LIMIT_S" in os.environ or R.LIMIT_S == 1800.0
