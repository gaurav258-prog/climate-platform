"""
Regulatory Change Detection Engine
Monitors regulatory sources and identifies changes
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from core.db.models_regulatory_complete import (
    RegulatoryChange, RegulatoryFramework, RegulationVersion
)

logger = logging.getLogger(__name__)


class RegulatoryChangeDetector:
    """
    Main change detection engine for regulatory compliance

    Responsibilities:
    1. Monitor regulatory sources (web scrapers, news feeds, APIs)
    2. Detect document changes (diff analysis)
    3. Classify changes (data model, processing logic, output format)
    4. Estimate development effort
    5. Calculate customer deadlines
    6. Notify stakeholders
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def detect_changes(self, framework_id: str) -> List[Dict]:
        """
        Main detection loop for a regulatory framework

        Returns list of detected changes with:
        - old_version: previous version number
        - new_version: new version number
        - change_source: where detected (EUR-Lex, SEC.gov, etc.)
        - affected_areas: data model, processing, output
        - estimated_effort: dev hours
        - customer_deadline: when to release to customers
        """
        changes = []

        try:
            framework = self.db.query(RegulatoryFramework).filter_by(
                framework_id=framework_id
            ).first()

            if not framework:
                self.logger.warning(f"Framework {framework_id} not found")
                return changes

            self.logger.info(f"Detecting changes for {framework.framework_name}")

            # Step 1: Fetch latest documents from regulatory sources
            latest_docs = self._fetch_from_sources(framework)

            # Step 2: Compare with stored versions
            for source_name, doc in latest_docs.items():
                change = self._compare_versions(framework, source_name, doc)
                if change:
                    changes.append(change)

            return changes

        except Exception as e:
            self.logger.error(f"Change detection failed: {e}", exc_info=True)
            return []

    def _fetch_from_sources(self, framework) -> Dict:
        """
        Fetch latest documents from regulatory sources

        Sources per framework:
        - TCFD: TCFD website, SEC filings
        - EU Taxonomy: EUR-Lex, EFRAG, EU Commission
        - SEC: SEC.gov, Federal Register
        - Basel III: BIS, national banking regulators
        - EBA/ECB: EUR-Lex, EBA website, ECB website
        - FCA: FCA handbook, regulatory notices
        """
        sources = {
            "TCFD": {"url": "https://www.tcfdhub.org", "type": "website"},
            "EU Taxonomy": {"url": "https://eur-lex.europa.eu", "type": "official"},
            "SEC": {"url": "https://www.sec.gov/cgi-bin", "type": "official"},
            "EBA/ECB": {"url": "https://eur-lex.europa.eu", "type": "official"},
            "FCA": {"url": "https://www.fca.org.uk/news", "type": "news"},
            "Basel III": {"url": "https://www.bis.org", "type": "official"},
        }

        docs = {}
        for source_name, source_config in sources.items():
            try:
                # TODO: Implement actual scrapers in ./scrapers/
                # For now, return mock data
                docs[source_name] = self._get_mock_document(framework.framework_name)
            except Exception as e:
                self.logger.error(f"Failed to fetch from {source_name}: {e}")

        return docs

    def _compare_versions(self, framework, source_name: str, new_doc: str) -> Optional[Dict]:
        """
        Compare new document with latest stored version
        Returns change details if differences found
        """
        # Get current version
        current_version = self.db.query(RegulationVersion).filter_by(
            framework_id=framework.framework_id,
            is_current=True
        ).first()

        if not current_version:
            self.logger.warning(f"No current version for {framework.framework_name}")
            return None

        # TODO: Implement document diff analysis in ./analysis/document_analyzer.py
        # For now, return None (no changes detected)

        return None

    def classify_change(self, change: Dict) -> Dict:
        """
        Classify change impact:
        - Data model change: affects bank_assets, emissions, etc.
        - Processing logic change: affects calculation engine
        - Output format change: affects reporting structure
        - New module: entirely new reporting requirement
        """
        classification = {
            "affects_data_model": False,
            "affects_processing": False,
            "affects_output": False,
            "is_new_module": False,
            "effort_hours": 0
        }

        # TODO: Implement classification logic
        # This will analyze what parts of the system change

        return classification

    def estimate_effort(self, change: Dict) -> int:
        """
        Estimate development effort in hours

        Based on:
        - Complexity of change
        - Number of affected modules
        - Testing requirements
        - Documentation needs
        """
        base_hours = 8  # Minimum analysis + planning

        if change.get("affects_data_model"):
            base_hours += 16  # DB migration + ORM model update

        if change.get("affects_processing"):
            base_hours += 24  # Processing logic update + testing

        if change.get("affects_output"):
            base_hours += 12  # Output format change + validation

        if change.get("is_new_module"):
            base_hours += 40  # Full new module development

        return base_hours

    def calculate_customer_deadline(
        self,
        regulatory_deadline: datetime,
        dev_effort_hours: int
    ) -> datetime:
        """
        Calculate when to release to customers

        Logic:
        1. Assume 4-6 weeks minimum for customer implementation
        2. Add 7 days buffer for customer testing
        3. If deadline too close (< 4 weeks), release immediately after testing
        """
        release_buffer = timedelta(days=7)
        min_customer_time = timedelta(weeks=4)

        target_release = regulatory_deadline - release_buffer

        # If not enough time, release immediately after dev+test
        dev_days = dev_effort_hours / 8  # 8 hour day
        test_days = dev_days * 0.5  # 50% of dev time for testing

        dev_complete = datetime.now() + timedelta(days=dev_days + test_days)

        if target_release < dev_complete:
            # Not enough customer time, release immediately after testing
            return dev_complete

        return target_release

    def create_change_record(
        self,
        framework_id: str,
        change_data: Dict
    ) -> RegulatoryChange:
        """
        Create change record in database
        """
        change = RegulatoryChange(
            framework_id=framework_id,
            old_version=change_data.get("old_version"),
            new_version=change_data.get("new_version"),
            change_source=change_data.get("source"),
            detected_date=datetime.utcnow(),
            status="Detected",
            change_type="change",  # or "module"
            is_new_module=change_data.get("is_new_module", False),
            affected_tables=change_data.get("affected_tables"),
            affected_processing_modules=change_data.get("affected_modules"),
            affected_outputs=change_data.get("affected_outputs"),
            estimated_dev_hours=change_data.get("dev_hours"),
            estimated_test_hours=int(change_data.get("dev_hours", 0) * 0.5),
            estimated_total_hours=int(change_data.get("dev_hours", 0) * 1.5),
            customer_deadline=change_data.get("customer_deadline"),
        )

        self.db.add(change)
        self.db.commit()

        return change

    def _get_mock_document(self, framework_name: str) -> str:
        """Mock document for testing - remove once real scrapers implemented"""
        return f"Mock document for {framework_name}"


# Daily monitoring job
async def run_daily_monitoring(db: Session):
    """
    Run change detection for all frameworks
    Scheduled to run daily at 02:00 UTC
    """
    logger.info("Starting daily regulatory monitoring")

    detector = RegulatoryChangeDetector(db)
    frameworks = db.query(RegulatoryFramework).all()

    total_changes = 0
    for framework in frameworks:
        changes = detector.detect_changes(framework.framework_id)
        total_changes += len(changes)

        for change in changes:
            detector.create_change_record(framework.framework_id, change)

    logger.info(f"Daily monitoring complete: {total_changes} changes detected")
