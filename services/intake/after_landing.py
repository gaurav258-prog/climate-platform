"""What a landed book starts by itself (the product owner's decision of 2026-10-23: once a file is accepted, the platform
works by itself): its new places scored, and — for a book of physical assets — its loss run for today's climate. Both run
on the jobs layer, never inside the request; risk indicators and decisions read the landed book live.
"""
from __future__ import annotations

from typing import Optional

from services.intake.catalog import Template


def dispatch(org_id: str, tpl: Template, cell_coords: dict, actor_user: Optional[str]) -> dict:
    return {**_scoring(cell_coords), **_losses(org_id, tpl, actor_user)}


def _scoring(cell_coords: dict) -> dict:
    if not cell_coords:
        return {}
    try:   # never inside the request: raster reads run on the jobs layer (worker or child process)
        from services.tasks.jobs import submit
        return {"scoring": "queued", "n_cells": len(cell_coords), **submit("scoring.process_cells", cell_coords)}
    except Exception as exc:  # noqa: BLE001 — dispatch is best-effort; the rows are already stored
        return {"scoring": "deferred", "n_cells": len(cell_coords), "note": f"scoring will run when available ({type(exc).__name__})"}


def _losses(org_id: str, tpl: Template, actor_user: Optional[str]) -> dict:
    """A book of physical assets that lands queues its loss run for today's climate (the product owner's decision of
    2026-10-23: once a file is accepted the platform works by itself). The run reads the curves the organisation chose —
    none chosen, each figure is the named gap saying so."""
    if not tpl.loss_book:
        return {}
    try:   # never inside the request: the loss engine runs on the jobs layer
        from services.tasks.jobs import submit
        return {"losses": {"state": "queued", "book": tpl.loss_book,
                           **submit("loss.run", org_id, tpl.loss_book, "baseline", "current", actor_user)}}
    except Exception as exc:  # noqa: BLE001 — dispatch is best-effort; the rows are already stored
        return {"losses": {"state": "deferred", "book": tpl.loss_book,
                           "note": f"losses will run when available ({type(exc).__name__})"}}
