from __future__ import annotations
from typing import Optional

import h3
from core.config import settings


def latlng_to_cell(lat: float, lng: float, resolution: Optional[int] = None) -> str:
    return h3.latlng_to_cell(lat, lng, resolution or settings.H3_RESOLUTION)


def cell_to_parent(cell: str, resolution: int) -> str:
    return h3.cell_to_parent(cell, resolution)


def cells_in_bbox(min_lat: float, min_lng: float, max_lat: float, max_lng: float) -> set[str]:
    """Return all H3 cells at configured resolution covering a bounding box."""
    polygon = h3.LatLngPoly([
        (min_lat, min_lng),
        (min_lat, max_lng),
        (max_lat, max_lng),
        (max_lat, min_lng),
    ])
    return h3.h3shape_to_cells(polygon, settings.H3_RESOLUTION)
