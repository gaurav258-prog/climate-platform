"""Platform metadata — the browsable data dictionary of the single golden model."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/meta", tags=["Meta"])


@router.get("/data-dictionary", summary="The single golden model — fields, source feeds, vintage, consumers")
def data_dictionary(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.data_dictionary import data_dictionary as _dd
    return _dd(session)


@router.get("/hazard-coverage", summary="Coverage of the EU Taxonomy's 28 physical climate hazards, by maturity tier")
def hazard_coverage(ctx: dict = Depends(require_permission("modules.view"))):
    """The completeness scoreboard: our channels mapped onto the EU Taxonomy's 28 hazards, each stamped with a
    maturity tier (calibrated / screening / reference / roadmap). Static registry — no tenant data — so it needs
    only view access. Coverage ≠ calibration; the tier says which claim we're making."""
    from services.intelligence.coverage import eu_taxonomy_coverage
    return eu_taxonomy_coverage()
