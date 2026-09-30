"""
Regulatory package endpoints — maker/checker workflow + XBRL export.

POST /v1/packages               — MAKER: create draft
POST /v1/packages/{id}/approve  — CHECKER: release (4-eyes enforced)
GET  /v1/packages/{id}          — retrieve package (metadata + data)
GET  /v1/packages/{id}/xbrl     — retired (410): the CSRD package and its non-EFRAG XBRL
GET  /v1/packages               — list packages for authenticated customer
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.deps import CustomerId
from api.schemas.packages import (
    PackageApproveRequest,
    PackageApproveResponse,
    PackageCreateRequest,
    PackageCreateResponse,
    PackageResponse,
    PackageSummary,
)
from ml.regulatory.packager import (
    RETIRED_FRAMEWORKS,
    MakerCheckerViolation,
    PackageAlreadyReleased,
    PackagerError,
    approve_package,
    create_package,
    get_package,
    list_packages,
)

router = APIRouter(prefix="/v1/packages", tags=["Regulatory Packages"])


# ── POST /v1/packages ─────────────────────────────────────────────────

@router.post(
    "",
    response_model=PackageCreateResponse,
    status_code=201,
    summary="MAKER — Create a draft regulatory package",
    description=(
        "Builds a regulatory disclosure package from canonical scores for the "
        "customer's portfolio. Status is DRAFT until a different user approves it. "
        "ECB (T1–T5 tables). CSRD packages are retired: the ESRS statement is filed per undertaking (esrs_pack)."
    ),
)
def create(body: PackageCreateRequest, customer_id: CustomerId):
    try:
        result = create_package(
            customer_id=customer_id,
            framework=body.framework,
            period_start=body.period_start,
            period_end=body.period_end,
            maker_user_id=body.maker_user_id,
            scenarios=body.scenarios,
            time_horizons=body.time_horizons,
        )
    except PackagerError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return PackageCreateResponse(**result)


# ── POST /v1/packages/{id}/approve ───────────────────────────────────

@router.post(
    "/{package_id}/approve",
    response_model=PackageApproveResponse,
    summary="CHECKER — Approve and release a draft package",
    description=(
        "Releases a DRAFT package. The checker must be a different user from the maker "
        "(4-eyes principle). Once released the package is immutable — no further updates "
        "are possible. The package may then be submitted to the regulator."
    ),
)
def approve(package_id: str, body: PackageApproveRequest):
    try:
        result = approve_package(
            package_id=package_id,
            checker_user_id=body.checker_user_id,
        )
    except MakerCheckerViolation as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error":   "maker_checker_violation",
                "message": str(e),
            },
        )
    except PackageAlreadyReleased as e:
        raise HTTPException(
            status_code=409,
            detail={
                "error":   "package_already_released",
                "message": str(e),
            },
        )
    except PackagerError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return PackageApproveResponse(**result)


# ── GET /v1/packages/{id} ─────────────────────────────────────────────

@router.get(
    "/{package_id}",
    response_model=PackageResponse,
    summary="Retrieve a regulatory package",
)
def get(package_id: str, include_data: bool = Query(default=True)):
    pkg = get_package(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package {package_id} not found")

    if not include_data:
        pkg.pop("package_data", None)

    return PackageResponse(
        package_id=pkg["package_id"],
        customer_id=pkg["customer_id"],
        framework=pkg["framework"],
        period_start=pkg["period_start"],
        period_end=pkg["period_end"],
        status="RELEASED" if pkg["is_released"] else "DRAFT",
        maker=pkg["maker"],
        checker=pkg.get("checker"),
        released_at=pkg.get("released_at"),
        created_at=pkg["created_at"],
        model_version=pkg.get("model_version", ""),
        is_released=pkg["is_released"],
        package_data=pkg.get("package_data") if include_data else None,
    )


# ── GET /v1/packages/{id}/xbrl ────────────────────────────────────────

@router.get(
    "/{package_id}/xbrl",
    summary="Retired — CSRD XBRL export",
    description="Retired: the CSRD package exported XBRL under element names that were not EFRAG's ESRS taxonomy. The ESRS "
                "statement is filed per undertaking (report type esrs_pack) and exports JSON until EFRAG's taxonomy is bound.",
    status_code=410,
)
def export_xbrl(package_id: str):
    raise HTTPException(status_code=410, detail={"error": "retired", "message": RETIRED_FRAMEWORKS["CSRD"]})


# ── GET /v1/packages ──────────────────────────────────────────────────

@router.get(
    "",
    response_model=list[PackageSummary],
    summary="List regulatory packages for this customer",
)
def list_all(
    customer_id: CustomerId,
    framework:   Optional[str] = Query(default=None, pattern="^(ECB|CSRD)$"),
):
    packages = list_packages(customer_id=customer_id, framework=framework)
    return [PackageSummary(**p) for p in packages]
