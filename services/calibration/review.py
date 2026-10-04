"""What the platform operator reviews (E162): the calibration batches awaiting a decision, and every recipe with its
latest and published run — read only; decisions go through the one approvals path."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def pending(session: Session) -> list[dict]:
    rows = session.execute(text("""
        SELECT a.request_id::text AS approval_request_id, a.title, a.created_at, a.payload, a.maker_user_id::text AS maker_id,
               u.email AS maker
        FROM approval_requests a LEFT JOIN users u ON u.user_id = a.maker_user_id
        WHERE a.request_type = 'calibration.publish' AND a.status = 'pending' ORDER BY a.seq""")).mappings()
    return [{"approval_request_id": r["approval_request_id"], "title": r["title"], "created_at": r["created_at"],
             "maker_id": r["maker_id"], "maker": r["maker"], "review": (r["payload"] or {}).get("review"),
             "summary": (r["payload"] or {}).get("summary")} for r in rows]


def recipes(session: Session) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT s.spec_id::text, s.commodity, s.origin, s.yield_region, s.driver, s.weather_kind, s.weather_key,
               s.season_months, s.season_prev_months, s.spei_scale, s.yield_source, s.allow_cycle, s.basis, s.protocol,
               l.run_id::text AS latest_run_id, l.run_at AS latest_run_at, l.status AS latest_status, l.outcome,
               CAST(l.r2_oos AS FLOAT) AS latest_r2_oos, l.downside_pass AS latest_downside, l.upside_pass AS latest_upside,
               l.upside->'failed' AS latest_upside_failed,
               p.run_id::text AS published_run_id, CAST(p.r2_oos AS FLOAT) AS published_r2_oos,
               p.downside_pass AS published_downside, p.upside_pass AS published_upside, p.decided_at AS published_at
        FROM crop_calibration_specs s
        LEFT JOIN LATERAL (SELECT * FROM crop_calibration_runs r WHERE r.spec_id = s.spec_id ORDER BY r.seq DESC LIMIT 1) l ON true
        LEFT JOIN crop_calibration_runs p ON p.spec_id = s.spec_id AND p.status = 'published'
        WHERE s.retired_at IS NULL
        ORDER BY s.commodity, s.origin, s.yield_region, s.driver""")).mappings()]
