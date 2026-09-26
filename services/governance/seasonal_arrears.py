"""Seasonal-arrears overlay — separate normal harvest-cycle carry-over, a climate-attributed bad harvest, and
genuine credit deterioration.

Agricultural income arrives in a marketing window, not evenly, so a post-harvest past-due is often expected
carry-over (bridged by the next crop's receipts or input finance), NOT a default signal. Everything that
ISN'T calendar carry-over used to be lumped into "genuine" — but a real chunk of that residual is a borrower
whose harvest failed because of an actual climate shock that year, which is not a credit-quality signal about
THAT borrower either. This classifies each PAST-DUE loan into three tiers, transparently, with the rationale
for every call. It is an EXPLAINABLE MANAGEMENT OVERLAY the accountable person can defend to a supervisor —
never a replacement for IFRS-9 staging; the raw days-past-due is preserved.

Calendar basis (disclosed, not fitted): the months in which post-harvest carry-over arrears are expected for a
crop, on a NORTHERN-HEMISPHERE default derived from FAO crop calendars. Region/hemisphere-specific calendars
are a configurable refinement (a Southern-hemisphere book shifts ~6 months). An unknown crop gets NO seasonal
allowance — it is treated as genuine (conservative).

Climate-attributed basis: crop_yield_observations (FAOSTAT/ICCO/ICO-grade, the same table the agri vertical's
own "Realized Exposure" feature already uses) — a >5% year-on-year national production decline for the loan's
crop x country x season. This is a COARSE, national-level proxy for one borrower's own harvest, disclosed as
such in every rationale string; it explains a PATTERN, it does not prove this specific farm failed. A loan
with no `country` on record cannot be checked (never guessed from the free-text `region`) and is reported
separately as "not checked", not silently folded into "genuine".
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# crop -> months (1-12) where post-harvest carry-over arrears are expected (Northern-hemisphere default)
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

# crop_yield_observations.commodity is free text from several source ingests (FAOSTAT/ICCO/ICO), so its spelling
# doesn't match CROP_SEASONAL_WINDOW's keys 1:1 (e.g. "Almonds" vs "almond", "Soybean RS full" vs "soy"). This
# maps every observed commodity value to the SAME crop key used above, so one loan crop checks both tables
# under one vocabulary. Disclosed, literal — never a fuzzy guess.
YIELD_COMMODITY_ALIAS: dict[str, str] = {
    "cocoa": "cocoa", "coffee": "coffee", "coffee arabica": "coffee", "coffee arabica mg": "coffee",
    "coffee_green": "coffee", "durum wheat": "durum wheat", "wheat": "wheat", "maize": "maize", "maize mt": "maize",
    "sorghum": "sorghum", "soybean": "soy", "soybean mt": "soy", "soybean rs": "soy", "soybean rs full": "soy",
    "rice": "rice", "barley": "barley", "cotton mt": "cotton", "sugar beet": "sugar beet", "cane sugar": "cane sugar",
    "olive oil": "olive oil", "citrus": "citrus", "almonds": "almond", "wine grapes": "wine grapes",
    "sunflower": "sunflower", "rapeseed": "rapeseed", "palm oil": "palm oil",
}
YIELD_SHOCK_THRESHOLD_PCT = -5.0   # same threshold agri's own Realized Exposure uses, for one consistent claim


def _crop_key(crop: Optional[str]) -> Optional[str]:
    """The loan's free-text crop, resolved to a canonical key (loose contains-match, e.g. 'Arabica coffee' -> 'coffee')."""
    if not crop:
        return None
    c = crop.strip().lower()
    if c in CROP_SEASONAL_WINDOW:
        return c
    for k in CROP_SEASONAL_WINDOW:
        if k in c:
            return k
    return None


def _window(crop_key: Optional[str]) -> Optional[set[int]]:
    return CROP_SEASONAL_WINDOW.get(crop_key) if crop_key else None


