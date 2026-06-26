"""
Asset risk projection — the one path from canonical_scores to any customer asset.

Reconciliation step #1. Before this, the bank vertical stored its own
`climate_hazard_exposure.physical_risk_score`, populated from uploads or
third-party maps, with no link to the platform's golden source. That made the
flagship product an island: it did not consume the engine it was built on.

This module makes an asset's physical risk a PROJECTION of `canonical_scores`,
matched by H3 cell — never an independently stored value. It is deliberately
sector-AGNOSTIC: it talks about "assets" with an `h3_cell`, not "bank assets".
The same function serves banking, insurance, agriculture — any sector — because
they all reduce to "a located asset" projected onto the canonical score.

The DB query is a thin adapter; the selection/bucketing logic is a pure function
(`project`) so it is deterministic and testable without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from core.types import normalize_hazard, normalize_scenario, score_to_bucket


@dataclass(frozen=True)
class Asset:
    """A located customer asset. `h3_cell` is the only field used for matching."""
    asset_id: str
    h3_cell: Optional[str]


@dataclass(frozen=True)
class CanonicalScoreRow:
    """A row from canonical_scores (the subset the projection needs)."""
    h3_cell: str
    hazard_type: str
    scenario: str
    time_horizon: str
    risk_score: float
    scored_at: datetime
    model_version: str
    valid_to: Optional[datetime] = None  # None == current (the active score)


@dataclass(frozen=True)
class AssetRisk:
    """
    An asset's physical risk for one hazard, PROJECTED from canonical_scores.
    `source` makes provenance explicit: 'canonical' when a score was found,
    'no_canonical_score' when the cell has not been scored (never a silent 0).
    """
    asset_id: str
    h3_cell: Optional[str]
    hazard_type: str
    scenario: str
    time_horizon: str
    risk_score: Optional[float]
    risk_bucket: Optional[str]
    model_version: Optional[str]
    scored_at: Optional[datetime]
    source: str


def project(
    assets: Iterable[Asset],
    scores: Iterable[CanonicalScoreRow],
    *,
    scenario: str = "baseline",
    time_horizon: str = "current",
) -> list[AssetRisk]:
    """
    Project canonical scores onto assets by H3 cell. Pure function.

    For each asset × hazard present in `scores` for the requested
    scenario/horizon, emit the latest current score (valid_to is None, max
    scored_at). The bucket is DERIVED via score_to_bucket — never read from a
    stored column, so it can never disagree with the score. Assets whose cell
    has no score still appear, with source='no_canonical_score'.
    """
    canonical_scenario = normalize_scenario(scenario).value
    # time_horizon stays as given (already canonical in callers); validated by DB.

    # Index current scores by (h3_cell, hazard), keeping the latest.
    latest: dict[tuple[str, str], CanonicalScoreRow] = {}
    for s in scores:
        if s.valid_to is not None:
            continue
        if normalize_scenario(s.scenario).value != canonical_scenario:
            continue
        if s.time_horizon != time_horizon:
            continue
        hazard = normalize_hazard(s.hazard_type).value
        key = (s.h3_cell, hazard)
        prev = latest.get(key)
        if prev is None or s.scored_at > prev.scored_at:
            latest[key] = s

    # Which hazards are in play (so we can report no-data per hazard per asset).
    hazards_in_play = sorted({h for (_cell, h) in latest})

    results: list[AssetRisk] = []
    for asset in assets:
        matched_any = False
        for (cell, hazard), s in latest.items():
            if asset.h3_cell is not None and cell == asset.h3_cell:
                matched_any = True
                results.append(AssetRisk(
                    asset_id=asset.asset_id,
                    h3_cell=asset.h3_cell,
                    hazard_type=hazard,
                    scenario=canonical_scenario,
                    time_horizon=time_horizon,
                    risk_score=float(s.risk_score),
                    risk_bucket=score_to_bucket(float(s.risk_score)).value,
                    model_version=s.model_version,
                    scored_at=s.scored_at,
                    source="canonical",
                ))
        if not matched_any:
            # Asset cell not scored — surface explicitly, once per hazard in play
            # (or a single placeholder row if nothing is scored at all).
            for hazard in (hazards_in_play or [None]):
                results.append(AssetRisk(
                    asset_id=asset.asset_id,
                    h3_cell=asset.h3_cell,
                    hazard_type=hazard,
                    scenario=canonical_scenario,
                    time_horizon=time_horizon,
                    risk_score=None,
                    risk_bucket=None,
                    model_version=None,
                    scored_at=None,
                    source="no_canonical_score",
                ))
    return results


# ── DB adapter ───────────────────────────────────────────────────────────────

_PORTFOLIO_RISK_SQL = """
    SELECT DISTINCT ON (ba.asset_id, cs.hazard_type)
           ba.asset_id::text       AS asset_id,
           ba.h3_cell              AS h3_cell,
           cs.hazard_type          AS hazard_type,
           cs.scenario             AS scenario,
           cs.time_horizon         AS time_horizon,
           CAST(cs.risk_score AS FLOAT) AS risk_score,
           cs.model_version        AS model_version,
           cs.scored_at            AS scored_at
    FROM   bank_assets     ba
    JOIN   canonical_scores cs ON cs.h3_cell = ba.h3_cell
    WHERE  ba.org_id       = :org_id
    AND    cs.scenario     = :scenario
    AND    cs.time_horizon = :horizon
    AND    cs.valid_to     IS NULL
    ORDER  BY ba.asset_id, cs.hazard_type, cs.scored_at DESC
"""


def project_org_assets(
    session,
    org_id: str,
    *,
    scenario: str = "baseline",
    time_horizon: str = "current",
) -> list[AssetRisk]:
    """
    DB-backed projection for one organisation's assets. Thin wrapper: the join
    is canonical_scores ⋈ bank_assets ON h3_cell — the same projection the
    platform's /v1/scores/portfolio endpoint uses, applied to the bank vertical
    so it stops storing its own physical_risk_score.
    """
    from sqlalchemy import text

    canonical_scenario = normalize_scenario(scenario).value
    rows = session.execute(text(_PORTFOLIO_RISK_SQL), {
        "org_id": org_id,
        "scenario": canonical_scenario,
        "horizon": time_horizon,
    }).mappings().all()

    return [
        AssetRisk(
            asset_id=r["asset_id"],
            h3_cell=r["h3_cell"],
            hazard_type=normalize_hazard(r["hazard_type"]).value,
            scenario=r["scenario"],
            time_horizon=r["time_horizon"],
            risk_score=float(r["risk_score"]),
            risk_bucket=score_to_bucket(float(r["risk_score"])).value,
            model_version=r["model_version"],
            scored_at=r["scored_at"],
            source="canonical",
        )
        for r in rows
    ]
