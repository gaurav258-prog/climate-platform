"""SFDR PAI 5 and 6 from company energy facts — reported → vendor → estimated, per company, with a plausibility check.

The European ESG Template asks PAI 5 as two figures (non-renewable share of energy CONSUMPTION; of energy PRODUCTION
for producers) and PAI 6 per high-impact NACE section. Each company's figure is taken in order of authority:

    1. what the company / manager reports, or a data vendor gives (issuer_esg_metrics, read with the usual precedence:
       the manager's own figure over a vendor's)
    2. derived from its reported energy use and revenue (energy_consumption_gwh ÷ revenue)
    3. only then an ESTIMATE (services.reference.energy_estimation: EU sector / country averages) — flagged, and the share
       of the fund's value resting on estimates is reported with every indicator

An estimate never overrides a real figure. A real figure that looks like a unit slip — an energy intensity more than 10×
away from its sector average (MWh typed as GWh is 1,000×; a misplaced decimal 10×), or a share written as a fraction
(0.6 where 60% is meant) — is flagged until a person corrects it or confirms it as right, with a reason
(issuer_data_confirmations, for that exact value). An unresolved flag blocks an EET version.
The bands are deliberately wide: tested on the demo book, a 3× / 40-point band flagged five figures that are genuinely
different (a company buying renewable power is far below its country's average) — a check that mostly flags correct
figures trains people to click "confirm". Ordinary differences from the average are expected and not flagged.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from services.governance.pillar3_templates import HIGH_CLIMATE_NACE

EET_SECTIONS = ("A", "B", "C", "D", "E", "F", "G", "H", "L", "M")
INTENSITY_BAND = 10.0         # a reported intensity beyond 10× (or under 1/10 of) the sector average is checked
FRACTION_MAX = 1.0            # a reported % share of 1 or less, where the country average is well above, looks like a fraction
FRACTION_MIN_ESTIMATE = 5.0
FIELD_LABEL = {"energy_intensity": "energy intensity (GWh per €M revenue)",
               "non_renewable_consumption": "non-renewable share of energy consumption (%)",
               "non_renewable_production": "non-renewable share of energy production (%)"}


def energy_facts(rows: list[dict]) -> list[dict]:
    """Per holding: {section, intensity, cons, prod} each (value, 'reported'|'estimated', basis) or None, plus the
    estimate alongside any reported figure ({field: (reported, estimate, basis)}) for the plausibility check."""
    from services.reference import energy_estimation as EE
    out = []
    for r in rows:
        sec = EE.section(r["nace_code"])
        est_i, est_c = EE.intensity(r["nace_code"]), EE.non_renewable_consumption(r.get("country"))
        est_p = EE.non_renewable_production(r.get("country")) if sec == "D" else None
        pairs = {}
        if r["energy_int"] is not None:
            inten = (r["energy_int"], "reported", "reported energy intensity")
        elif r["energy_gwh"] is not None and r.get("revenue_eur"):
            inten = (r["energy_gwh"] / (r["revenue_eur"] / 1e6), "reported", "reported energy use ÷ revenue")
        else:
            inten = (est_i["value"], "estimated", est_i["basis"]) if est_i else None
        if inten and inten[1] == "reported" and est_i:
            pairs["energy_intensity"] = (inten[0], est_i["value"], est_i["basis"])
        if r["nr_cons"] is not None:
            cons = (r["nr_cons"], "reported", "reported")
        elif r["non_renew"] is not None:
            cons = (r["non_renew"], "reported", "reported combined consumption + production share")
        else:
            cons = (est_c["value"], "estimated", est_c["basis"]) if est_c else None
        if cons and cons[1] == "reported" and est_c:
            pairs["non_renewable_consumption"] = (cons[0], est_c["value"], est_c["basis"])
        prod = None
        if sec == "D":                               # production share applies to energy producers
            if r["nr_prod"] is not None:
                prod = (r["nr_prod"], "reported", "reported")
                if est_p:
                    pairs["non_renewable_production"] = (prod[0], est_p["value"], est_p["basis"])
            else:
                prod = (est_p["value"], "estimated", est_p["basis"]) if est_p else None
        out.append({"section": sec, "intensity": inten, "cons": cons, "prod": prod, "pairs": pairs})
    return out


def _implausible(field: str, reported: float, estimate: float) -> Optional[str]:
    if field == "energy_intensity":
        if estimate <= 0:
            return None
        ratio = reported / estimate if reported else 0.0
        if ratio > INTENSITY_BAND or ratio < 1 / INTENSITY_BAND:
            return f"{ratio:.1f}× the sector average — check the unit (GWh, per €M of revenue)"
        return None
    if 0 < reported <= FRACTION_MAX and estimate >= FRACTION_MIN_ESTIMATE:
        return f"{reported:g}% against a country average of {estimate:.0f}% — is it a fraction (0.6) where a percentage (60) is meant?"
    return None


def outliers(session, org_id: Optional[str], rows: list[dict], energy: list[dict]) -> list[dict]:
    """Reported figures far from their estimate and not yet confirmed as right — one entry per company and field."""
    confirmed: dict[tuple, list[float]] = {}
    ids = list({r["issuer_id"] for r in rows if r.get("issuer_id")})
    if org_id and ids:
        for c in session.execute(text("""
            SELECT issuer_id::text AS issuer_id, field, CAST(value AS FLOAT) AS value FROM issuer_data_confirmations
            WHERE org_id = CAST(:o AS uuid) AND issuer_id = ANY(CAST(:i AS uuid[]))
        """), {"o": org_id, "i": ids}).mappings():
            confirmed.setdefault((c["issuer_id"], c["field"]), []).append(c["value"])
    out, seen = [], set()
    for r, f in zip(rows, energy):
        for field, (rep, est, basis) in f["pairs"].items():
            why = _implausible(field, rep, est)
            key = (r.get("issuer_id"), field)
            if not why or key in seen:
                continue
            seen.add(key)
            if any(abs(v - rep) <= 1e-9 * max(abs(rep), 1.0) for v in confirmed.get(key, [])):
                continue
            out.append({"issuer_id": r.get("issuer_id"), "issuer": r.get("issuer_name"), "field": field,
                        "label": FIELD_LABEL[field], "reported": round(rep, 6), "estimate": round(est, 6),
                        "basis": basis, "why": why})
    return out


def _weighted(rows, energy, key, total_mv, keep=lambda f: True) -> dict:
    """Value-weighted average over holdings with a figure; coverage and the estimated part as % of fund value;
    eligible = % of fund value the indicator applies to."""
    elig = [(r["mv"], f) for r, f in zip(rows, energy) if keep(f)]
    have = [(mv, f[key]) for mv, f in elig if f[key] is not None]
    w = sum(mv for mv, _ in have)
    est = sum(mv for mv, x in have if x[1] == "estimated")
    return {"value": round(sum(mv * x[0] for mv, x in have) / w, 4) if w else None,
            "coverage_pct": round(100 * w / total_mv, 1), "estimated_pct": round(100 * est / total_mv, 1),
            "eligible_pct": round(100 * sum(mv for mv, _ in elig) / total_mv, 1),
            "bases": sorted({x[2] for _, x in have if x[1] == "estimated"})[:5]}


def energy_pais(rows: list[dict], total_mv: float, energy: list[dict]) -> dict:
    cons = _weighted(rows, energy, "cons", total_mv)
    prod = _weighted(rows, energy, "prod", total_mv, keep=lambda f: f["section"] == "D")
    high = _weighted(rows, energy, "intensity", total_mv, keep=lambda f: f["section"] in HIGH_CLIMATE_NACE)
    by_section = {s: _weighted(rows, energy, "intensity", total_mv, keep=lambda f, s=s: f["section"] == s) for s in EET_SECTIONS}
    # PAI 5 as the RTS states it — ONE share per company across its energy consumption and production, value-weighted
    # once: a combined figure the company reports; else, for an energy producer, its production share (production is
    # by far its larger energy flow); else its consumption share. (Fixed 2026-09-28: producers were counted twice.)
    one = []
    for r, f in zip(rows, energy):
        x = ((r["non_renew"], "reported", "reported combined") if r.get("non_renew") is not None
             else f["prod"] if f["prod"] is not None else f["cons"])
        if x is not None:
            one.append((r["mv"], x))
    w = sum(mv for mv, _ in one)
    est_mv = sum(mv for mv, x in one if x[1] == "estimated")
    pai5 = {"value": round(sum(mv * x[0] for mv, x in one) / w, 2) if w else None,
            "coverage_pct": round(100 * w / total_mv, 1), "estimated_pct": round(100 * est_mv / total_mv, 1)}
    return {"pai_5": pai5, "pai_5_consumption": cons, "pai_5_production": prod,
            "pai_6": {k: (round(v, 2) if k == "value" and v is not None else v) for k, v in high.items()},
            "pai_6_by_section": by_section}


def confirm(session, org_id: str, issuer_id: str, field: str, value: float, reason: str, user_id: Optional[str]) -> dict:
    """A person confirms a flagged figure as right (for this exact value)."""
    if field not in FIELD_LABEL:
        raise ValueError(f"field must be one of: {', '.join(FIELD_LABEL)}")
    if not (reason or "").strip():
        raise ValueError("say why the figure is right (e.g. 'checked against the 2024 annual report, p. 112')")
    session.execute(text("""
        INSERT INTO issuer_data_confirmations (org_id, issuer_id, field, value, reason, confirmed_by)
        VALUES (CAST(:o AS uuid), CAST(:i AS uuid), :f, :v, :r, CAST(:u AS uuid))
    """), {"o": org_id, "i": issuer_id, "f": field, "v": value, "r": reason.strip()[:500], "u": user_id})
    return {"issuer_id": issuer_id, "field": field, "value": value, "confirmed": True}
