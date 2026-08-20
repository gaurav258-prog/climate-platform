"""Realized climate exposure — the observed events that have already crossed the org's own book.

The retrospective counterpart to the forward scores: real named storms + earthquakes (located books) or real
observed yield shocks (agri), matched to the institution's own assets. See services/intelligence/realized_
exposure.py. One endpoint, sector-dispatched off the caller's org type — every figure is an observed catalogue
event, nothing projected.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from api.deps import DbSession, require_permission
from services.intelligence.climate_track_record import track_record, track_record_pdf
from services.intelligence.model_validation import model_validation_all
from services.intelligence.realized_exposure import realized_exposure
from services.intelligence.underwriting_review import underwriting_review

router = APIRouter(prefix="/v1/realized-exposure", tags=["Realized exposure"])

# org type -> shared-engine vertical
_VERTICAL = {"bank": "banking", "insurer": "insurance", "reit": "realestate",
             "asset_manager": "assetmgmt", "manufacturer": "agri"}


@router.get("", summary="Real climate events that have already crossed this org's book (observed, not modelled)")
def get_realized_exposure(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    org = ctx["org"]
    vertical = _VERTICAL.get(org.get("type"))
    if not vertical:
        return {"available": False, "reason": "unsupported_sector"}
    return {"org_id": org["org_id"], "sector": org["type"],
            **realized_exposure(session, org["org_id"], vertical)}


@router.get("/underwriting-review", summary="Per-policy observed loss experience + frequency validation of the priced return period (insurance)")
def get_underwriting_review(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    """The insurance underwriting deliverable: for the caller's policy book, the real climate events that have
    already crossed each risk, plus — for perils Tellumen holds an observed catalogue for (storm, seismic) —
    whether the observed hit-rate matches the modelled return period the policy is priced on. Insurers only."""
    org = ctx["org"]
    if org.get("type") != "insurer":
        return {"available": False, "reason": "insurance_only"}
    return {"org_id": org["org_id"], "sector": org["type"], **underwriting_review(session, org["org_id"])}


@router.get("/model-validation", summary="Score vs observed-record consistency backtest (model validation / supervisory credibility)")
def get_model_validation(session: DbSession, ctx: dict = Depends(require_permission("modules.view"))):
    """Tests Tellumen's own hazard scores against the observed catalogues, for the perils with a real record
    (seismic, storm): do higher-scored locations carry more observed near-field events? Reports a per-band
    table, a Spearman discrimination metric, and an honest verdict — weak results shown as weak. In-sample
    consistency (faithfulness), not out-of-sample prediction; see the note."""
    return model_validation_all(session)


@router.get("/track-record", summary="Climate Track Record for any address — observed past + current risk (diligence)")
def get_track_record(session: DbSession,
                     lat: float = Query(..., ge=-90, le=90),
                     lon: float = Query(..., ge=-180, le=180),
                     name: str = Query(None, description="Optional label for the location/counterparty."),
                     ctx: dict = Depends(require_permission("modules.view"))):
    """The per-location diligence dossier: the real events that have already crossed this address, plus its
    current hazard scores. A different deliverable (and buyer) from the regulatory filings — underwriting,
    lending, and M&A diligence."""
    return track_record(session, lat, lon, name)


@router.get("/track-record.pdf", summary="Climate Track Record as a one-page PDF dossier (diligence hand-over)")
def track_record_pdf_ep(session: DbSession,
                        lat: float = Query(..., ge=-90, le=90),
                        lon: float = Query(..., ge=-180, le=180),
                        name: str = Query(None),
                        ctx: dict = Depends(require_permission("modules.view"))):
    fname, blob = track_record_pdf(session, lat, lon, name)
    return Response(blob, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
