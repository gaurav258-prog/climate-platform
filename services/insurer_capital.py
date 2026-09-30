"""An insurer's capital position and the reinsurance in force, for a reporting period — read once, here, from the values
the undertaking states under Solvency II (datapoint catalog 'insurer_solvency', provided and attested under four eyes;
services.governance.provided_data). Every insurer report that needs them (net nat-cat losses, the ORSA climate
analysis, the recovery-plan stress) reads them from here, so a figure is stated once and frozen with the filing.

A value not yet attested is absent (None) — never assumed. The reinsurance programme falls back to the platform's
illustrative programme only where no treaty is attested, and says so (basis 'illustrative_standard').
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

FRAMEWORK = "insurer_solvency"
CAPITAL = ("eligible_own_funds_scr", "scr_total", "mcr_total")
TREATY = {"ri_quota_share_pct": "quota_share_pct", "ri_xol_attachment_eur": "xol_attachment_eur",
          "ri_xol_limit_eur": "xol_limit_eur"}
REINSTATEMENT = {"ri_xol_reinstatements": "xol_reinstatements", "ri_xol_reinstatement_premium_eur": "xol_reinstatement_premium_eur"}
ILLUSTRATIVE_PROGRAMME = {"quota_share_pct": 20.0, "xol_attachment_eur": 50_000_000, "xol_limit_eur": 100_000_000}


def _attested(session: Session, org_id: str, period_end: date) -> dict:
    from services.governance.provided_data import attested_values
    return {v["key"].removeprefix("provided."): v for v in attested_values(session, org_id, FRAMEWORK, period_end)}


def position(session: Session, org_id: str, period_end: date) -> dict:
    """{eligible_own_funds_scr, scr_total, mcr_total, scr_ratio_pct, provenance}: None where not attested."""
    a = _attested(session, org_id, period_end)
    vals = {k: (float(a[k]["value"]) if k in a and a[k]["value"] is not None else None) for k in CAPITAL}
    of, scr = vals["eligible_own_funds_scr"], vals["scr_total"]
    return {**vals, "scr_ratio_pct": round(100 * of / scr, 1) if of is not None and scr else None,
            "period_end": period_end.isoformat(),
            "provenance": {k: {"attested_by": a[k]["attested_by"], "attested_at": a[k]["attested_at"], "provider": a[k]["provider"]}
                           for k in CAPITAL if k in a}}


def programme(session: Session, org_id: str, period_end: date) -> tuple[dict, str]:
    """(the reinsurance programme in force, its basis): the attested treaty terms, or — where none is attested — the
    illustrative programme, labelled as such. A partly attested programme uses what is attested and 0 for the rest
    (no quota share / no cat layer), never the illustrative figure."""
    a = _attested(session, org_id, period_end)
    if not any(k in a for k in TREATY):
        return dict(ILLUSTRATIVE_PROGRAMME), "illustrative_standard"
    prog = {name: float(a[k]["value"]) if k in a and a[k]["value"] is not None else 0.0 for k, name in TREATY.items()}
    # reinstatements: absent stays absent (None) — the nat-cat scenarios then assume none (declared reading)
    prog.update({name: float(a[k]["value"]) if k in a and a[k]["value"] is not None else None
                 for k, name in REINSTATEMENT.items()})
    return prog, "attested"


def natcat_other_regions(session: Session, org_id: str, period_end: date) -> dict:
    """{peril: {"by_region": {Annex III region: premium}}} — the premiums to be earned for risks outside Annex XIII, as
    the undertaking states them on S.27.01.01 (supplied template cells, attested under four eyes). A region not
    attested is absent; with none, the standard formula marks the peril incomplete and never charges zero."""
    import services.regspec as R
    from services.governance import s2701
    spec = R.governing(s2701.FAMILY, period_end=period_end)
    if spec is None:
        return {}
    a = _attested(session, org_id, period_end)
    supplied = {k: v["value"] for k, v in a.items() if k.startswith(f"{s2701.TID}.")}
    return s2701.premiums_from_supplied(spec, supplied)
