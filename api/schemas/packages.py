from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


class PackageCreateRequest(BaseModel):
    framework:      str          = Field(..., pattern="^(ECB|CSRD)$")
    period_start:   date
    period_end:     date
    maker_user_id:  str          = Field(..., min_length=3)
    company_name:   Optional[str] = None
    nace_codes:     list[str]    = []
    scenarios:      list[str]    = ["baseline"]
    time_horizons:  list[str]    = ["current", "2030", "2050"]


class PackageApproveRequest(BaseModel):
    checker_user_id: str = Field(..., min_length=3)


class PackageSummary(BaseModel):
    package_id:   str
    framework:    str
    period_start: str
    period_end:   str
    status:       str
    maker:        str
    checker:      Optional[str] = None
    released_at:  Optional[str] = None
    created_at:   str


class PackageResponse(PackageSummary):
    customer_id:   str
    model_version: str
    is_released:   bool
    package_data:  Optional[dict] = None


class PackageCreateResponse(BaseModel):
    package_id:  str
    status:      str
    framework:   str
    customer_id: str
    period_start: str
    period_end:   str
    maker:        str
    n_scores:     int
    summary:      dict
    created_at:   str
    is_released:  bool


class PackageApproveResponse(BaseModel):
    package_id:  str
    status:      str
    framework:   str
    maker:       str
    checker:     str
    released_at: str
    immutable:   bool
