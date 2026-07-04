from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class HazardLookupResult(BaseModel):
    hazard_type:  str
    status:       str   # 'cached_hit' | 'scored' | 'insufficient_data' | 'pending'
    risk_score:   Optional[float] = None
    risk_bucket:  Optional[str] = None
    reason:       Optional[str] = None   # populated when status='insufficient_data'
    lookup_id:    Optional[str] = None   # populated when status='pending' — poll /lookup/score/{lookup_id}


class OverallRisk(BaseModel):
    """The platform's actual pitch ('...boils it down into ONE easy number') made real.

    MAX across every hazard with a real score right now — not an average, which would
    hide a severe seismic score behind a mild drought one (same "worst governs" rule
    as pollution's own multi-pollutant sub-score and bank portfolio's headline_score).
    `status='provisional'` means at least one hazard is still computing in the
    background — re-call GET /v1/lookup/score (or poll a pending hazard's lookup_id)
    to refine. This is a MINIMUM, not a claim of full coverage: hazards_insufficient
    counts real absence-of-data, not zero risk (see core/types.py's whole hazard-
    reporting convention)."""
    score:                Optional[float] = None
    bucket:                Optional[str] = None
    driver_hazard:          Optional[str] = None
    status:                 str            # 'complete' | 'provisional'
    hazards_scored:         int
    hazards_pending:        int
    hazards_insufficient:   int


class LookupResponse(BaseModel):
    latitude:     float
    longitude:    float
    display_name: Optional[str] = None
    h3_cell:      str
    hazards:      list[HazardLookupResult]
    overall:      OverallRisk


class PollResponse(BaseModel):
    hazard:  HazardLookupResult
    overall: OverallRisk
