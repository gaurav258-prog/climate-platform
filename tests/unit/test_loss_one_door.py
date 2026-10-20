"""The product owner's decision of 2026-10-20: filings, risk indicators and decisions take only tested loss figures.
Outside the loss engine and the loss screen's own API, loss figures are read only through services/loss/figures.py,
which hands out tested figures alone — this fails when any other code reads the loss tables directly."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE = ("services", "api", "core", "ml", "scripts")
TABLES = re.compile(r"\bloss_(results|ep_points)\b")
ALLOWED = ("services/loss/", "api/routers/loss.py", "core/db/migrations/")


def readers() -> list[str]:
    out = []
    for p in [f for d in CODE for f in (ROOT / d).rglob("*.py")]:
        rel = p.relative_to(ROOT).as_posix()
        if not rel.startswith(ALLOWED) and TABLES.search(p.read_text(encoding="utf-8", errors="ignore")):
            out.append(rel)
    return sorted(out)


def test_nothing_outside_the_loss_engine_reads_loss_figures_but_through_the_one_door():
    assert readers() == [], "read loss figures through services.loss.figures.tested (tested figures only)"


def test_the_scan_sees_a_direct_read():
    assert TABLES.search("SELECT eal_eur FROM loss_results WHERE …") and not TABLES.search("loss_results_view_x")
