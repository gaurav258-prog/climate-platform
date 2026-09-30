"""Protected-area layers — every load kept (protected_dataset_loads), the current one per dataset open.

A layer is loaded as a whole (Natura 2000, OSM, WDPA …): a new load becomes current and the previous one is retired,
never deleted, so a filing can say which load of each layer it read (current_loads) and a restatement can re-read
the same one. Every loader calls load_layer; readers read v_protected_h3_current.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


def load_layer(session: Session, dataset: str, data_vintage: date | str | None, source: str,
               cells: Iterable[dict], res: int) -> dict:
    """cells: {"h3_cell", "within_km", "site_ref"} (one per cell — the closest reading wins). Commits nothing."""
    best: dict[str, dict] = {}
    for c in cells:
        prev = best.get(c["h3_cell"])
        if prev is None or c["within_km"] < prev["within_km"]:
            best[c["h3_cell"]] = c
    old = session.execute(text("SELECT load_id FROM protected_dataset_loads WHERE dataset = :d AND retired_at IS NULL"),
                          {"d": dataset}).scalar()
    if old:
        session.execute(text("UPDATE protected_dataset_loads SET retired_at = now() WHERE load_id = :l"), {"l": old})
    load_id = session.execute(text("""
        INSERT INTO protected_dataset_loads (dataset, data_vintage, source, n_cells)
        VALUES (:d, :v, :s, :n) RETURNING load_id::text
    """), {"d": dataset, "v": data_vintage, "s": source, "n": len(best)}).scalar()
    rows = [{"l": load_id, "c": c["h3_cell"], "r": res, "d": dataset, "w": c["within_km"], "s": c.get("site_ref"),
             "v": data_vintage} for c in best.values()]
    for j in range(0, len(rows), 5000):
        session.execute(text("""
            INSERT INTO protected_h3_cell (load_id, h3_cell, h3_res, dataset, within_km, site_ref, data_vintage)
            VALUES (CAST(:l AS uuid), :c, :r, :d, :w, :s, :v)
        """), rows[j:j + 5000])
    return {"load_id": load_id, "dataset": dataset, "n_cells": len(best), "retired": old and str(old)}


def current_loads(session: Session) -> list[dict]:
    """The load of each layer a reading uses now — frozen with anything that reads protected areas."""
    rows = session.execute(text("""
        SELECT load_id::text AS load_id, dataset, data_vintage, loaded_at, n_cells
        FROM protected_dataset_loads WHERE retired_at IS NULL ORDER BY dataset
    """)).mappings().all()
    return [{**dict(r), "data_vintage": r["data_vintage"] and r["data_vintage"].isoformat(),
             "loaded_at": r["loaded_at"].isoformat()} for r in rows]
