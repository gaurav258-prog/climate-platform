"""Seasonal-arrears overlay — separate normal harvest-cycle carry-over from genuine deterioration.

Agricultural income arrives in a marketing window, not evenly, so a post-harvest past-due is often expected
carry-over (bridged by the next crop's receipts or input finance), NOT a default signal. This classifies each
PAST-DUE loan as 'seasonal carry-over' or 'genuine', transparently, against a documented crop calendar, and
returns the rationale for every reclassification. It is an EXPLAINABLE MANAGEMENT OVERLAY the accountable
person can defend to a supervisor — never a replacement for IFRS-9 staging; the raw days-past-due is preserved.

Calendar basis (disclosed, not fitted): the months in which post-harvest carry-over arrears are expected for a
crop, on a NORTHERN-HEMISPHERE default derived from FAO crop calendars. Region/hemisphere-specific calendars
are a configurable refinement (a Southern-hemisphere book shifts ~6 months). An unknown crop gets NO seasonal
allowance — it is treated as genuine (conservative).
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# crop → months (1-12) where post-harvest carry-over arrears are expected (Northern-hemisphere default)
CROP_SEASONAL_WINDOW: dict[str, set[int]] = {
    "wheat": {9, 10, 11, 12, 1, 2}, "durum wheat": {9, 10, 11, 12, 1, 2}, "barley": {9, 10, 11, 12, 1, 2},
    "maize": {10, 11, 12, 1, 2}, "corn": {10, 11, 12, 1, 2}, "sunflower": {10, 11, 12, 1},
    "soy": {10, 11, 12, 1}, "soybean": {10, 11, 12, 1}, "rice": {10, 11, 12, 1}, "sorghum": {10, 11, 12, 1},
    "coffee": {11, 12, 1, 2, 3}, "cocoa": {10, 11, 12, 1}, "cotton": {10, 11, 12, 1},
    "sugar beet": {10, 11, 12, 1, 2}, "cane sugar": {10, 11, 12, 1, 2}, "sugar": {10, 11, 12, 1, 2},
    "olive oil": {11, 12, 1, 2}, "olive": {11, 12, 1, 2}, "grape": {9, 10, 11, 12}, "wine grapes": {9, 10, 11, 12},
    "almond": {9, 10, 11, 12}, "citrus": {12, 1, 2, 3},
}
# Beyond this, a past-due is genuine deterioration regardless of season (roughly two quarters — well past one
# harvest-to-marketing cycle). A configurable honesty cap so the overlay can never excuse a deeply-impaired loan.
SEASONAL_MAX_DPD = 180
MIN_DPD = 1   # only past-due loans are assessed


def _window(crop: Optional[str]) -> Optional[set[int]]:
    if not crop:
        return None
    c = crop.strip().lower()
    if c in CROP_SEASONAL_WINDOW:
        return CROP_SEASONAL_WINDOW[c]
    for k, v in CROP_SEASONAL_WINDOW.items():   # loose contains-match ('Arabica coffee' → coffee)
        if k in c:
            return v
    return None


def ingest(session: Session, org_id: str, rows: list[dict], user_id: Optional[str]) -> dict:
    """One upload = one dated batch. rows: {loan_ref, borrower_name?, crop?, region?, exposure_eur?, days_past_due, as_of_date?}."""
    bid = str(uuid.uuid4())
    n = 0
    for r in rows:
        ref = str(r.get("loan_ref") or "").strip()
        try:
            dpd = int(float(str(r.get("days_past_due")).strip()))
        except (TypeError, ValueError, AttributeError):
            continue
        if not ref:
            continue
        try:
            exp = float(str(r.get("exposure_eur")).replace(",", "").replace("€", "").strip()) if r.get("exposure_eur") not in (None, "") else None
        except (TypeError, ValueError, AttributeError):
            exp = None
        session.execute(text("""
            INSERT INTO loan_arrears (arrears_id, org_id, batch_id, loan_ref, borrower_name, crop, region, exposure_eur, days_past_due, as_of_date, uploaded_by)
            VALUES (CAST(:a AS uuid), CAST(:o AS uuid), CAST(:b AS uuid), :ref, :bn, :crop, :reg, :exp, :dpd, CAST(:asof AS date), CAST(:u AS uuid))
        """), {"a": str(uuid.uuid4()), "o": org_id, "b": bid, "ref": ref[:80], "bn": str(r.get("borrower_name") or "")[:200],
               "crop": (str(r.get("crop")).strip() or None) if r.get("crop") else None,
               "reg": (str(r.get("region")).strip() or None) if r.get("region") else None,
               "exp": exp, "dpd": dpd,
               "asof": (str(r.get("as_of_date")).strip() or None) if r.get("as_of_date") else None, "u": user_id})
        n += 1
    session.commit()
    return {"batch_id": bid, "rows": n}


def _latest_batch(session: Session, org_id: str):
    return session.execute(text("""
        SELECT batch_id::text AS b, max(as_of_date) AS asof
        FROM loan_arrears WHERE org_id = CAST(:o AS uuid)
        GROUP BY batch_id ORDER BY max(uploaded_at) DESC LIMIT 1
    """), {"o": org_id}).mappings().first()


def assessment(session: Session, org_id: str, as_of_month: Optional[int] = None) -> dict:
    batch = _latest_batch(session, org_id)
    if not batch:
        return {"available": False, "reason": "no_arrears_uploaded"}
    month = as_of_month or (batch["asof"].month if batch["asof"] else date.today().month)
    rows = session.execute(text("""
        SELECT loan_ref, borrower_name, crop, region, CAST(exposure_eur AS FLOAT) AS exposure_eur, days_past_due
        FROM loan_arrears WHERE org_id = CAST(:o AS uuid) AND batch_id = CAST(:b AS uuid) AND days_past_due >= :m
        ORDER BY exposure_eur DESC NULLS LAST
    """), {"o": org_id, "b": batch["b"], "m": MIN_DPD}).mappings().all()

    loans, seasonal_eur, genuine_eur, seasonal_n = [], 0.0, 0.0, 0
    for r in rows:
        win = _window(r["crop"])
        dpd = r["days_past_due"]
        is_seasonal = bool(win) and (month in win) and dpd <= SEASONAL_MAX_DPD
        exp = r["exposure_eur"] or 0
        if is_seasonal:
            seasonal_eur += exp
            seasonal_n += 1
            reason = f"{r['crop']} carry-over — month {month} in harvest window, {dpd}d ≤ {SEASONAL_MAX_DPD}d cap"
        else:
            genuine_eur += exp
            reason = (f"{dpd}d exceeds the {SEASONAL_MAX_DPD}d seasonal cap" if (win and month in win and dpd > SEASONAL_MAX_DPD)
                      else f"month {month} outside {r['crop']}'s harvest window" if win
                      else "no seasonal calendar for this crop")
        loans.append({"loan_ref": r["loan_ref"], "borrower_name": r["borrower_name"], "crop": r["crop"],
                      "region": r["region"], "exposure_eur": round(exp), "days_past_due": dpd,
                      "classification": "seasonal" if is_seasonal else "genuine", "rationale": reason})
    total_eur = seasonal_eur + genuine_eur
    return {
        "available": True, "as_of": batch["asof"].isoformat() if batch["asof"] else None, "assessed_month": month,
        "seasonal_cap_days": SEASONAL_MAX_DPD,
        "summary": {
            "n_past_due": len(loans), "past_due_eur": round(total_eur),
            "n_seasonal": seasonal_n, "seasonal_eur": round(seasonal_eur),
            "n_genuine": len(loans) - seasonal_n, "genuine_eur": round(genuine_eur),
            "reclassified_pct": round(100 * seasonal_eur / total_eur, 1) if total_eur else 0,
        },
        "loans": loans,
    }
