"""
Analyst Dashboard
Internal interface for reviewing and confirming detected regulatory changes
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from core.db.config import get_db
from core.db.models_regulatory_complete import (
    RegulatoryChange, RegulatoryFramework, AuditLog
)

router = APIRouter(prefix="/api/v1/analyst", tags=["analyst-dashboard"])


# ============================================================================
# SCHEMAS
# ============================================================================

class ChangeDetailResponse(BaseModel):
    change_id: str
    framework_name: str
    old_version: str
    new_version: str
    source: str
    source_url: Optional[str]
    detected_date: datetime
    status: str
    affected_tables: Optional[List[str]]
    affected_modules: Optional[List[str]]
    affected_outputs: Optional[List[str]]
    estimated_hours: Optional[int]
    is_new_module: bool
    customer_deadline: Optional[datetime]
    change_type: str


class AnalystDashboardSummary(BaseModel):
    total_detected: int
    pending_confirmation: int
    in_development: int
    ready_for_release: int
    recent_changes: List[ChangeDetailResponse]
    by_framework: dict


class ConfirmChangeRequest(BaseModel):
    is_real: bool
    notes: Optional[str] = None
    analyst_name: str


class ReleaseApprovalRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None
    approver_name: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/dashboard", response_model=AnalystDashboardSummary)
async def get_dashboard(
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=90)
):
    """
    Get analyst dashboard summary
    Shows all pending changes for review

    Returns:
    - Total detected changes
    - Breakdown by status
    - Recent changes needing review
    - Summary by framework
    """
    try:
        from sqlalchemy import func
        from datetime import timedelta

        recent_date = datetime.utcnow() - timedelta(days=days)

        # Get all changes
        all_changes = db.query(RegulatoryChange).filter(
            RegulatoryChange.detected_date >= recent_date
        ).all()

        # Count by status
        detected = len([c for c in all_changes if c.status == "Detected"])
        in_dev = len([c for c in all_changes if c.status == "In Development"])
        ready = len([c for c in all_changes if c.status == "Ready"])

        # Recent changes (last 10)
        recent_changes = sorted(
            all_changes,
            key=lambda x: x.detected_date,
            reverse=True
        )[:10]

        # By framework
        by_framework = {}
        for change in all_changes:
            framework_name = change.framework.framework_name if change.framework else "Unknown"
            if framework_name not in by_framework:
                by_framework[framework_name] = 0
            by_framework[framework_name] += 1

        return AnalystDashboardSummary(
            total_detected=len(all_changes),
            pending_confirmation=detected,
            in_development=in_dev,
            ready_for_release=ready,
            recent_changes=[
                ChangeDetailResponse(
                    change_id=str(c.change_id),
                    framework_name=c.framework.framework_name if c.framework else "Unknown",
                    old_version=c.old_version or "",
                    new_version=c.new_version or "",
                    source=c.change_source or "",
                    source_url=c.source_document_url,
                    detected_date=c.detected_date,
                    status=c.status,
                    affected_tables=c.affected_tables,
                    affected_modules=c.affected_processing_modules,
                    affected_outputs=c.affected_outputs,
                    estimated_hours=c.estimated_total_hours,
                    is_new_module=c.is_new_module or False,
                    customer_deadline=c.customer_deadline,
                    change_type=c.change_type or ""
                )
                for c in recent_changes
            ],
            by_framework=by_framework
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/pending", response_model=List[ChangeDetailResponse])
async def get_pending_changes(
    db: Session = Depends(get_db),
    framework_id: Optional[str] = None
):
    """
    Get all changes pending analyst confirmation
    These are newly detected changes (status = "Detected")
    """
    try:
        query = db.query(RegulatoryChange).filter(
            RegulatoryChange.status == "Detected"
        )

        if framework_id:
            query = query.filter(RegulatoryChange.framework_id == framework_id)

        changes = query.order_by(
            RegulatoryChange.detected_date.desc()
        ).all()

        return [
            ChangeDetailResponse(
                change_id=str(c.change_id),
                framework_name=c.framework.framework_name if c.framework else "Unknown",
                old_version=c.old_version or "",
                new_version=c.new_version or "",
                source=c.change_source or "",
                source_url=c.source_document_url,
                detected_date=c.detected_date,
                status=c.status,
                affected_tables=c.affected_tables,
                affected_modules=c.affected_processing_modules,
                affected_outputs=c.affected_outputs,
                estimated_hours=c.estimated_total_hours,
                is_new_module=c.is_new_module or False,
                customer_deadline=c.customer_deadline,
                change_type=c.change_type or ""
            )
            for c in changes
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/changes/{change_id}/confirm")
async def confirm_change(
    change_id: str,
    request: ConfirmChangeRequest,
    db: Session = Depends(get_db)
):
    """
    Analyst confirms if detected change is real
    Moves from "Detected" → "Confirmed" or archives if false alarm
    """
    try:
        change = db.query(RegulatoryChange).filter_by(
            change_id=change_id
        ).first()

        if not change:
            raise HTTPException(status_code=404, detail="Change not found")

        if request.is_real:
            change.status = "Confirmed"
            change.confirmed_by = request.analyst_name
            change.confirmed_date = datetime.utcnow()

            # Create audit log
            audit = AuditLog(
                org_id=None,  # System-level change
                entity_type="RegulatoryChange",
                entity_id=change.change_id,
                action="CONFIRMED",
                changed_by=request.analyst_name,
                change_details={
                    "notes": request.notes,
                    "timestamp": datetime.utcnow().isoformat()
                },
                compliance_relevant=True
            )
            db.add(audit)

            result_msg = "Change confirmed and moved to development queue"
        else:
            change.status = "Rejected"
            change.confirmed_by = request.analyst_name
            change.confirmed_date = datetime.utcnow()

            # Create audit log
            audit = AuditLog(
                org_id=None,
                entity_type="RegulatoryChange",
                entity_id=change.change_id,
                action="REJECTED",
                changed_by=request.analyst_name,
                change_details={
                    "reason": request.notes or "False alarm",
                    "timestamp": datetime.utcnow().isoformat()
                },
                compliance_relevant=False
            )
            db.add(audit)

            result_msg = "Change marked as false alarm"

        db.commit()

        return {
            "change_id": str(change.change_id),
            "new_status": change.status,
            "analyst": request.analyst_name,
            "confirmed_at": change.confirmed_date.isoformat(),
            "message": result_msg
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/changes/{change_id}/approve-release")
async def approve_release(
    change_id: str,
    request: ReleaseApprovalRequest,
    db: Session = Depends(get_db)
):
    """
    Quality/Release manager approves change for customer release
    Moves from "Ready" → "Released"
    """
    try:
        change = db.query(RegulatoryChange).filter_by(
            change_id=change_id
        ).first()

        if not change:
            raise HTTPException(status_code=404, detail="Change not found")

        if change.status != "Ready":
            raise HTTPException(
                status_code=400,
                detail=f"Can only release changes in 'Ready' status, current: {change.status}"
            )

        if request.approved:
            change.status = "Released"
            msg = "Change released to all customers"
        else:
            change.status = "In Development"  # Send back for more work
            msg = "Change returned to development"

        # Audit log
        audit = AuditLog(
            org_id=None,
            entity_type="RegulatoryChange",
            entity_id=change.change_id,
            action="RELEASE_DECISION",
            changed_by=request.approver_name,
            change_details={
                "approved": request.approved,
                "notes": request.notes,
                "timestamp": datetime.utcnow().isoformat()
            },
            compliance_relevant=True
        )
        db.add(audit)
        db.commit()

        return {
            "change_id": str(change.change_id),
            "new_status": change.status,
            "approver": request.approver_name,
            "approved_at": datetime.utcnow().isoformat(),
            "message": msg
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/{change_id}/audit-trail")
async def get_audit_trail(
    change_id: str,
    db: Session = Depends(get_db)
):
    """
    Get complete audit trail for a change
    Shows all confirmations, approvals, and state changes
    """
    try:
        # Get change
        change = db.query(RegulatoryChange).filter_by(
            change_id=change_id
        ).first()

        if not change:
            raise HTTPException(status_code=404, detail="Change not found")

        # Get audit logs
        audits = db.query(AuditLog).filter(
            AuditLog.entity_id == change.change_id
        ).order_by(AuditLog.timestamp).all()

        return {
            "change_id": str(change.change_id),
            "framework": change.framework.framework_name if change.framework else "Unknown",
            "current_status": change.status,
            "detected_at": change.detected_date.isoformat(),
            "audit_trail": [
                {
                    "action": audit.action,
                    "by": audit.changed_by,
                    "at": audit.timestamp.isoformat(),
                    "details": audit.change_details
                }
                for audit in audits
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
