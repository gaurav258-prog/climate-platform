"""
Regulatory submission history — real reporting periods + a genuinely immutable
snapshot, gated through the existing approval_requests maker/checker inbox.

A submission freezes build_disclosure_snapshot() (see bank.py) for one
reporting period so that later, when live bank_assets/valuations have moved
on, a bank can still answer "what exactly did we submit for Q1 2026" — not
just the rollup number, but the full per-asset detail that produced it.

Release/rejection happens via POST /v1/approvals/{id}/decide (see
approvals.py), which — for request_type == 'submission.release' — flips the
linked row here. Immutability itself is enforced by a DB trigger
(prevent_submission_mutation, see the e2f3a4b5c6d7 migration), not just this
router's logic.
"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
from api.routers.bank import build_disclosure_snapshot
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/bank/submissions", tags=["Banking"])


class SubmissionCreate(BaseModel):
    framework: str = Field("TCFD_EU_TAXONOMY", max_length=30)
    period_label: str = Field(..., max_length=50)
    period_start: date
    period_end: date
    scenario: str = Field("baseline", max_length=30)
    horizon: str = Field("current", max_length=20)


def _serialize(r) -> dict:
    return {
        "id": str(r["submission_id"]),
        "framework": r["framework"],
        "period_label": r["period_label"],
        "period_start": r["period_start"].isoformat() if r["period_start"] else None,
        "period_end": r["period_end"].isoformat() if r["period_end"] else None,
        "scenario": r["scenario"],
        "horizon": r["horizon"],
        "status": r["status"],
        "maker_email": r.get("maker_email"),
        "checker_email": r.get("checker_email"),
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "released_at": r["released_at"].isoformat() if r["released_at"] else None,
    }


@router.post("", status_code=201, summary="Snapshot the current disclosure and queue it for release (maker)")
def create_submission(body: SubmissionCreate, session: DbSession,
                       ctx: dict = Depends(require_permission("reports.publish"))):
    org_id = ctx["org"]["org_id"]

    snapshot = build_disclosure_snapshot(session, org_id, body.scenario, body.horizon)

    # A plain "does a draft already exist" pre-check can't lock a row that doesn't
    # exist yet, so two concurrent creators for a brand-new period would both pass
    # it. The real serialization point is THIS statement: Postgres blocks a second
    # INSERT ON CONFLICT on the same period until the first transaction commits,
    # so by the time our own statement returns, any transaction that "won" the
    # race is already fully committed -- including its approval_requests link.
    # We check for that AFTER this insert, not before.
    submission_id = session.execute(text("""
        INSERT INTO bank_disclosure_submissions
            (org_id, framework, period_label, period_start, period_end, scenario, horizon,
             snapshot, maker_user_id)
        VALUES (:o, :f, :pl, :ps, :pe, :s, :h, CAST(:snap AS jsonb), :m)
        ON CONFLICT (org_id, framework, period_start, period_end) WHERE status = 'draft'
        DO UPDATE SET snapshot = EXCLUDED.snapshot, scenario = EXCLUDED.scenario, horizon = EXCLUDED.horizon
        RETURNING submission_id
    """), {"o": org_id, "f": body.framework, "pl": body.period_label, "ps": body.period_start,
           "pe": body.period_end, "s": body.scenario, "h": body.horizon,
           "snap": json.dumps(snapshot, default=str), "m": ctx["user"]["id"]}).scalar()

    linked_request_id = session.execute(text(
        "SELECT approval_request_id FROM bank_disclosure_submissions WHERE submission_id = :s"
    ), {"s": submission_id}).scalar()
    if linked_request_id:
        linked_status = session.execute(text(
            "SELECT status FROM approval_requests WHERE request_id = :r"
        ), {"r": linked_request_id}).scalar()
        if linked_status == "pending":
            raise HTTPException(409, {"error": "already_queued",
                                       "message": "This period already has a submission awaiting a checker's decision. "
                                                  "Ask the checker to decide it before resubmitting."})

    approval_payload = {
        "submission_id": str(submission_id),
        "framework": body.framework,
        "period_label": body.period_label,
        "period_start": body.period_start.isoformat(),
        "period_end": body.period_end.isoformat(),
        "value_at_risk_eur": snapshot["rollup"]["value_at_risk_eur"],
        "n_assets": snapshot["rollup"]["n_assets"],
    }
    request_id = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o, 'submission.release', :title, CAST(:p AS jsonb), :m)
        RETURNING request_id
    """), {"o": org_id, "title": f"Release {body.framework} disclosure — {body.period_label}",
           "p": json.dumps(approval_payload), "m": ctx["user"]["id"]}).scalar()

    session.execute(text(
        "UPDATE bank_disclosure_submissions SET approval_request_id = :r WHERE submission_id = :s"
    ), {"r": request_id, "s": submission_id})

    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="submission.create",
                target_type="bank_disclosure_submission", target_id=str(submission_id),
                detail={"framework": body.framework, "period_label": body.period_label})

    return {"id": str(submission_id), "approval_request_id": str(request_id), "status": "draft"}


