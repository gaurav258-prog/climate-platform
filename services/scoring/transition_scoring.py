"""Runner that populates issuer_transition_scores from issuer_emissions +
issuer sector, using ml/scoring/transition_risk.py. The transition analogue of
the physical scoring engine writing canonical_scores: append-only, supersedes
prior current rows (valid_to), reproducible via model_version + data_vintage.

Never invents inputs — an issuer with no emissions and a no-thesis sector simply
gets no transition score (honest absence), exactly like an unscored h3 cell.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from ml.scoring.transition_risk import CARBON_PRICE_EUR, MODEL_VERSION, transition_score

# Same scenario × horizon grid the physical side uses.
SCENARIOS = list(CARBON_PRICE_EUR.keys())
HORIZONS = ["current", "2030", "2050", "2100"]


def score_all_issuers(session, issuer_ids: list[str] | None = None) -> dict:
    """Recompute transition scores for every scenario × horizon and append them,
    superseding the prior current rows. Returns a small run summary."""
    where = "WHERE i.issuer_id = ANY(:ids)" if issuer_ids else ""
    issuers = session.execute(text(f"""
        SELECT i.issuer_id::text AS issuer_id, i.nace_code,
               e.scope1_tco2e, e.scope2_tco2e, e.scope3_tco2e, e.revenue_eur, e.reporting_year
        FROM issuers i
        LEFT JOIN LATERAL (
            SELECT scope1_tco2e, scope2_tco2e, scope3_tco2e, revenue_eur, reporting_year
            FROM issuer_emissions WHERE issuer_id = i.issuer_id
            ORDER BY reporting_year DESC, (source='disclosed') DESC LIMIT 1
        ) e ON TRUE
        {where}
    """), ({"ids": issuer_ids} if issuer_ids else {})).mappings().all()

    now = datetime.now(timezone.utc)
    written = 0
    scored_issuers = set()
    for iss in issuers:
        rows = []
        for scenario in SCENARIOS:
            for horizon in HORIZONS:
                blk = transition_score(
                    iss["scope1_tco2e"] and float(iss["scope1_tco2e"]),
                    iss["scope2_tco2e"] and float(iss["scope2_tco2e"]),
                    iss["scope3_tco2e"] and float(iss["scope3_tco2e"]),
                    iss["revenue_eur"] and float(iss["revenue_eur"]),
                    iss["nace_code"], scenario, horizon,
                )
                if blk:
                    rows.append((scenario, horizon, blk))
        if not rows:
            continue  # honest absence — no emissions and no sector thesis
        scored_issuers.add(iss["issuer_id"])
        # supersede prior current rows for this issuer, then append the new ones
        session.execute(text("""
            UPDATE issuer_transition_scores SET valid_to = :now
            WHERE issuer_id = :iid AND valid_to IS NULL
        """), {"iid": iss["issuer_id"], "now": now})
        for scenario, horizon, blk in rows:
            session.execute(text("""
                INSERT INTO issuer_transition_scores
                    (issuer_id, scenario, time_horizon, transition_risk_score, risk_bucket,
                     carbon_intensity_tco2e_per_meur, stranded_asset_pct, carbon_price_impact_eur,
                     model_version, data_vintage)
                VALUES (:iid, :s, :h, :score, :bucket, :ci, :strand, :impact, :mv, :vintage)
            """), {
                "iid": iss["issuer_id"], "s": scenario, "h": horizon,
                "score": blk["transition_risk_score"], "bucket": blk["risk_bucket"],
                "ci": blk["carbon_intensity_tco2e_per_meur"], "strand": blk["stranded_asset_pct"],
                "impact": blk["carbon_price_impact_eur"], "mv": MODEL_VERSION,
                "vintage": now,
            })
            written += 1
    return {"model_version": MODEL_VERSION, "issuers_scored": len(scored_issuers),
            "issuers_seen": len(issuers), "rows_written": written}
