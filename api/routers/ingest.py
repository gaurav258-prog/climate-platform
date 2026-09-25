"""Direct source-system integration — the third input mode (after manual entry and template upload).

Two audiences, two auth models, one router:
  * DATA endpoints (Bearer ingest token, tlm_live_…): a customer's SYSTEM pushes rows into its own tenant.
    They reuse the exact same ingestion cores + validation gate + golden-source scoring as the UI uploads.
  * TOKEN-management endpoints (user JWT + admin.users.manage): an admin creates / lists / revokes the
    tokens for their org. The raw token is returned exactly once, at creation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import DbSession, IngestOrg, require_permission
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/ingest", tags=["Integration"])


# ─────────────────────────── DATA endpoints (ingest token) ───────────────────────────

@router.get("/ping", summary="Verify an ingest token and see which tenant & sector it authenticates")
def ping(ctx: IngestOrg):
    """A cheap health/handshake call for a customer wiring up their integration — confirms the token works
    and reports the tenant and sector it acts as, so they hit the right ingest endpoint."""
    return {"ok": True, "org_id": ctx["org_id"], "org_name": ctx["org_name"],
            "sector": ctx["org_type"], "ready": True}


class BankAssetsIn(BaseModel):
    rows: list[dict] = Field(..., min_length=1, max_length=5000,
                             description="Loan-tape rows — same fields as the CSV template "
                                         "(asset_name, asset_type, latitude, longitude, appraised_value_eur, sector, "
                                         "counterparty_evic_eur, …).")
    declared_row_count: int | None = Field(None, description="Optional control: how many rows you are sending.")
    declared_totals: dict[str, float] | None = Field(
        None, description='Optional control totals, e.g. {"appraised_value_eur": 1250000000} — the batch is refused '
                          "if the rows do not add up to what you declared.")


@router.post("/bank/assets", summary="Push loan-tape rows directly into your bank tenant")
def ingest_bank(body: BankAssetsIn, session: DbSession, ctx: IngestOrg):
    """Land loan-tape rows via the API — identical processing to the CSV upload: the same intake controls
    (receipt, transformation, gate), then geocoding to an H3 cell and scoring against the golden source.
    A batch that fails a control is refused with the full control report (an API token cannot sign a batch off —
    fix and resend, or have a user import it in the app with a sign-off). Nothing is guessed or defaulted."""
    if ctx["org_type"] != "bank":
        raise HTTPException(409, {"error": "wrong_sector",
                                  "message": f"This token's tenant is '{ctx['org_type']}', not a bank. "
                                             f"Use the ingest endpoint for your sector."})
    import json as _json

    import pandas as pd

    from api.routers.bank import ASSET_TEMPLATE_FIELDS
    from api.services.intake_http import gate_409
    from services.ingest.batches import GateError, begin_import
    declared = {}
    if body.declared_row_count is not None:
        declared["row_count"] = body.declared_row_count
    if body.declared_totals:
        declared["control_totals"] = body.declared_totals
    raw = _json.dumps(body.rows, sort_keys=True, default=str).encode()
    try:
        ctl = begin_import(session, ctx["org_id"], None, "bank_assets", raw, pd.DataFrame(body.rows), ASSET_TEMPLATE_FIELDS,
                           filename=f"api:{ctx['token_id']}", via="api", declared=declared or None,
                           value_field="appraised_value_eur")
    except GateError as e:
        raise gate_409(e) from e
    from services.ingest.portfolio_ingest import ingest_bank_assets
    res = ingest_bank_assets(session, ctx["org_id"], ctl.clean_df.to_dict("records"))
    ctl.finish(session, n_landed=res["n_ingested"], value_landed=res.get("value_ingested"))
    write_audit(session, org_id=ctx["org_id"], actor_user_id=None, action="ingest.bank.assets",
                target_type="bank_assets", target_id=ctl.batch_id,
                detail={"n_ingested": res["n_ingested"], "n_skipped": res["n_skipped"], "batch_id": ctl.batch_id,
                        "via": "api", "token_id": ctx["token_id"]})
    return {"ingested": res["n_ingested"], "skipped": res["n_skipped"], "skipped_detail": res["skipped"],
            "batch_id": ctl.batch_id, "controls": ctl.controls, "scoring": res["processing"]}


# ─────────────────────────── TOKEN management (admin JWT) ───────────────────────────

class TokenCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80,
                      description="A label so you can tell tokens apart, e.g. 'Core banking nightly'.")


@router.post("/tokens", status_code=201, summary="Create a tenant ingest token (raw token shown once)")
def create_ingest_token(body: TokenCreate, session: DbSession,
                        ctx: dict = Depends(require_permission("admin.users.manage"))):
    from api.services.ingest_tokens import create_token
    res = create_token(session, ctx["org"]["org_id"], body.name, ctx["user"]["id"])
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="ingest.token.create", target_type="ingest_token", target_id=res["token_id"],
                detail={"name": body.name})
    return res


@router.get("/tokens", summary="List your organization's ingest tokens")
def list_ingest_tokens(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from api.services.ingest_tokens import list_tokens
    return list_tokens(session, ctx["org"]["org_id"])


@router.delete("/tokens/{token_id}", summary="Revoke an ingest token")
def revoke_ingest_token(token_id: str, session: DbSession,
                        ctx: dict = Depends(require_permission("admin.users.manage"))):
    from api.services.ingest_tokens import revoke_token
    if not revoke_token(session, token_id, ctx["org"]["org_id"]):
        raise HTTPException(404, {"error": "not_found", "message": "Token not found or already revoked."})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="ingest.token.revoke", target_type="ingest_token", target_id=token_id)
    return {"revoked": True}
