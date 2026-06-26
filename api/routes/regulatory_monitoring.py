"""
API Routes for Regulatory Change Detection (CRCS)
Endpoints for:
- Trigger change detection
- View detected changes
- Manage change status
- Get impact analysis
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from core.db.config import get_db
from core.db.models_regulatory_complete import (
    RegulatoryChange, RegulatoryFramework, Organization
)
from services.regulatory_monitoring import RegulatoryChangeDetector
from services.regulatory_monitoring.analysis import (
    DocumentAnalyzer, ImpactAnalyzer
)
from services.regulatory_monitoring.scrapers import EurLexScraper

router = APIRouter(prefix="/api/v1/regulatory", tags=["regulatory-monitoring"])


# ============================================================================
# SCHEMAS
# ============================================================================

class ChangeDetectionRequest(BaseModel):
    framework_id: Optional[str] = None  # Detect for specific framework or all
    skip_cache: bool = False  # Force fresh detection


class ChangeResponse(BaseModel):
    change_id: str
    framework_name: str
    old_version: str
    new_version: str
    status: str
    detected_date: datetime
    customer_deadline: Optional[datetime]
    estimated_hours: Optional[int]
    is_new_module: bool


class ChangeImpactResponse(BaseModel):
    affected_tables: List[str]
    affected_modules: List[str]
    affected_outputs: List[str]
    estimated_effort_hours: int
    is_module: bool
    timeline_weeks: int


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/detect-changes", response_model=dict)
async def trigger_change_detection(
    request: ChangeDetectionRequest,
    db: Session = Depends(get_db)
):
    """
    Trigger regulatory change detection
    Scans all regulatory sources for updates

    Returns: number of changes detected
    """
    try:
        detector = RegulatoryChangeDetector(db)

        if request.framework_id:
            # Detect for specific framework
            changes = detector.detect_changes(request.framework_id)
            count = len(changes)
        else:
            # Detect for all frameworks
            frameworks = db.query(RegulatoryFramework).all()
            total_changes = 0

            for framework in frameworks:
                changes = detector.detect_changes(framework.framework_id)
                total_changes += len(changes)

            count = total_changes

        return {
            "status": "success",
            "changes_detected": count,
            "timestamp": datetime.utcnow().isoformat(),
            "next_scan": "Tomorrow at 02:00 UTC"  # Daily scan
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes", response_model=List[ChangeResponse])
async def get_detected_changes(
    framework_id: Optional[str] = None,
    status: Optional[str] = None,
    org_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get detected regulatory changes
    Filter by framework, status, or organization

    Status values:
    - Detected: Just discovered
    - Confirmed: Analyst confirmed it's real
    - In Development: Being implemented
    - Testing: QA phase
    - Ready: Ready to release
    - Released: Deployed to customers
    """
    try:
        query = db.query(RegulatoryChange)

        if framework_id:
            query = query.filter_by(framework_id=framework_id)

        if status:
            query = query.filter_by(status=status)

        changes = query.order_by(RegulatoryChange.detected_date.desc()).all()

        return [
            ChangeResponse(
                change_id=str(c.change_id),
                framework_name=c.framework.framework_name if c.framework else "Unknown",
                old_version=c.old_version or "",
                new_version=c.new_version or "",
                status=c.status,
                detected_date=c.detected_date,
                customer_deadline=c.customer_deadline,
                estimated_hours=c.estimated_total_hours,
                is_new_module=c.is_new_module or False
            )
            for c in changes
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/changes/{change_id}/impact", response_model=ChangeImpactResponse)
async def get_change_impact(
    change_id: str,
    db: Session = Depends(get_db)
):
    """
    Get impact analysis for a detected change
    Shows what components are affected and timeline
    """
    try:
        change = db.query(RegulatoryChange).filter_by(
            change_id=change_id
        ).first()

        if not change:
            raise HTTPException(status_code=404, detail="Change not found")

        # Use stored impact analysis if available
        if change.affected_tables:
            return ChangeImpactResponse(
                affected_tables=change.affected_tables or [],
                affected_modules=change.affected_processing_modules or [],
                affected_outputs=change.affected_outputs or [],
                estimated_effort_hours=change.estimated_total_hours or 0,
                is_module=change.is_new_module or False,
                timeline_weeks=int((change.estimated_total_hours or 0) / 40)
            )

        # Otherwise analyze from change description
        analyzer = ImpactAnalyzer()
        description = f"{change.old_version} to {change.new_version}: {change.change_source}"
        impact = analyzer.analyze_impact(description)
        timeline = analyzer.estimate_timeline(impact)

        return ChangeImpactResponse(
            affected_tables=impact["affected_tables"],
            affected_modules=impact["affected_modules"],
            affected_outputs=impact["affected_outputs"],
            estimated_effort_hours=impact["estimated_effort_hours"],
            is_module=analyzer.determine_if_module(impact),
            timeline_weeks=timeline["weeks"]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scrape-eur-lex", response_model=dict)
async def test_eur_lex_scraper():
    """
    Test EUR-Lex scraper (for development)
    Returns sample documents from EUR-Lex
    """
    try:
        scraper = EurLexScraper()

        # Test each scraper type
        results = {
            "taxonomy_updates": scraper.scrape_taxonomy_updates(),
            "csrd_updates": scraper.scrape_csrd_updates(),
            "eba_guidelines": scraper.scrape_eba_guidelines(),
            "recent_documents": scraper.scrape_recent_documents(days=7),
            "timestamp": datetime.utcnow().isoformat()
        }

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/changes/{change_id}/status", response_model=dict)
async def update_change_status(
    change_id: str,
    new_status: str,
    db: Session = Depends(get_db)
):
    """
    Update change status (for internal workflow)
    Valid statuses: Detected → Confirmed → In Development → Testing → Ready → Released
    """
    valid_statuses = [
        "Detected", "Confirmed", "In Development",
        "Testing", "Ready", "Released"
    ]

    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    try:
        change = db.query(RegulatoryChange).filter_by(
            change_id=change_id
        ).first()

        if not change:
            raise HTTPException(status_code=404, detail="Change not found")

        change.status = new_status
        change.status_updated_at = datetime.utcnow()
        db.commit()

        return {
            "change_id": str(change.change_id),
            "new_status": new_status,
            "updated_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
