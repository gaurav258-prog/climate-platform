"""Map geometry for the client — every drawn cell comes from the one cell service, clipped to land."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.deps import CurrentUser

router = APIRouter(prefix="/v1/geo", tags=["Geo"])


@router.get("/cells", summary="Shapes of H3 cells, clipped to land (Eurostat GISCO countries 2020, 1:3M)")
def cells(ctx: CurrentUser, cells: str):
    from services.geo.cells import LAYER_LABEL, cell_shape, land_available
    ids = [c.strip() for c in cells.split(",") if c.strip()]
    if not ids or len(ids) > 2000:
        raise HTTPException(status_code=422, detail={"error": "invalid", "message": "Pass 1 to 2000 cell ids."})
    out = {}
    for c in ids:
        try:
            s = cell_shape(c)
        except Exception:
            raise HTTPException(status_code=422, detail={"error": "invalid", "message": f"{c} is not an H3 cell id."})
        out[c] = {"rings": s["rings_latlon"], "on_land": s["on_land"], "clipped": s["clipped"], "country": s["country"]}
    return {"cells": out, "land_layer": LAYER_LABEL if land_available() else None}
