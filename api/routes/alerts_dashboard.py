"""
Alert Dashboard API Routes
Real-time dashboard endpoints for viewing and managing alerts
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from core.db.config import get_db
from core.db.models_regulatory_complete import (
    RegulatoryAlert, DashboardNotification, Organization, RegulatoryFramework
)
from services.intelligence.benchmarking import CompetitiveBenchmarking
from services.notifications.notification_service import NotificationService

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts-dashboard"])


# ============================================================================
# SCHEMAS
# ============================================================================

class AlertSummary(BaseModel):
    alert_id: str
    framework_name: str
    affected_assets: int
    portfolio_value_affected_eur: float
    dev_hours: int
    deadline: str
    urgency_level: str
    alert_status: str
    created_at: str


class AlertDetail(BaseModel):
    alert_id: str
    org_name: str
    framework_name: str
    old_version: str
    new_version: str
    detected_date: str
    affected_assets: int
    total_assets: int
    portfolio_value_affected_eur: float
    total_portfolio_value_eur: float
    affected_tables: Optional[List[str]]
    affected_modules: Optional[List[str]]
    estimated_dev_hours: int
    estimated_test_hours: int
    deadline: str
    urgency_level: str
    peer_count_affected: int
    peer_avg_implementation_weeks: int
    alert_status: str
    action_url: str


class PeerBenchmark(BaseModel):
    peer_count: int
    peer_adoption_rate_pct: int
    avg_implementation_weeks: int
    status_breakdown: dict
    your_speed_percentile: int
    speed_assessment: str


class DashboardSummary(BaseModel):
    total_alerts: int
    critical_alerts: int
    high_priority_alerts: int
    new_alerts: int
    overdue_alerts: int
    next_deadline: Optional[str]
    recent_alerts: List[AlertSummary]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary(
    org_id: str = Query(..., description="Organization ID"),
    db: Session = Depends(get_db)
):
    """
    Get dashboard summary for organization
    Shows alert counts, critical items, deadlines
    """
    try:
        # Get org
        org = db.query(Organization).filter_by(org_id=org_id).first()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

        # Get all alerts for org
        alerts = db.query(RegulatoryAlert).filter_by(org_id=org_id).all()

        # Count by urgency
        critical = len([a for a in alerts if a.urgency_level == 'critical'])
        high = len([a for a in alerts if a.urgency_level == 'high'])
        new = len([a for a in alerts if a.alert_status == 'new'])

        # Check for overdue
        overdue = len([
            a for a in alerts
            if a.org_implementation_deadline and a.org_implementation_deadline < datetime.now().date()
        ])

        # Get next deadline
        future_alerts = [
            a for a in alerts
            if a.org_implementation_deadline and a.org_implementation_deadline >= datetime.now().date()
        ]
        next_deadline = min(
            (a.org_implementation_deadline.isoformat() for a in future_alerts),
            default=None
        )

        # Get recent alerts (last 5)
        recent = sorted(alerts, key=lambda a: a.created_at, reverse=True)[:5]

        recent_summaries = []
        for alert in recent:
            framework = db.query(RegulatoryFramework).filter_by(
                framework_id=alert.framework_id
            ).first()

            recent_summaries.append(AlertSummary(
                alert_id=str(alert.alert_id),
                framework_name=framework.framework_name if framework else "Unknown",
                affected_assets=alert.affected_asset_count,
                portfolio_value_affected_eur=float(alert.portfolio_value_affected_eur or 0),
                dev_hours=alert.estimated_dev_hours or 0,
                deadline=alert.org_implementation_deadline.isoformat() if alert.org_implementation_deadline else "N/A",
                urgency_level=alert.urgency_level or "medium",
                alert_status=alert.alert_status,
                created_at=alert.created_at.isoformat()
            ))

        return DashboardSummary(
            total_alerts=len(alerts),
            critical_alerts=critical,
            high_priority_alerts=high,
            new_alerts=new,
            overdue_alerts=overdue,
            next_deadline=next_deadline,
            recent_alerts=recent_summaries
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/alerts", response_model=List[AlertSummary])
async def list_alerts(
    org_id: str = Query(..., description="Organization ID"),
    status: Optional[str] = Query(None, description="Filter by status: new, acknowledged, in_progress"),
    urgency: Optional[str] = Query(None, description="Filter by urgency: critical, high, medium, low"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    List alerts for organization
    Supports filtering by status and urgency
    """
    try:
        query = db.query(RegulatoryAlert).filter_by(org_id=org_id)

        if status:
            query = query.filter_by(alert_status=status)

        if urgency:
            query = query.filter_by(urgency_level=urgency)

        # Sort by deadline, then urgency
        alerts = query.order_by(
            RegulatoryAlert.org_implementation_deadline.asc(),
            RegulatoryAlert.urgency_level.desc()
        ).offset(skip).limit(limit).all()

        summaries = []
        for alert in alerts:
            framework = db.query(RegulatoryFramework).filter_by(
                framework_id=alert.framework_id
            ).first()

            summaries.append(AlertSummary(
                alert_id=str(alert.alert_id),
                framework_name=framework.framework_name if framework else "Unknown",
                affected_assets=alert.affected_asset_count,
                portfolio_value_affected_eur=float(alert.portfolio_value_affected_eur or 0),
                dev_hours=alert.estimated_dev_hours or 0,
                deadline=alert.org_implementation_deadline.isoformat() if alert.org_implementation_deadline else "N/A",
                urgency_level=alert.urgency_level or "medium",
                alert_status=alert.alert_status,
                created_at=alert.created_at.isoformat()
            ))

        return summaries

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/alerts/{alert_id}", response_model=AlertDetail)
async def get_alert_detail(
    alert_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: Session = Depends(get_db)
):
    """
    Get full alert details
    Includes impact analysis, peer benchmarks, recommended actions
    """
    try:
        alert = db.query(RegulatoryAlert).filter_by(
            alert_id=alert_id,
            org_id=org_id
        ).first()

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        org = db.query(Organization).filter_by(org_id=org_id).first()
        framework = db.query(RegulatoryFramework).filter_by(framework_id=alert.framework_id).first()

        # Mark as viewed
        alert.dashboard_viewed_at = datetime.utcnow()
        if alert.alert_status == 'new':
            alert.alert_status = 'viewed'
        db.commit()

        return AlertDetail(
            alert_id=str(alert.alert_id),
            org_name=org.name if org else "Unknown",
            framework_name=framework.framework_name if framework else "Unknown",
            old_version="",  # From change record
            new_version="",  # From change record
            detected_date=alert.created_at.isoformat(),
            affected_assets=alert.affected_asset_count,
            total_assets=alert.total_assets or 0,
            portfolio_value_affected_eur=float(alert.portfolio_value_affected_eur or 0),
            total_portfolio_value_eur=float(alert.total_portfolio_value_eur or 0),
            affected_tables=alert.affected_tables,
            affected_modules=alert.affected_modules,
            estimated_dev_hours=alert.estimated_dev_hours or 0,
            estimated_test_hours=alert.estimated_test_hours or 0,
            deadline=alert.org_implementation_deadline.isoformat() if alert.org_implementation_deadline else "N/A",
            urgency_level=alert.urgency_level or "medium",
            peer_count_affected=alert.peer_count_affected or 0,
            peer_avg_implementation_weeks=alert.peer_response_avg_weeks or 0,
            alert_status=alert.alert_status,
            action_url=f"/api/v1/alerts/dashboard/alerts/{alert_id}/create-task"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/alerts/{alert_id}/peer-context", response_model=PeerBenchmark)
async def get_peer_context(
    alert_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: Session = Depends(get_db)
):
    """
    Get competitive peer benchmarking for this alert
    Shows how other banks are responding
    """
    try:
        alert = db.query(RegulatoryAlert).filter_by(
            alert_id=alert_id,
            org_id=org_id
        ).first()

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        # Get benchmarking data
        benchmarking = CompetitiveBenchmarking(db)
        peer_status = benchmarking.get_peer_status(org_id, alert.framework_id)
        adoption = benchmarking.get_framework_adoption(alert.framework_id)
        speed = benchmarking.get_speed_comparison(org_id)

        return PeerBenchmark(
            peer_count=peer_status.get('peer_count', 0),
            peer_adoption_rate_pct=adoption.get('adoption_rate_pct', 0),
            avg_implementation_weeks=peer_status.get('avg_implementation_weeks', 0),
            status_breakdown=adoption.get('status_breakdown', {}),
            your_speed_percentile=speed.get('speed_percentile', 0),
            speed_assessment=speed.get('assessment', 'unknown')
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: Session = Depends(get_db)
):
    """
    Acknowledge alert (move from 'new' to 'acknowledged')
    """
    try:
        alert = db.query(RegulatoryAlert).filter_by(
            alert_id=alert_id,
            org_id=org_id
        ).first()

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        alert.alert_status = 'acknowledged'
        alert.acknowledged_at = datetime.utcnow()
        db.commit()

        return {
            'alert_id': str(alert.alert_id),
            'status': 'acknowledged',
            'acknowledged_at': alert.acknowledged_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard/alerts/{alert_id}/create-task")
async def create_task_from_alert(
    alert_id: str,
    org_id: str = Query(..., description="Organization ID"),
    system: str = Query("jira", description="Task system: jira or linear"),
    db: Session = Depends(get_db)
):
    """
    Create task in JIRA or Linear from alert
    Prepopulated with alert details
    """
    try:
        alert = db.query(RegulatoryAlert).filter_by(
            alert_id=alert_id,
            org_id=org_id
        ).first()

        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")

        # TODO: Integrate with JIRA/Linear APIs
        # For now, return placeholder

        return {
            'status': 'placeholder',
            'message': 'JIRA/Linear integration coming in Phase 2 Week 4',
            'alert_id': str(alert.alert_id),
            'system': system
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/notifications")
async def get_dashboard_notifications(
    org_id: str = Query(..., description="Organization ID"),
    unread_only: bool = Query(False, description="Only unread notifications"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get dashboard notifications for organization
    These are in-app alerts (separate from email)
    """
    try:
        query = db.query(DashboardNotification).filter_by(org_id=org_id)

        if unread_only:
            query = query.filter_by(is_read=False)

        notifications = query.order_by(
            DashboardNotification.created_at.desc()
        ).limit(limit).all()

        return [
            {
                'notification_id': str(n.notification_id),
                'title': n.title,
                'message': n.message,
                'type': n.notification_type,
                'severity': n.severity,
                'is_read': n.is_read,
                'action_url': n.action_url,
                'created_at': n.created_at.isoformat()
            }
            for n in notifications
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dashboard/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    org_id: str = Query(..., description="Organization ID"),
    db: Session = Depends(get_db)
):
    """
    Mark notification as read
    """
    try:
        notification = db.query(DashboardNotification).filter_by(
            notification_id=notification_id,
            org_id=org_id
        ).first()

        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")

        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.commit()

        return {
            'notification_id': str(notification.notification_id),
            'is_read': True,
            'read_at': notification.read_at.isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
