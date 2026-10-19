"""Map geometry for the client — every drawn cell comes from the one cell service, clipped to land."""
from __future__ import annotations

import h3
from fastapi import APIRouter

from api.deps import CurrentUser
from core.errors import UserError

router = APIRouter(prefix="/v1/geo", tags=["Geo"])


@router.get("/cells", summary="Shapes of H3 cells, clipped to land (Eurostat GISCO countries 2020, 1:3M)")
def cells(ctx: CurrentUser, cells: str):
    from services.geo.cells import LAYER_LABEL, cell_shape, land_available
    ids = [c.strip() for c in cells.split(",") if c.strip()]
    if not ids or len(ids) > 2000:
        raise UserError("agri.map.cell_count")
    bad = next((c for c in ids if not h3.is_valid_cell(c)), None)
    if bad is not None:                       # a fault inside the cell service is ours, never read as a bad id
        raise UserError("agri.map.not_a_cell", cell=bad[:40])
    out = {}
    for c in ids:
        s = cell_shape(c)
        out[c] = {"rings": s["rings_latlon"], "on_land": s["on_land"], "clipped": s["clipped"], "country": s["country"]}
    return {"cells": out, "land_layer": LAYER_LABEL if land_available() else None}
