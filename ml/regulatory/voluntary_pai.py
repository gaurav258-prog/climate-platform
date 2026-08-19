"""Voluntary (additional) PAI — RTS Annex I Tables 2 & 3.

SFDR makes 14 investee PAI indicators mandatory, then requires the manager to
ADOPT at least one more environmental indicator (Table 2) and at least one more
social indicator (Table 3), of their choosing. This module:

  * defines a catalog of supported additional indicators (a real, curated subset
    of Tables 2 & 3), each with its table, unit and how it aggregates;
  * computes the fund roll-up over the issuer values the manager supplied —
    value-weighted mean for numeric indicators, share-of-value for yes/no ones —
    with coverage disclosed;
  * reports adoption compliance: has the manager picked ≥1 environmental AND
    ≥1 social indicator?

Numbers come only from supplied data; a selected indicator with no issuer values
is surfaced as awaiting input, never guessed.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from services.asset_manager_engine import fund_descendant_ids

# key -> catalog entry. agg: 'weighted_avg' (numeric, value-weighted) or
# 'share_true' (boolean, % of invested value where the flag is true).
CATALOG: dict[str, dict] = {
    # ── Table 2 — additional environmental ──────────────────────────────
    "water_consumption_m3_per_meur": {
        "table": 2, "kind": "environmental", "agg": "weighted_avg",
        "name": "Water consumption intensity", "unit": "m³ per €M revenue"},
    "non_recycled_waste_ratio_pct": {
        "table": 2, "kind": "environmental", "agg": "weighted_avg",
        "name": "Non-recycled waste ratio", "unit": "% of total waste"},
    "natural_species_negative_impact": {
        "table": 2, "kind": "environmental", "agg": "share_true",
        "name": "Investees negatively affecting biodiversity-sensitive areas", "unit": "% of value"},
    "deforestation_no_policy": {
        "table": 2, "kind": "environmental", "agg": "share_true",
        "name": "Investees without a deforestation policy", "unit": "% of value"},
    # ── Table 3 — additional social ─────────────────────────────────────
    "no_supplier_code_of_conduct": {
        "table": 3, "kind": "social", "agg": "share_true",
        "name": "Investees without a supplier code of conduct", "unit": "% of value"},
    "no_human_rights_policy": {
        "table": 3, "kind": "social", "agg": "share_true",
        "name": "Investees without a human-rights policy", "unit": "% of value"},
    "no_grievance_mechanism": {
        "table": 3, "kind": "social", "agg": "share_true",
        "name": "Investees without a grievance/complaints mechanism", "unit": "% of value"},
    "ceo_pay_ratio": {
        "table": 3, "kind": "social", "agg": "weighted_avg",
        "name": "Excessive CEO pay ratio (CEO / median employee)", "unit": "ratio"},
}


def catalog() -> list[dict]:
    """The selectable indicators, for the UI."""
    return [{"key": k, **v} for k, v in CATALOG.items()]


def validate_keys(keys: list[str]) -> list[str]:
    """Return any keys not in the catalog (caller rejects on non-empty)."""
    return [k for k in keys if k not in CATALOG]


def compute_voluntary_pai(session, fund_id: str, comp: Optional[dict] = None,
                          *, fund_ids=None, org_id=None) -> dict:
    """Fund roll-up of the adopted additional indicators.

    comp is the composition block (for total invested value); if omitted we sum
    the latest positions. Adoption compliance follows RTS: ≥1 environmental AND
    ≥1 social indicator must be adopted. Pass fund_ids+org_id for entity-level."""
    if org_id is None:
        org_id = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    fids = fund_ids if fund_ids is not None else fund_descendant_ids(session, fund_id)

    selected = session.execute(text("""
        SELECT DISTINCT indicator_key FROM fund_voluntary_pai
        WHERE fund_id = ANY(:fids)
    """), {"fids": fids}).scalars().all()
    selected = [k for k in selected if k in CATALOG]

    total_value = session.execute(text("""
        SELECT COALESCE(SUM(CAST(p.market_value_eur AS FLOAT)), 0) FROM fund_positions p
        WHERE p.fund_id = ANY(:fids)
          AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)
    """), {"fids": fids}).scalar() or 0.0

    indicators = []
    for key in selected:
        entry = CATALOG[key]
        rows = session.execute(text("""
            SELECT CAST(p.market_value_eur AS FLOAT) AS mv,
                   CAST(v.value_num AS FLOAT) AS num, v.value_bool AS flag
            FROM   fund_positions p
            JOIN   securities s ON s.security_id = p.security_id
            LEFT   JOIN LATERAL (
                SELECT value_num, value_bool FROM issuer_voluntary_pai
                WHERE issuer_id = s.issuer_id AND indicator_key = :k
                  AND (org_id = :org OR org_id IS NULL)
                ORDER BY (org_id IS NULL), reporting_year DESC LIMIT 1
            ) v ON TRUE
            WHERE  p.fund_id = ANY(:fids)
              AND  p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)
        """), {"fids": fids, "org": org_id, "k": key}).mappings().all()

        if entry["agg"] == "weighted_avg":
            cov = [(r["mv"], r["num"]) for r in rows if r["num"] is not None]
        else:  # share_true
            cov = [(r["mv"], 1.0 if r["flag"] else 0.0) for r in rows if r["flag"] is not None]
        cov_w = sum(mv for mv, _ in cov)
        value = round(sum(mv * v for mv, v in cov) / cov_w, 2) if cov_w else None
        if entry["agg"] == "share_true" and value is not None:
            value = round(100 * value, 1)   # express as % of covered value
        indicators.append({
            "key": key, "table": entry["table"], "kind": entry["kind"],
            "name": entry["name"], "unit": entry["unit"], "agg": entry["agg"],
            "value": value,
            "coverage_pct": round(100 * cov_w / total_value, 1) if total_value else 0.0,
            "input_required": None if cov_w else "per-issuer values for this indicator",
        })

    kinds = {CATALOG[k]["kind"] for k in selected}
    has_env, has_soc = "environmental" in kinds, "social" in kinds
    return {
        "selected": selected,
        "indicators": indicators,
        "adoption_compliant": has_env and has_soc,
        "status": "adopted" if (has_env and has_soc) else "declaration_required",
        "requirement": "Adopt ≥1 additional environmental (RTS Table 2) and ≥1 additional social (Table 3) indicator.",
        "missing": [k for k, ok in (("environmental", has_env), ("social", has_soc)) if not ok],
        "input_required": (None if (has_env and has_soc)
                           else "select the additional indicators the fund adopts (≥1 environmental + ≥1 social)"),
    }
