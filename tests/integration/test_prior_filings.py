"""Prior filings end-to-end + KRI raise-task — the filed-data loop and the act-on-breach task.
Requires PostgreSQL (uses the Meridian demo org). Each test cleans up after itself."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
import services.governance.prior_filings as PF
import services.governance.tasks as T

BANK_ORG = "11111111-1111-4111-8111-111111111111"
_IX = ('<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>'
       '<ix:nonFraction name="FinancedEmissionsScope3" contextRef="c" unitRef="tco2e" scale="0">1500000</ix:nonFraction>'
       '<ix:nonFraction name="SomeProprietaryMetric" contextRef="c" unitRef="eur" scale="0">4200</ix:nonFraction>'
       '</body></html>').encode()


def _actor(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


@pytest.mark.integration
def test_upload_confirm_remap_trend_and_projection():
    with get_session() as s:
        u = _actor(s)
        draft = PF.create_from_upload(s, BANK_ORG, u, framework="bank_p3esg", period_label="2097",
                                      entity_name="Meridian Bank", filename="t.html", data=_IX)
        try:
            figs = {f["label"]: f for f in draft["figures"]}
            assert draft["status"] == "draft" and len(figs) == 2
            # one line auto-maps, the other is unmatched until the preparer remaps it
            emis = next(f for f in draft["figures"] if f["datapoint_key"] == "p3_scope3")
            unm = next(f for f in draft["figures"] if f["datapoint_key"] is None)
            assert emis["value_num"] == 1500000.0

            conf = PF.confirm(s, draft["filing_id"], BANK_ORG, u, edits=[
                {"figure_id": unm["figure_id"], "datapoint_key": "p3_gar_aligned"},   # remap the unmatched line
                {"figure_id": emis["figure_id"], "value_num": 1490000.0},             # correct a value
            ], basis_note="PCAF v2")
            assert conf["status"] == "confirmed"
            byid = {f["figure_id"]: f for f in conf["figures"]}
            assert byid[unm["figure_id"]]["datapoint_key"] == "p3_gar_aligned"
            assert byid[unm["figure_id"]]["read_method"] == "confirmed"
            assert byid[emis["figure_id"]]["value_num"] == 1490000.0

            # trend for the confirmed datapoint + a forward projection anchored at the last filed value
            tr = PF.trends(s, BANK_ORG, "bank_p3esg", horizon_years=2)
            scope = next(x for x in tr["series"] if x["datapoint_key"] == "p3_scope3")
            assert any(p["period"] == "2097" and p["value"] == 1490000.0 for p in scope["points"])
            assert len(scope["projection"]) == 2   # projects forward from the last filed point
        finally:
            PF.delete_filing(s, draft["filing_id"], BANK_ORG)   # reported_figure cascades; leaves the org clean


@pytest.mark.integration
def test_kri_raise_task_is_deduped_by_source_ref():
    with get_session() as s:
        u = _actor(s)
        ref = "bank_p3esg:__test_share_at_risk__"
        t1 = T.create_task(s, BANK_ORG, u, title="KRI breach — test", criticality="high",
                           source="kri", source_ref=ref)
        t2 = T.create_task(s, BANK_ORG, u, title="KRI breach — test again", criticality="high",
                           source="kri", source_ref=ref)
        try:
            assert t1["source"] == "kri" and t1["source_ref"] == ref
            assert t1["task_id"] == t2["task_id"]   # a live task for the same indicator is reused, not duplicated
        finally:
            # activity log is append-only (WORM) — a task is retired by cancelling, not deleting
            s.execute(text("UPDATE regulatory_task SET status='cancelled' WHERE source='kri' AND source_ref=:r"),
                      {"r": ref})
            s.commit()
