"""Per-org reporting basis — one place the assemblers read their scenario / horizon / materiality.

Platform defaults, overridden by an org row (org_reporting_settings). Keeps the ESRS/Taxonomy
assemblers free of hardcoded constants so a compliance officer can set the basis as the rules move
(Omnibus). The r²≥0.40 publish gate is intentionally NOT configurable — it's an honesty constant.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

# EUR is today's platform-wide presentation currency; an org changes it here (governed) — it is a visible setting,
# never an assumption hidden in code.
DEFAULTS = {"scenario": "baseline", "horizon": "current", "materiality_threshold": 40, "presentation_currency": "EUR"}


def get_settings(session: Session, org_id: str) -> dict:
    """The org's reporting basis, merged over the platform defaults (period defaults to last year-end)."""
    row = session.execute(text("""
        SELECT reporting_period_end, scenario, horizon, materiality_threshold, presentation_currency
        FROM org_reporting_settings WHERE org_id = :o
    """), {"o": org_id}).mappings().first()
    out = dict(DEFAULTS)
    out["reporting_period_end"] = f"{date.today().year - 1}-12-31"
    if row:
        if row["scenario"]:
            out["scenario"] = row["scenario"]
        if row["horizon"]:
            out["horizon"] = row["horizon"]
        if row["materiality_threshold"] is not None:
            out["materiality_threshold"] = int(row["materiality_threshold"])
        if row["presentation_currency"]:
            out["presentation_currency"] = row["presentation_currency"].strip()
        if row["reporting_period_end"]:
            out["reporting_period_end"] = row["reporting_period_end"].isoformat()
    out["is_override"] = bool(row)
    return out


def upsert_reporting_settings(session: Session, org_id: str, updates: dict, updated_by: str) -> dict:
    """Set the org's reporting basis (COALESCE upsert). The r²≥0.40 publish gate is deliberately NOT
    settable here — it's an honesty constant, not a knob. Returns the resolved settings."""
    ccy = updates.get("presentation_currency")
    if ccy is not None:
        from services.intake.money import validate_declaration
        ccy, _ = validate_declaration(session, ccy, None)          # a currency we can convert, or MoneyError
    session.execute(text("""
        INSERT INTO org_reporting_settings (org_id, reporting_period_end, scenario, horizon, materiality_threshold,
                                            presentation_currency, updated_by, updated_at)
        VALUES (:o, :p, COALESCE(:s,'baseline'), COALESCE(:h,'current'), COALESCE(:m,40), :c, :u, now())
        ON CONFLICT (org_id) DO UPDATE SET
            reporting_period_end = COALESCE(EXCLUDED.reporting_period_end, org_reporting_settings.reporting_period_end),
            scenario = COALESCE(EXCLUDED.scenario, org_reporting_settings.scenario),
            horizon = COALESCE(EXCLUDED.horizon, org_reporting_settings.horizon),
            materiality_threshold = COALESCE(EXCLUDED.materiality_threshold, org_reporting_settings.materiality_threshold),
            presentation_currency = COALESCE(EXCLUDED.presentation_currency, org_reporting_settings.presentation_currency),
            updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"o": org_id, "p": updates.get("reporting_period_end"), "s": updates.get("scenario"),
           "h": updates.get("horizon"), "m": updates.get("materiality_threshold"), "c": ccy, "u": updated_by})
    return get_settings(session, org_id)
