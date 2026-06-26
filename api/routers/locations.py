"""
Customer location endpoints.

Customers register their physical assets here (lat/lng → H3 cell).
The H3 cell is the join key into canonical_scores.

POST /v1/locations         — register a location
GET  /v1/locations         — list all active locations for this customer
DELETE /v1/locations/{id}  — deactivate (soft-delete, never hard-delete)
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from api.deps import CustomerId, DbSession
from api.schemas.locations import (
    LocationListResponse, LocationRegisterRequest, LocationResponse,
)
from core.h3_utils import latlng_to_cell

router = APIRouter(prefix="/v1/locations", tags=["Locations"])


@router.post(
    "",
    response_model=LocationResponse,
    status_code=201,
    summary="Register a customer asset location",
    description=(
        "Registers a lat/lng asset. The platform resolves the coordinates to an H3 r8 cell "
        "which is used as the join key into canonical_scores for all future score queries."
    ),
)
def register(body: LocationRegisterRequest, customer_id: CustomerId, session: DbSession):
    location_id = uuid.uuid4()

    h3_r8 = latlng_to_cell(body.latitude, body.longitude, resolution=8)
    h3_r7 = latlng_to_cell(body.latitude, body.longitude, resolution=7)

    session.execute(text("""
        INSERT INTO customer_locations
            (location_id, customer_id, location_name,
             latitude, longitude, h3_cell_r8, h3_cell_r7,
             asset_type, asset_value, currency, is_active, registered_at)
        VALUES
            (:location_id, :customer_id, :location_name,
             :lat, :lng, :h3_r8, :h3_r7,
             :asset_type, :asset_value, :currency, true, now())
    """), {
        "location_id":   str(location_id),
        "customer_id":   customer_id,
        "location_name": body.location_name,
        "lat":           body.latitude,
        "lng":           body.longitude,
        "h3_r8":         h3_r8,
        "h3_r7":         h3_r7,
        "asset_type":    body.asset_type,
        "asset_value":   body.asset_value,
        "currency":      body.currency,
    })

    return LocationResponse(
        location_id=str(location_id),
        customer_id=customer_id,
        location_name=body.location_name,
        latitude=body.latitude,
        longitude=body.longitude,
        h3_cell_r8=h3_r8,
        asset_type=body.asset_type,
        asset_value=body.asset_value,
        currency=body.currency,
        is_active=True,
    )


@router.get(
    "",
    response_model=LocationListResponse,
    summary="List all registered locations for this customer",
)
def list_locations(customer_id: CustomerId, session: DbSession):
    rows = session.execute(text("""
        SELECT location_id, customer_id, location_name,
               CAST(latitude AS FLOAT)   AS latitude,
               CAST(longitude AS FLOAT)  AS longitude,
               h3_cell_r8, asset_type,
               CAST(asset_value AS FLOAT) AS asset_value,
               currency, is_active
        FROM   customer_locations
        WHERE  customer_id = :cid AND is_active = true
        ORDER  BY registered_at DESC
    """), {"cid": customer_id}).mappings().all()

    locations = [LocationResponse(**dict(r)) for r in rows]
    return LocationListResponse(total=len(locations), locations=locations)


@router.delete(
    "/{location_id}",
    status_code=204,
    summary="Deactivate a location (soft-delete)",
)
def deactivate(location_id: str, customer_id: CustomerId, session: DbSession):
    result = session.execute(text("""
        UPDATE customer_locations
        SET    is_active = false
        WHERE  location_id  = :location_id
        AND    customer_id  = :customer_id
        AND    is_active    = true
    """), {"location_id": location_id, "customer_id": customer_id})

    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail=f"Location {location_id} not found or already inactive.",
        )
