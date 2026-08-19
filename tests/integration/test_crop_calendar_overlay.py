"""WS4b — two crops on ONE belt cell keep their OWN drought calendars (no clobber).

`canonical_scores` holds one active drought row per (cell, hazard) — the GENERIC lane every
financial/regulatory reader aggregates. `sc_crop_calendar_score` overlays a per-crop-calendar
reading that only the agri plot view reads (preferring the crop's own row). This proves:
  1. two crops (wheat + barley) can hold DIFFERENT active drought readings on the SAME cell;
  2. each plot reads ITS crop's calendar via v_sc_plot_physical_risk (not the other's);
  3. the generic canonical lane is untouched (a financial reader on the cell still sees it).
Runs inside a transaction that is ROLLED BACK, so it writes nothing durable (respects the
append-only WORM triggers, which fire only on commit) and is fully repeatable.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from core.db.session import engine

CELL = "88_ws4b_testcell_x"   # synthetic; no real plot/asset uses it


def _ids(conn):
    w = conn.execute(text("SELECT commodity_id FROM sc_commodities WHERE name='Wheat'")).scalar()
    b = conn.execute(text("SELECT commodity_id FROM sc_commodities WHERE name='Barley'")).scalar()
    org = conn.execute(text("SELECT org_id FROM sc_sourcing_plots LIMIT 1")).scalar()
    return w, b, org


def test_two_crop_calendars_coexist_and_resolve_per_plot():
    now = datetime.now(timezone.utc)
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            wheat, barley, org = _ids(conn)
            # one GENERIC canonical drought row on the shared cell (what a financial reader sees)
            conn.execute(text("""
                INSERT INTO canonical_scores
                    (score_id,h3_cell,h3_resolution,hazard_type,scenario,time_horizon,risk_score,
                     risk_bucket,model_version,data_vintage,valid_from,scored_at,score_lane)
                VALUES (:id,:c,8,'drought','baseline','current',40,'M','test',:now,:now,:now,'standing')
            """), {"id": str(uuid.uuid4()), "c": CELL, "now": now})
            # two plots, same cell, different crops
            wp, bp = str(uuid.uuid4()), str(uuid.uuid4())
            for pid, cid, nm in ((wp, wheat, "ws4b wheat"), (bp, barley, "ws4b barley")):
                conn.execute(text("""
                    INSERT INTO sc_sourcing_plots (plot_id,org_id,commodity_id,plot_name,country,h3_cell,eudr_status,created_at)
                    VALUES (:p,:o,:c,:n,'MA',:cell,'unknown',:now)
                """), {"p": pid, "o": org, "c": cid, "n": nm, "cell": CELL, "now": now})
            # two crop-calendar overlays on the SAME cell — wheat 1-4/spei3 → 55, barley 1-6/spei6 → 70
            for cid, season, spei, sc in ((wheat, "1,2,3,4", 3, 55), (barley, "1,2,3,4,5,6", 6, 70)):
                conn.execute(text("""
                    INSERT INTO sc_crop_calendar_score
                        (score_id,commodity_id,origin,h3_cell,h3_resolution,hazard_type,scenario,time_horizon,
                         risk_score,risk_bucket,season_months,spei_scale,model_version,data_vintage,scored_at,valid_from,valid_to)
                    VALUES (:id,:cid,'MA',:cell,8,'drought','baseline','current',:sc,'M',:season,:spei,'test',:now,:now,:now,NULL)
                """), {"id": str(uuid.uuid4()), "cid": cid, "cell": CELL, "sc": sc, "season": season, "spei": spei, "now": now})

            rows = {r["plot_id"]: r["physical_risk_score"] for r in conn.execute(text("""
                SELECT plot_id, physical_risk_score FROM v_sc_plot_physical_risk
                WHERE h3_cell=:c AND hazard_type='drought' AND scenario='baseline' AND time_horizon='current'
            """), {"c": CELL}).mappings()}

            # (1)+(2): each plot reads ITS crop's calendar, not the other's, not the generic
            assert rows[uuid.UUID(wp)] == 55.0, f"wheat plot should read wheat calendar, got {rows.get(uuid.UUID(wp))}"
            assert rows[uuid.UUID(bp)] == 70.0, f"barley plot should read barley calendar, got {rows.get(uuid.UUID(bp))}"
            # (3): the generic canonical lane is untouched — a direct (financial-style) read still sees 40
            generic = conn.execute(text("""
                SELECT risk_score FROM canonical_scores
                WHERE h3_cell=:c AND hazard_type='drought' AND scenario='baseline'
                  AND time_horizon='current' AND valid_to IS NULL
            """), {"c": CELL}).scalar()
            assert float(generic) == 40.0, f"generic lane should be untouched, got {generic}"
        finally:
            trans.rollback()   # write nothing durable — repeatable, WORM-safe


def test_overlay_index_permits_two_active_rows_one_cell():
    # the uniqueness key includes commodity_id, so two crops CAN be active on one cell
    with engine.connect() as conn:
        idxdef = conn.execute(text("""
            SELECT indexdef FROM pg_indexes
            WHERE tablename='sc_crop_calendar_score' AND indexname='ix_crop_calendar_current'
        """)).scalar()
    assert idxdef and "commodity_id" in idxdef and "valid_to IS NULL" in idxdef