def classify_loan(crop: Optional[str], dpd: int, month: int, country: Optional[str],
                  yield_shocks: dict[tuple[str, str, int], float], season_year: Optional[int]) -> dict:
    """Pure classifier — no DB. `yield_shocks` is a pre-fetched {(crop_key, country, season_year): yoy_change_pct}
    map for shocks below YIELD_SHOCK_THRESHOLD_PCT (see `_yield_shock_map`). Returns {classification, rationale}."""
    crop_key = _crop_key(crop)
    win = _window(crop_key)
    if win and (month in win) and dpd <= SEASONAL_MAX_DPD:
        return {"classification": "seasonal",
                "rationale": f"{crop} carry-over — month {month} in harvest window, {dpd}d ≤ {SEASONAL_MAX_DPD}d cap"}

    if country and crop_key and season_year:
        yoy = yield_shocks.get((crop_key, country.upper(), season_year))
        if yoy is not None:
            return {"classification": "climate_attributed",
                    "rationale": f"{country.upper()} {crop or crop_key} production fell {yoy:.1f}% y/y in {season_year} "
                                f"(FAOSTAT-grade, national) — a bad harvest, not a credit-specific signal; {dpd}d past due"}

    if win and month in win and dpd > SEASONAL_MAX_DPD:
        reason = f"{dpd}d exceeds the {SEASONAL_MAX_DPD}d seasonal cap"
    elif win:
        reason = f"month {month} outside {crop}'s harvest window"
    else:
        reason = "no seasonal calendar for this crop"
    if not country:
        reason += "; no country on record, so no climate-shock check was possible"
    return {"classification": "genuine", "rationale": reason}


def _yield_shock_map(session: Session, keys: set[tuple[str, str]]) -> dict[tuple[str, str, int], float]:
    """{(crop_key, country, season_year): yoy_change_pct} for every observed shock below threshold, restricted to
    the (crop_key, country) pairs actually on the past-due book (cheap: at most a few dozen rows fetched)."""
    if not keys:
        return {}
    countries = {c for _, c in keys}
    rows = session.execute(text("""
        SELECT commodity, country, season_year, CAST(yoy_change_pct AS FLOAT) AS yoy
        FROM crop_yield_observations
        WHERE country = ANY(:countries) AND yoy_change_pct < :thr
    """), {"countries": list(countries), "thr": YIELD_SHOCK_THRESHOLD_PCT}).mappings().all()
    out: dict[tuple[str, str, int], float] = {}
    for r in rows:
        key = YIELD_COMMODITY_ALIAS.get(str(r["commodity"]).strip().lower())
        if key and (key, r["country"]) in keys:
            out[(key, r["country"], r["season_year"])] = r["yoy"]
    return out


