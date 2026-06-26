from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class LocationRegisterRequest(BaseModel):
    location_name: Optional[str] = None
    latitude:      float = Field(..., ge=-90,   le=90)
    longitude:     float = Field(..., ge=-180,  le=180)
    asset_type:    Optional[str] = None
    asset_value:   Optional[float] = Field(default=None, ge=0)
    currency:      str = "EUR"


class LocationResponse(BaseModel):
    location_id:  str
    customer_id:  str
    location_name: Optional[str]
    latitude:     Optional[float]
    longitude:    Optional[float]
    h3_cell_r8:   Optional[str]
    asset_type:   Optional[str]
    asset_value:  Optional[float]
    currency:     str
    is_active:    bool

    model_config = {"from_attributes": True}


class LocationListResponse(BaseModel):
    total:     int
    locations: list[LocationResponse]
