"""E300: a report offers each channel once. A mandate that prescribes manual filing to the authority (the insurer's ORSA
climate analysis and recovery-plan stress) listed that channel twice — as prescribed, and again as the general fallback —
so the channel picker showed it twice. Reads the demo organisations, changes nothing."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.transmission.service import channels_for

pytestmark = pytest.mark.integration


def test_every_report_offers_each_channel_once_and_a_prescribed_channel_as_prescribed(session_rolled_back):
    s = session_rolled_back
    seen_prescribed_manual = False
    for org_type in ("bank", "insurer", "asset_manager", "reit", "manufacturer"):
        org = s.execute(text("SELECT org_id::text FROM organizations WHERE type = :t AND name LIKE '%(demo)' LIMIT 1"),
                        {"t": org_type}).scalar()
        for f in channels_for(s, org)["frameworks"]:
            ids = [c["channel_id"] for c in f["channels"]]
            assert len(ids) == len(set(ids)), (org_type, f["framework"], ids)
            manual = [c for c in f["channels"] if c["channel_id"] == "nca_manual"]
            assert len(manual) == 1, (org_type, f["framework"])          # the fallback is always on offer, once
            seen_prescribed_manual |= manual[0]["prescribed"]
    assert seen_prescribed_manual                                        # the case that listed it twice is covered
