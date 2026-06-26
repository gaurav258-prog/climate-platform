"""
Regulatory Packager — orchestrator with 4-eyes maker/checker workflow.

Flow:
  1. maker calls create_package()  → status: DRAFT, is_released=False
  2. checker calls approve_package() → status: APPROVED, is_released=True
     (checker CANNOT be the same user as the maker)
  3. Once released, the package is immutable — no updates allowed.

The immutability guarantee matters for regulators: if a bank submits a package
to the ECB on Jan 15, the platform must be able to prove that the package_data
has not changed since it was approved. We enforce this at the application layer
(no UPDATE path exists for released packages) and the DB schema has a trigger
enforcing it at the storage layer.

This module is the ONLY writer to regulatory_packages. All other services
read-only from this table.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.db.session import get_session
from . import ecb, csrd

logger = logging.getLogger(__name__)

SUPPORTED_FRAMEWORKS = {
    "ECB":  ecb.build,
    "CSRD": csrd.build,
}


class PackagerError(Exception):
    pass


class MakerCheckerViolation(PackagerError):
    """Raised when checker and maker are the same user."""
    pass


class PackageAlreadyReleased(PackagerError):
    """Raised when attempting to modify a released package."""
    pass


def create_package(
    customer_id: str,
    framework: str,
    period_start: date,
    period_end: date,
    maker_user_id: str,
    company_name: Optional[str] = None,
    nace_codes: Optional[list[str]] = None,
    scenarios: Optional[list[str]] = None,
    time_horizons: Optional[list[str]] = None,
) -> dict:
    """
    MAKER step: Build and persist a DRAFT regulatory package.

    The package is marked is_released=False. No checker has approved it yet.
    Returns the persisted package record.

    Parameters
    ----------
    framework    : "ECB" or "CSRD"
    maker_user_id: identity of the person creating the draft (email / SSO id)
    """
    framework = framework.upper()
    if framework not in SUPPORTED_FRAMEWORKS:
        raise PackagerError(
            f"Unknown framework '{framework}'. "
            f"Supported: {list(SUPPORTED_FRAMEWORKS)}"
        )

    logger.info(f"[Packager] MAKER — {maker_user_id} creating {framework} package "
                f"for customer {customer_id}  {period_start}→{period_end}")

    # Build the package data
    builder = SUPPORTED_FRAMEWORKS[framework]
    with get_session() as session:
        package_data = builder(
            session=session,
            customer_id=customer_id,
            period_start=period_start,
            period_end=period_end,
            **({"scenarios": scenarios} if framework == "ECB" else {}),
            **({"company_name": company_name, "nace_codes": nace_codes} if framework == "CSRD" else {}),
            time_horizons=time_horizons,
        )

    # Collect score_ids referenced in the package
    score_ids = _extract_score_ids(package_data)
    model_version = _infer_model_version(package_data)

    package_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    with get_session() as session:
        session.execute(text("""
            INSERT INTO regulatory_packages (
                package_id, customer_id, framework,
                reporting_period_start, reporting_period_end,
                score_ids, model_version, methodology_doc_uri,
                package_data,
                maker_user_id, maker_at,
                is_released, created_at
            ) VALUES (
                :package_id, :customer_id, :framework,
                :period_start, :period_end,
                :score_ids, :model_version, :methodology_uri,
                CAST(:package_data AS jsonb),
                :maker_user_id, :maker_at,
                false, :created_at
            )
        """), {
            "package_id":     str(package_id),
            "customer_id":    customer_id,
            "framework":      framework,
            "period_start":   period_start,
            "period_end":     period_end,
            "score_ids":      score_ids,
            "model_version":  model_version,
            "methodology_uri": _methodology_uri(framework),
            "package_data":   _to_json(package_data),
            "maker_user_id":  maker_user_id,
            "maker_at":       now,
            "created_at":     now,
        })

    logger.info(f"[Packager] Draft created — package_id={package_id}  "
                f"scores={len(score_ids)}  status=DRAFT")

    return {
        "package_id":   str(package_id),
        "status":       "DRAFT",
        "framework":    framework,
        "customer_id":  customer_id,
        "period_start": str(period_start),
        "period_end":   str(period_end),
        "maker":        maker_user_id,
        "created_at":   str(now),
        "is_released":  False,
        "n_scores":     len(score_ids),
        "summary":      _summarise(package_data),
    }


def approve_package(
    package_id: str,
    checker_user_id: str,
) -> dict:
    """
    CHECKER step: Approve and release a DRAFT package.

    Enforces:
      - Package must exist and be in DRAFT state
      - checker_user_id must differ from maker_user_id (4-eyes rule)
      - Once released, package_data is immutable forever

    Returns the updated package record.
    """
    logger.info(f"[Packager] CHECKER — {checker_user_id} reviewing package {package_id}")

    with get_session() as session:
        row = session.execute(text("""
            SELECT package_id, maker_user_id, is_released, framework, customer_id,
                   reporting_period_start, reporting_period_end, created_at
            FROM   regulatory_packages
            WHERE  package_id = :package_id
        """), {"package_id": package_id}).mappings().fetchone()

    if not row:
        raise PackagerError(f"Package {package_id} not found")

    if row["is_released"]:
        raise PackageAlreadyReleased(
            f"Package {package_id} is already released — it is immutable and cannot be modified."
        )

    if str(row["maker_user_id"]) == str(checker_user_id):
        raise MakerCheckerViolation(
            f"4-eyes violation: checker ({checker_user_id}) cannot be the same as "
            f"maker ({row['maker_user_id']}). A different user must approve this package."
        )

    released_at = datetime.now(timezone.utc)

    with get_session() as session:
        session.execute(text("""
            UPDATE regulatory_packages
            SET    checker_user_id = :checker,
                   checker_at      = :checked_at,
                   is_released     = true,
                   released_at     = :released_at
            WHERE  package_id = :package_id
            AND    is_released = false
        """), {
            "package_id":  package_id,
            "checker":     checker_user_id,
            "checked_at":  released_at,
            "released_at": released_at,
        })

    logger.info(f"[Packager] APPROVED — package_id={package_id}  "
                f"checker={checker_user_id}  released_at={released_at}")

    return {
        "package_id":    package_id,
        "status":        "RELEASED",
        "framework":     row["framework"],
        "customer_id":   str(row["customer_id"]),
        "period_start":  str(row["reporting_period_start"]),
        "period_end":    str(row["reporting_period_end"]),
        "maker":         str(row["maker_user_id"]),
        "checker":       checker_user_id,
        "released_at":   str(released_at),
        "is_released":   True,
        "immutable":     True,
    }


def get_package(package_id: str) -> Optional[dict]:
    """Retrieve a package by ID (any state)."""
    with get_session() as session:
        row = session.execute(text("""
            SELECT * FROM regulatory_packages WHERE package_id = :package_id
        """), {"package_id": package_id}).mappings().fetchone()

    if not row:
        return None

    return {
        "package_id":   str(row["package_id"]),
        "customer_id":  str(row["customer_id"]),
        "framework":    row["framework"],
        "period_start": str(row["reporting_period_start"]),
        "period_end":   str(row["reporting_period_end"]),
        "maker":        str(row["maker_user_id"]),
        "checker":      str(row["checker_user_id"]) if row["checker_user_id"] else None,
        "is_released":  row["is_released"],
        "released_at":  str(row["released_at"]) if row["released_at"] else None,
        "model_version": row["model_version"],
        "package_data": row["package_data"],
        "created_at":   str(row["created_at"]),
    }


def list_packages(customer_id: str, framework: Optional[str] = None) -> list[dict]:
    """List all packages for a customer (metadata only, not full package_data)."""
    with get_session() as session:
        rows = session.execute(text("""
            SELECT package_id, framework, reporting_period_start, reporting_period_end,
                   is_released, released_at, maker_user_id, checker_user_id, created_at
            FROM   regulatory_packages
            WHERE  customer_id = :customer_id
            """ + ("AND framework = :framework" if framework else "") + """
            ORDER BY created_at DESC
        """), {
            "customer_id": customer_id,
            **({"framework": framework.upper()} if framework else {}),
        }).mappings().all()

    return [{
        "package_id":   str(r["package_id"]),
        "framework":    r["framework"],
        "period_start": str(r["reporting_period_start"]),
        "period_end":   str(r["reporting_period_end"]),
        "status":       "RELEASED" if r["is_released"] else "DRAFT",
        "released_at":  str(r["released_at"]) if r["released_at"] else None,
        "maker":        str(r["maker_user_id"]),
        "checker":      str(r["checker_user_id"]) if r["checker_user_id"] else None,
        "created_at":   str(r["created_at"]),
    } for r in rows]


# ── Helpers ────────────────────────────────────────────────────────────

def _extract_score_ids(package_data: dict) -> list[str]:
    """Walk the package data and collect all unique score fingerprints."""
    # regulatory_packages.score_ids is ARRAY(UUID) — we store fingerprints
    # as surrogate score references until we track score UUIDs through the package
    fingerprints = set()
    for table_key in ["t1_geographic", "t4_high_risk_assets",
                      "e1_9a_material_risks", "e1_9c_financial_exposure"]:
        for row in package_data.get(table_key, []):
            fp = row.get("fingerprint")
            if fp:
                fingerprints.add(fp)
    return list(fingerprints)


def _infer_model_version(package_data: dict) -> str:
    meth = package_data.get("t5_methodology") or package_data.get("methodology") or {}
    return meth.get("scoring_model", "ensemble-v1")


def _methodology_uri(framework: str) -> str:
    return f"https://docs.platform.internal/methodology/{framework.lower()}-v1.pdf"


def _summarise(package_data: dict) -> dict:
    return {
        "n_locations":     package_data.get("n_locations", 0),
        "n_score_records": package_data.get("n_score_records", package_data.get("n_material_risks", 0)),
        "pct_high_risk":   package_data.get("pct_high_risk", package_data.get("pct_locations_material", 0)),
    }


def _to_json(data: dict) -> str:
    import json
    from datetime import date, datetime
    def default(o):
        if isinstance(o, (date, datetime)):
            return str(o)
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")
    return json.dumps(data, default=default)
