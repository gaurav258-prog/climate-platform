"""Customer-contracts vault API — role-gated (contracts.view / contracts.manage), org-scoped, audited.

Signed agreements a client's members can see per their role. Viewing/downloading needs contracts.view;
uploading/removing needs contracts.manage. Every download and mutation is written to the access audit log.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from services.governance import contracts as C

router = APIRouter(prefix="/v1/contracts", tags=["Contracts"])


@router.get("", summary="List the organization's signed customer contracts")
def list_contracts(session: DbSession, ctx: dict = Depends(require_permission("contracts.view"))):
    return {"contracts": C.list_contracts(session, ctx["org"]["org_id"]),
            "can_manage": "contracts.manage" in ctx["permissions"]}


@router.post("", status_code=201, summary="Upload a signed contract (contracts.manage)")
async def upload_contract(session: DbSession, ctx: dict = Depends(require_permission("contracts.manage")),
                          file: UploadFile = File(...), title: str = Form(...),
                          counterparty: Optional[str] = Form(None), contract_type: str = Form("other"),
                          status: str = Form("active"), signed_date: Optional[str] = Form(None),
                          effective_date: Optional[str] = Form(None), expiry_date: Optional[str] = Form(None)):
    data = await file.read()
    try:
        res = C.add_contract(session, ctx["org"]["org_id"], ctx["user"]["id"], title=title,
                             filename=file.filename or "contract", content_type=file.content_type, data=data,
                             counterparty=counterparty, contract_type=contract_type, status=status,
                             signed_date=signed_date, effective_date=effective_date, expiry_date=expiry_date)
    except C.ContractError as e:
        raise HTTPException(status_code=400, detail={"error": "contract_error", "message": str(e)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="contract.uploaded",
                target_type="customer_contract", target_id=res["contract_id"],
                detail=f"Uploaded '{res['title']}' ({res['contract_type']}, {res['size_bytes']} bytes)")
    return res


@router.get("/{contract_id}/file", summary="Download a contract (contracts.view · audited)")
def download_contract(contract_id: str, session: DbSession, ctx: dict = Depends(require_permission("contracts.view"))):
    got = C.get_contract_file(session, ctx["org"]["org_id"], contract_id)
    if not got:
        raise HTTPException(status_code=404, detail="contract not found")
    filename, content_type, data = got
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="contract.downloaded",
                target_type="customer_contract", target_id=contract_id, detail=f"Downloaded '{filename}'")
    return Response(content=data, media_type=content_type or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.delete("/{contract_id}", summary="Remove a contract (contracts.manage · audited)")
def delete_contract(contract_id: str, session: DbSession, ctx: dict = Depends(require_permission("contracts.manage"))):
    if not C.delete_contract(session, ctx["org"]["org_id"], contract_id):
        raise HTTPException(status_code=404, detail="contract not found")
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="contract.removed",
                target_type="customer_contract", target_id=contract_id, detail="Removed contract")
    return {"ok": True}
