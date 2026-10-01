"""One obligation per financial product (E93): an asset manager with two Art. 8 / 9 funds is owed each fund's periodic
document for the year, and the calendar shows both with their fund (it broke on the second before)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.governance import filings as F

pytestmark = pytest.mark.integration
NORDKAP = "44444444-4444-4444-8444-444444444444"


def test_two_funds_are_each_owed_their_periodic_document(session_rolled_back):
    s = session_rolled_back
    ids = [str(s.execute(text("""INSERT INTO funds (org_id, name, fund_type, sfdr_classification)
                                 VALUES (CAST(:o AS uuid), :n, 'fund', :c) RETURNING fund_id"""),
                         {"o": NORDKAP, "n": f"E93 fund {i}", "c": c}).scalar()) for i, c in ((1, "article_8"), (2, "article_9"))]
    owed = F.list_obligations(s, NORDKAP, "asset_manager")
    periodic = {o["fund_id"] for o in owed if o["framework"] == "sfdr_periodic"}
    assert set(ids) <= periodic, periodic
