"""The r² publish floor has ONE source of truth (audit T10). Requires PostgreSQL.

The floor `RANGED_PUBLISH_FLOOR` was historically duplicated as a bare `0.40` literal in the fit
script, the COGS service, and the SQL calibration view. A drift between them would silently publish (or
withhold) crops the others wouldn't. These tests pin every copy to the one Python constant.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.intelligence.supply_cogs import RANGED_PUBLISH_FLOOR


def test_fit_script_reuses_the_constant():
    # the fit script must not redefine its own floor — it imports the canonical one
    from scripts.fit_ranged_crop import MIN_R2
    assert MIN_R2 == RANGED_PUBLISH_FLOOR


@pytest.mark.integration
def test_db_calibration_view_floor_matches_constant():
    with get_session() as s:
        vdef = s.execute(text(
            "SELECT pg_get_viewdef(to_regclass('v_sc_commodity_calibration'), true)")).scalar()
    # the ranged branch gates on out-of-sample r² (audit F2); its literal must equal the constant
    m = re.search(r"r2_oos\s*>=\s*([0-9]*\.?[0-9]+)", vdef)
    assert m, "v_sc_commodity_calibration does not gate on r2_oos — check the ranged branch"
    assert float(m.group(1)) == RANGED_PUBLISH_FLOOR, (
        f"DB view floor {m.group(1)} != RANGED_PUBLISH_FLOOR {RANGED_PUBLISH_FLOOR}")
