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
    from services.intake.catalog import templates_for
    return {"ok": True, "org_id": ctx["org_id"], "org_name": ctx["org_name"],
            "sector": ctx["org_type"], "ready": True,
            "templates": [{"template": t.key, "label": t.label, "endpoint": f"/v1/ingest/books/{t.key}"}
                          for t in templates_for(ctx["org_type"])]}


class BookRowsIn(BaseModel):
    rows: list[dict] = Field(..., min_length=1, max_length=5000,
                             description="Rows of your book — our template's fields, or your own field names with a "
                                         "mapping_profile_id (see GET /v1/intake/mappings).")
    declared_row_count: int | None = Field(None, description="Optional control: how many rows you are sending.")
    declared_totals: dict[str, float] | None = Field(
        None, description='Optional control totals, e.g. {"appraised_value_eur": 1250000000} — the batch fails a check '
                          "if the rows do not add up to what you declared.")
    mapping_profile_id: str | None = Field(None, description="Optional: a saved column mapping, when your rows use your "
                                                             "own field names, units or currency.")
    currency: str | None = Field(None, min_length=3, max_length=3,
                                 description="ISO 4217 code of the amounts (e.g. EUR, USD). Required unless every row has a "
                                             "'currency' field. Never assumed.")
    book_date: str | None = Field(None, description="YYYY-MM-DD — the date the figures describe. Required unless every row "
                                                    "has a 'book_date' field. Balances convert at that day's rate; annual "
                                                    "flows at the average of the 12 months to it.")


def _push(template: str, body: BookRowsIn, session, ctx: dict):
    """Every sector's API push runs the SAME intake pipeline as a file upload: stored write-once, scanned, mapped,
    checked, matched to the book. Every check passed → imported (200). A check failed → sent for approval by a person
    other than the token's owner (202; nothing lands until approved). Nothing valid → 422."""
    import json as _json

    from api.services.intake_http import submit
    from services.intake.catalog import TEMPLATES
    tpl = TEMPLATES.get(template)
    if tpl is None:
        raise HTTPException(404, {"error": "unknown_template", "message": f"No template '{template}'.",
                                  "templates": sorted(TEMPLATES)})
    if ctx["org_type"] != tpl.org_type:
        from services.intake.catalog import templates_for
        raise HTTPException(409, {"error": "wrong_sector",
                                  "message": f"This token's tenant is '{ctx['org_type']}'; the {tpl.label} template is for "
                                             f"'{tpl.org_type}'. Your templates: {', '.join(t.key for t in templates_for(ctx['org_type'])) or 'none'}."})
    declared = {}
    if body.declared_row_count is not None:
        declared["row_count"] = body.declared_row_count
    if body.declared_totals:
        declared["control_totals"] = body.declared_totals
    raw = _json.dumps(body.rows, sort_keys=True, default=str).encode()
    return submit(session, ctx["org_id"], template, raw, f"api:{ctx['token_id']}", token_id=ctx["token_id"],
                  via="api", declared=declared or None, mapping_profile_id=body.mapping_profile_id,
                  currency=body.currency, book_date=body.book_date)


@router.post("/books/{template}", summary="Push rows of your book (any sector) directly into your tenant")
def ingest_book(template: str, body: BookRowsIn, session: DbSession, ctx: IngestOrg):
    """template: bank_assets | insurance_policies | realestate_properties | assetmgmt_holdings | supply_plots —
    the one for your sector (GET /v1/ingest/ping tells you which)."""
    return _push(template, body, session, ctx)


@router.post("/bank/assets", summary="Push loan-tape rows directly into your bank tenant (same as /books/bank_assets)")
def ingest_bank(body: BookRowsIn, session: DbSession, ctx: IngestOrg):
    return _push("bank_assets", body, session, ctx)


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
