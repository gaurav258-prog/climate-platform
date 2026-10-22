"""gates-v2: a hazard's grade reads the band check only when its registered conditions are shown. The first —
MIN_N_REGION_CLAIM samples in at least GLOBAL_CLAIM_MIN_REGIONS macro-regions — is a fact of the ledger, checked here for
every hazard listed in core/validation_gates.MONOTONE_GRADE_HAZARDS."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core import validation_gates as G

pytestmark = pytest.mark.integration


def _regions(metrics: dict) -> dict:
    out = {}
    for key in ("per_region", "stratified"):
        block = metrics.get(key) or {}
        rows = block.get("regions", block) if isinstance(block, dict) else {}
        for name, r in (rows.items() if isinstance(rows, dict) else []):
            if isinstance(r, dict) and isinstance(r.get("n"), (int, float)):
                out[name] = max(out.get(name, 0), int(r["n"]))
    return out


def test_every_listed_hazard_meets_the_regional_sample_floor_in_the_ledger(session_rolled_back):
    for hazard in G.MONOTONE_GRADE_HAZARDS:
        best = 0
        for (m,) in session_rolled_back.execute(text("SELECT metrics FROM validation_run WHERE hazard_type = :h"),
                                                {"h": hazard}):
            regions = _regions(m or {})
            best = max(best, sum(1 for n in regions.values() if n >= G.MIN_N_REGION_CLAIM))
        assert best >= G.GLOBAL_CLAIM_MIN_REGIONS, (hazard, best)
