"""Voluntary (additional) PAI — Delegated Regulation (EU) 2022/1288, Annex I, Tables 2 & 3.

SFDR requires a manager to ADOPT at least one additional environmental indicator (Table 2) and at least one additional
social indicator (Table 3) (Article 6(1)). This module:

  * offers every Table 2 / Table 3 row that can be built from per-issuer values — keyed on its official row number,
    with its official wording and aggregation, from the governing spec and its binding (services/governance/
    sfdr_binding.py) — never a hand-kept list;
  * computes the roll-up over the issuer values the manager supplied, as the metric's wording requires (share of
    invested value; attributed per € million invested; value-weighted average of an issuer ratio), coverage disclosed;
  * reports adoption compliance: ≥1 environmental AND ≥1 social indicator adopted?

Numbers come only from supplied data; an adopted indicator with no issuer values is surfaced as awaiting input.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

from services.asset_manager_engine import fund_descendant_ids


def _catalog() -> dict[str, dict]:
    import services.regspec as R
    from services.governance.sfdr_binding import optional_catalog
    spec = R.governing("sfdr_pai", period_end=date.today())
    return optional_catalog(spec) if spec else {}


# key → {table, row, kind, agg, unit, name, metric}; key = official table + row ('t2_6_1'), from the governing spec
CATALOG: dict[str, dict] = _catalog()


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
                   CAST(v.value_num AS FLOAT) AS num, v.value_bool AS flag,
                   (SELECT CAST(e.evic_eur AS FLOAT) FROM issuer_emissions e
                    WHERE e.issuer_id = s.issuer_id AND (e.org_id = :org OR e.org_id IS NULL) AND e.evic_eur IS NOT NULL
                    ORDER BY (e.org_id IS NULL) LIMIT 1) AS evic
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

        if entry["agg"] == "per_meur":
            # Σ (value / EVIC × issuer amount) ÷ € million invested — attributed like Table 1 no. 8-9 (definition (3));
            # the denominator is everything invested, coverage says how much of it carries the issuer amount + EVIC
            cov = [(r["mv"], r["num"], r["evic"]) for r in rows if r["num"] is not None and r["evic"] and r["evic"] > 0]
            cov_w = sum(mv for mv, _, __ in cov)
            value = (round(sum(min(mv / ev, 1.0) * v for mv, v, ev in cov) / (total_value / 1e6), 4)
                     if cov and total_value else None)
        else:
            if entry["agg"] == "avg":
                cov = [(r["mv"], r["num"]) for r in rows if r["num"] is not None]
            else:  # share
                cov = [(r["mv"], 1.0 if r["flag"] else 0.0) for r in rows if r["flag"] is not None]
            cov_w = sum(mv for mv, _ in cov)
            value = round(sum(mv * v for mv, v in cov) / cov_w, 2) if cov_w else None
            if entry["agg"] == "share" and value is not None:
                value = round(100 * value, 1)   # % of covered invested value
        indicators.append({
            "key": key, "table": entry["table"], "row": entry["row"], "kind": entry["kind"],
            "name": entry["name"], "metric": entry["metric"], "unit": entry["unit"], "agg": entry["agg"],
            "value": value,
            "coverage_pct": round(100 * cov_w / total_value, 1) if total_value else 0.0,
            "input_required": (None if cov_w else "per-issuer values for this indicator"
                               + (" and the issuer's enterprise value (EVIC)" if entry["agg"] == "per_meur" else "")),
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