@router.get("", summary="Prior submissions for this org (the 'what did we submit last quarter' list)")
def list_submissions(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    rows = session.execute(text("""
        SELECT bs.submission_id, bs.framework, bs.period_label, bs.period_start, bs.period_end,
               bs.scenario, bs.horizon, bs.status, bs.created_at, bs.released_at,
               mu.email AS maker_email, cu.email AS checker_email
        FROM bank_disclosure_submissions bs
        LEFT JOIN users mu ON mu.user_id = bs.maker_user_id
        LEFT JOIN users cu ON cu.user_id = bs.checker_user_id
        WHERE bs.org_id = :o
        ORDER BY bs.period_start DESC, bs.created_at DESC
    """), {"o": ctx["org"]["org_id"]}).mappings().all()
    return [_serialize(r) for r in rows]


def _flagged_asset_ids(snapshot: dict) -> set:
    return {a["asset_id"] for a in snapshot["assets"] if a["headline_bucket"] in ("H", "VH")}


def _period_delta(prev_snap: dict, curr_snap: dict) -> dict:
    """Real quarter-over-quarter comparison of two frozen snapshots -- not a
    recomputation, just a diff of two numbers that already exist. Asset-level
    membership changes (newly_flagged/de_flagged) are computed by asset_id set
    difference, so a genuinely new VH asset is distinguished from one whose
    bucket merely fluctuated within H/VH."""
    pr, cr = prev_snap["rollup"], curr_snap["rollup"]
    prev_flagged, curr_flagged = _flagged_asset_ids(prev_snap), _flagged_asset_ids(curr_snap)
    newly_flagged = curr_flagged - prev_flagged
    de_flagged = prev_flagged - curr_flagged
    asset_by_id = {a["asset_id"]: a for a in curr_snap["assets"]}
    prev_asset_by_id = {a["asset_id"]: a for a in prev_snap["assets"]}

    prev_coverage = pr["n_scored"] / pr["n_assets"] if pr["n_assets"] else 0.0
    curr_coverage = cr["n_scored"] / cr["n_assets"] if cr["n_assets"] else 0.0

    prev_tax = {k: v["value_eur"] for k, v in prev_snap["taxonomy"].items()}
    curr_tax = {k: v["value_eur"] for k, v in curr_snap["taxonomy"].items()}
    tax_shift = {k: round(curr_tax.get(k, 0) - prev_tax.get(k, 0)) for k in set(prev_tax) | set(curr_tax)}

    return {
        "value_at_risk_delta_eur": round(cr["value_at_risk_eur"] - pr["value_at_risk_eur"]),
        "pct_value_at_risk_delta": round(cr["pct_value_at_risk"] - pr["pct_value_at_risk"], 2),
        "n_high_delta": cr["n_high"] - pr["n_high"],
        "scored_coverage_pct_delta": round(100 * (curr_coverage - prev_coverage), 1),
        "newly_flagged_assets": [
            {"asset_id": aid, "asset_name": asset_by_id[aid]["asset_name"],
             "headline_bucket": asset_by_id[aid]["headline_bucket"],
             "headline_hazard": asset_by_id[aid]["headline_hazard"]}
            for aid in newly_flagged if aid in asset_by_id
        ],
        "de_flagged_assets": [
            {"asset_id": aid, "asset_name": prev_asset_by_id[aid]["asset_name"]}
            for aid in de_flagged if aid in prev_asset_by_id
        ],
        "taxonomy_value_shift_eur": tax_shift,
    }


@router.get("/trend", summary="Quarter-over-quarter trend across released submissions")
def submissions_trend(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    """Real deltas between consecutive RELEASED submissions, ordered by
    reporting period -- not a fitted trend line or forecast, just an honest
    diff of numbers this org already froze and released. Needs at least 2
    released submissions to produce a delta; fewer returns an empty trend
    with a clear reason rather than a fabricated single-point 'trend'."""
    rows = session.execute(text("""
        SELECT submission_id, period_label, period_start, period_end, snapshot
        FROM bank_disclosure_submissions
        WHERE org_id = :o AND status = 'released'
        ORDER BY period_start ASC
    """), {"o": ctx["org"]["org_id"]}).mappings().all()

    if len(rows) < 2:
        return {"periods": [{"period_label": r["period_label"], "period_start": r["period_start"].isoformat()}
                             for r in rows],
                "deltas": [], "status": "insufficient_history",
                "message": "Need at least 2 released submissions to compute a trend."}

    deltas = []
    for prev, curr in zip(rows, rows[1:]):
        delta = _period_delta(prev["snapshot"], curr["snapshot"])
        deltas.append({
            "from_period": prev["period_label"], "to_period": curr["period_label"],
            "to_period_start": curr["period_start"].isoformat(),
            **delta,
        })

    first, last = rows[0]["snapshot"]["rollup"], rows[-1]["snapshot"]["rollup"]
    cumulative = {
        "from_period": rows[0]["period_label"], "to_period": rows[-1]["period_label"],
        "value_at_risk_delta_eur": round(last["value_at_risk_eur"] - first["value_at_risk_eur"]),
        "pct_value_at_risk_delta": round(last["pct_value_at_risk"] - first["pct_value_at_risk"], 2),
        "n_high_delta": last["n_high"] - first["n_high"],
    }
    return {
        "periods": [{"period_label": r["period_label"], "period_start": r["period_start"].isoformat()}
                    for r in rows],
        "deltas": deltas,
        "cumulative": cumulative,
        "status": "ok",
    }


@router.get("/{submission_id}", summary="A single submission, including its frozen snapshot")
def get_submission(submission_id: str, session: DbSession,
                    ctx: dict = Depends(require_permission("reports.view"))):
    row = session.execute(text("""
        SELECT bs.*, mu.email AS maker_email, cu.email AS checker_email
        FROM bank_disclosure_submissions bs
        LEFT JOIN users mu ON mu.user_id = bs.maker_user_id
        LEFT JOIN users cu ON cu.user_id = bs.checker_user_id
        WHERE bs.submission_id = :s AND bs.org_id = :o
    """), {"s": submission_id, "o": ctx["org"]["org_id"]}).mappings().first()
    if not row:
        raise HTTPException(404, {"error": "not_found", "message": "Submission not found."})
    return {**_serialize(row), "snapshot": row["snapshot"]}
