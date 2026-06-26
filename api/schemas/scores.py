from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ScoreResponse(BaseModel):
    h3_cell:               str
    h3_resolution:         int
    hazard_type:           str
    scenario:              str
    time_horizon:          str
    risk_score:            float = Field(..., ge=0, le=100)
    risk_bucket:           str
    score_ci_lower:        Optional[float] = None
    score_ci_upper:        Optional[float] = None
    score_velocity_6h:     Optional[float] = None
    score_velocity_24h:    Optional[float] = None
    score_velocity_48h:    Optional[float] = None
    ensemble_scores:       Optional[dict]  = None
    compound_flag:         Optional[bool]  = None
    regulatory_fingerprint: Optional[str] = None
    model_version:         str
    scored_at:             datetime
    valid_from:            datetime

    model_config = {"from_attributes": True}


class ScoreListResponse(BaseModel):
    total:  int
    scores: list[ScoreResponse]


class VelocityAlert(BaseModel):
    """Returned when score velocity exceeds a meaningful threshold."""
    h3_cell:        str
    hazard_type:    str
    velocity_24h:   float
    current_score:  float
    risk_bucket:    str
    alert_reason:   str