def ingest(session: Session, org_id: str, rows: list[dict], user_id: Optional[str], currency: Optional[str] = None,
           book_date: Optional[str] = None) -> dict:
    """One upload = one dated batch. rows: {loan_ref, borrower_name?, crop?, region?, country?, exposure (or
    exposure_eur)?, currency?, days_past_due, as_of_date?}. `country` is an optional ISO-2 the uploader provides
    directly — never inferred from `region`. An exposure's currency is the row's `currency`, else the declared one —
    never assumed; converted to EUR at the closing rate of the row's as_of_date (else the declared book date), the
    amount as sent and the rate kept (money_source). A row that can't be used is reported with the reason."""
    from services.intake.money import MoneyError, convert_amount, source_record
    bid = str(uuid.uuid4())
    n, skipped = 0, []
    for i, r in enumerate(rows, start=2):
        ref = str(r.get("loan_ref") or "").strip()
        try:
            dpd = int(float(str(r.get("days_past_due")).strip()))
        except (TypeError, ValueError, AttributeError):
            skipped.append({"row": i, "reason": "days_past_due is not a whole number"})
            continue
        if not ref:
            skipped.append({"row": i, "reason": "loan_ref is missing"})
            continue
        raw_exp = r.get("exposure", r.get("exposure_eur"))
        asof = str(r.get("as_of_date") or "").strip() or book_date
        exp, ms = None, None
        if raw_exp not in (None, ""):
            ccy = (str(r.get("currency") or "").strip() or currency or "").upper()
            try:
                c = convert_amount(session, raw_exp, ccy, asof, label="exposure", org_id=org_id)
            except MoneyError as e:
                skipped.append({"row": i, "reason": str(e)})
                continue
            exp, ms = c["eur"], json.dumps(source_record(ccy, asof, {"exposure_eur": c}, origin=f"arrears_batch:{bid}"), default=str)
        country = str(r.get("country") or "").strip().upper()[:3] or None
        session.execute(text("""
            INSERT INTO loan_arrears (arrears_id, org_id, batch_id, loan_ref, borrower_name, crop, region, country, exposure_eur,
                                      days_past_due, as_of_date, uploaded_by, money_source)
            VALUES (CAST(:a AS uuid), CAST(:o AS uuid), CAST(:b AS uuid), :ref, :bn, :crop, :reg, :country, :exp, :dpd,
                    CAST(:asof AS date), CAST(:u AS uuid), CAST(:ms AS jsonb))
        """), {"a": str(uuid.uuid4()), "o": org_id, "b": bid, "ref": ref[:80], "bn": str(r.get("borrower_name") or "")[:200],
               "crop": (str(r.get("crop")).strip() or None) if r.get("crop") else None,
               "reg": (str(r.get("region")).strip() or None) if r.get("region") else None,
               "country": country, "exp": exp, "dpd": dpd, "asof": asof, "u": user_id, "ms": ms})
        n += 1
    session.commit()
    return {"batch_id": bid, "rows": n, "skipped": skipped[:50], "n_skipped": len(skipped)}


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
        SELECT loan_ref, borrower_name, crop, region, country, CAST(exposure_eur AS FLOAT) AS exposure_eur, days_past_due, as_of_date
        FROM loan_arrears WHERE org_id = CAST(:o AS uuid) AND batch_id = CAST(:b AS uuid) AND days_past_due >= :m
        ORDER BY exposure_eur DESC NULLS LAST
    """), {"o": org_id, "b": batch["b"], "m": MIN_DPD}).mappings().all()

    # pre-fetch only the (crop_key, country) pairs actually on the book, before classifying anything
    keys = {(_crop_key(r["crop"]), r["country"].upper()) for r in rows if r["crop"] and r["country"]}
    keys = {(k, c) for k, c in keys if k}
    shocks = _yield_shock_map(session, keys)

    loans = []
    totals = {"seasonal": 0.0, "climate_attributed": 0.0, "genuine": 0.0}
    counts = {"seasonal": 0, "climate_attributed": 0, "genuine": 0}
    n_no_country = 0
    for r in rows:
        # crop_yield_observations.season_year is the crop-year END — the as_of_date's own year is the honest default
        season_year = (r["as_of_date"] or date.today()).year
        res = classify_loan(r["crop"], r["days_past_due"], month, r["country"], shocks, season_year)
        exp = r["exposure_eur"] or 0
        cls = res["classification"]
        totals[cls] += exp
        counts[cls] += 1
        if not r["country"] and cls != "seasonal":
            n_no_country += 1
        loans.append({"loan_ref": r["loan_ref"], "borrower_name": r["borrower_name"], "crop": r["crop"],
                      "region": r["region"], "country": r["country"], "exposure_eur": round(exp),
                      "days_past_due": r["days_past_due"], "classification": cls, "rationale": res["rationale"]})
    total_eur = sum(totals.values())
    return {
        "available": True, "as_of": batch["asof"].isoformat() if batch["asof"] else None, "assessed_month": month,
        "seasonal_cap_days": SEASONAL_MAX_DPD, "yield_shock_threshold_pct": YIELD_SHOCK_THRESHOLD_PCT,
        "summary": {
            "n_past_due": len(loans), "past_due_eur": round(total_eur),
            "n_seasonal": counts["seasonal"], "seasonal_eur": round(totals["seasonal"]),
            "n_climate_attributed": counts["climate_attributed"], "climate_attributed_eur": round(totals["climate_attributed"]),
            "n_genuine": counts["genuine"], "genuine_eur": round(totals["genuine"]),
            "reclassified_pct": round(100 * (totals["seasonal"] + totals["climate_attributed"]) / total_eur, 1) if total_eur else 0,
            "n_not_checked_no_country": n_no_country,
        },
        "loans": loans,
    }
