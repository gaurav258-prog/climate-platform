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


class LookupResponse(BaseModel):
    latitude:     float
    longitude:    float
    display_name: Optional[str] = None
    h3_cell:      str
    hazards:      list[HazardLookupResult]
