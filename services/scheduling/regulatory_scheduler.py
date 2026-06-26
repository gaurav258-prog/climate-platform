"""
Regulatory Monitoring Scheduler
Runs daily at 02:00 UTC to detect regulatory changes for all customers
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from core.db.config import SessionLocal
from core.db.models_regulatory_complete import (
    Organization, RegulatoryFramework, RegulatoryChange, RegulatoryAlert
)
from services.regulatory_monitoring import RegulatoryChangeDetector
from services.regulatory_monitoring.analysis import ImpactAnalyzer
from services.intelligence.benchmarking import CompetitiveBenchmarking

logger = logging.getLogger(__name__)


class RegulatoryScheduler:
    """
    Daily regulatory monitoring scheduler

    Runs 02:00 UTC each day:
    1. For each organization
    2. For each regulatory framework they track
    3. Detect changes (CRCS)
    4. Analyze impact (specific to their portfolio)
    5. Queue notifications
    6. Create dashboard alerts
    """

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
        self.detector = RegulatoryChangeDetector(self.db)
        self.analyzer = ImpactAnalyzer()
        self.benchmarking = CompetitiveBenchmarking(self.db)

    def run_daily_scan(self) -> Dict:
        """
        Main daily scan entry point
        Returns: summary of detection results
        """
        logger.info("=" * 80)
        logger.info("STARTING DAILY REGULATORY MONITORING")
        logger.info(f"Scan time: {datetime.utcnow().isoformat()}")
        logger.info("=" * 80)

        try:
            # Get all organizations
            organizations = self.db.query(Organization).all()
            logger.info(f"Found {len(organizations)} organizations to scan")

            total_alerts = 0
            total_changes = 0

            for org in organizations:
                try:
                    alerts = self._scan_org(org)
                    total_alerts += len(alerts)
                    total_changes += sum(1 for a in alerts if not a.get('is_duplicate'))
                except Exception as e:
                    logger.error(f"Error scanning org {org.name}: {e}", exc_info=True)
                    continue

            # Log summary
            logger.info("=" * 80)
            logger.info(f"DAILY SCAN COMPLETE")
            logger.info(f"  Organizations scanned: {len(organizations)}")
            logger.info(f"  Total alerts generated: {total_alerts}")
            logger.info(f"  New changes detected: {total_changes}")
            logger.info("=" * 80)

            return {
                "status": "success",
                "scan_time": datetime.utcnow().isoformat(),
                "orgs_scanned": len(organizations),
                "alerts_generated": total_alerts,
                "new_changes": total_changes
            }

        except Exception as e:
            logger.error(f"Daily scan failed: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "scan_time": datetime.utcnow().isoformat()
            }

    def _scan_org(self, org: Organization) -> List[Dict]:
        """
        Scan one organization for all frameworks
        """
        logger.info(f"\n→ Scanning: {org.name}")

        alerts = []

        try:
            # Get frameworks this org tracks
            frameworks = self.db.query(RegulatoryFramework).all()
            logger.info(f"  Checking {len(frameworks)} frameworks")

            for framework in frameworks:
                try:
                    alert = self._detect_and_analyze(org, framework)
                    if alert:
                        alerts.append(alert)
                        logger.info(
                            f"    ✓ {framework.framework_name}: "
                            f"{alert.get('change_type')} detected "
                            f"({alert.get('affected_assets')} assets affected)"
                        )
                except Exception as e:
                    logger.error(
                        f"  Error scanning {framework.framework_name} for {org.name}: {e}"
                    )
                    continue

        except Exception as e:
            logger.error(f"Error scanning org {org.name}: {e}", exc_info=True)

        return alerts

    def _detect_and_analyze(
        self,
        org: Organization,
        framework: RegulatoryFramework
    ) -> Optional[Dict]:
        """
        Detect changes for one org + one framework, analyze impact

        Returns: alert_data if changes detected, None if no changes
        """

        # Step 1: Detect changes (using Phase 1 CRCS)
        changes = self.detector.detect_changes(framework.framework_id)

        if not changes:
            return None

        # For each detected change, analyze impact specific to this org
        for change in changes:
            try:
                # Step 2: Analyze impact specific to this org
                impact = self._calculate_org_impact(org, change)

                # Step 3: Get peer benchmarks
                peer_data = self.benchmarking.get_peer_status(
                    org.org_id,
                    framework.framework_id
                )

                # Step 4: Check if alert already exists (deduplication)
                existing_alert = self.db.query(RegulatoryAlert).filter_by(
                    org_id=org.org_id,
                    change_id=change.get('change_id')
                ).first()

                if existing_alert:
                    logger.debug(f"    (duplicate alert, skipping)")
                    return {
                        'is_duplicate': True,
                        'alert_id': str(existing_alert.alert_id)
                    }

                # Step 5: Create alert record in database
                alert_id = self._create_alert(org, framework, change, impact, peer_data)

                # Step 6: Queue notification (don't send yet, let worker process)
                self._queue_notification(org, alert_id, change, impact)

                return {
                    'is_duplicate': False,
                    'alert_id': str(alert_id),
                    'change_type': change.get('change_type'),
                    'affected_assets': impact.get('affected_asset_count'),
                    'effort_hours': impact.get('estimated_dev_hours'),
                    'deadline': change.get('customer_deadline')
                }

            except Exception as e:
                logger.error(f"Error analyzing change for {org.name}: {e}")
                return None

        return None

    def _calculate_org_impact(self, org: Organization, change: Dict) -> Dict:
        """
        Calculate impact of regulatory change specific to org's portfolio

        This is what makes us different from competitors:
        We tell banks HOW MANY of THEIR assets are affected, not generic counts
        """

        logger.debug(f"  Calculating impact for {org.name}...")

        try:
            from core.db.models_regulatory_complete import BankAsset

            # Get this org's assets
            assets = self.db.query(BankAsset).filter_by(org_id=org.org_id).all()

            if not assets:
                return {
                    'affected_asset_count': 0,
                    'portfolio_value_affected_eur': 0,
                    'estimated_dev_hours': change.get('estimated_dev_hours', 40),
                    'affected_sectors': [],
                    'tables_affected': change.get('affected_tables', [])
                }

            # Analyze impact using ImpactAnalyzer
            impact_analysis = self.analyzer.analyze_impact(
                f"{change.get('old_version')} → {change.get('new_version')}: "
                f"{change.get('change_source')}"
            )

            timeline = self.analyzer.estimate_timeline(impact_analysis)

            # Calculate which of ORG's assets are affected
            # Simple heuristic: changes to sector data affect assets in that sector
            affected_assets = [
                a for a in assets
                if self._asset_affected_by_change(a, change)
            ]

            total_portfolio_value = sum(
                float(a.asset_value_eur or 0) for a in assets
            )
            affected_portfolio_value = sum(
                float(a.asset_value_eur or 0) for a in affected_assets
            )

            return {
                'affected_asset_count': len(affected_assets),
                'total_assets': len(assets),
                'portfolio_value_affected_eur': affected_portfolio_value,
                'total_portfolio_value_eur': total_portfolio_value,
                'affected_sectors': list(set(a.sector for a in affected_assets if a.sector)),
                'estimated_dev_hours': impact_analysis.get('estimated_effort_hours'),
                'estimated_test_hours': int(impact_analysis.get('estimated_effort_hours', 40) * 0.5),
                'tables_affected': impact_analysis.get('affected_tables'),
                'modules_affected': impact_analysis.get('affected_modules'),
                'outputs_affected': impact_analysis.get('affected_outputs'),
                'is_module': self.analyzer.determine_if_module(impact_analysis),
                'timeline_weeks': timeline.get('weeks')
            }

        except Exception as e:
            logger.error(f"Error calculating impact: {e}")
            return {
                'affected_asset_count': 0,
                'portfolio_value_affected_eur': 0,
                'estimated_dev_hours': 40
            }

    def _asset_affected_by_change(self, asset, change: Dict) -> bool:
        """
        Simple heuristic: is this asset affected by the regulatory change?

        Examples:
        - If change is about "EU Taxonomy", affected = asset in EU
        - If change is about "TCFD", affected = asset in TCFD-reporting region
        - If change is about sector-specific rules, affected = that sector
        """

        change_source = change.get('change_source', '').lower()
        framework = change.get('framework_id')

        # Simple geographic heuristic
        if 'eu' in change_source and asset.country not in ['DE', 'FR', 'NL', 'IT', 'ES', 'AT', 'BE', 'SE', 'DK', 'FI', 'IE', 'LU', 'PL', 'PT', 'CZ', 'GR', 'HU', 'RO', 'SK', 'SI', 'BG', 'HR', 'LT', 'LV', 'EE', 'MT', 'CY']:
            return False

        if 'sec' in change_source and asset.country != 'US':
            return False

        if 'fca' in change_source and asset.country != 'GB':
            return False

        # If sector-specific, check asset sector
        if change.get('affected_tables'):
            if 'bank_assets' in str(change.get('affected_tables')):
                return True

        # Default: assume affected if not specifically excluded
        return True

    def _create_alert(
        self,
        org: Organization,
        framework: RegulatoryFramework,
        change: Dict,
        impact: Dict,
        peer_data: Dict
    ) -> str:
        """
        Create RegulatoryAlert record in database
        """

        try:
            from uuid import uuid4

            alert = RegulatoryAlert(
                alert_id=uuid4(),
                org_id=org.org_id,
                change_id=change.get('change_id'),
                framework_id=framework.framework_id,
                affected_asset_count=impact.get('affected_asset_count', 0),
                total_assets=impact.get('total_assets', 0),
                portfolio_value_affected_eur=impact.get('portfolio_value_affected_eur', 0),
                total_portfolio_value_eur=impact.get('total_portfolio_value_eur', 0),
                affected_tables=impact.get('tables_affected'),
                estimated_dev_hours=impact.get('estimated_dev_hours'),
                estimated_test_hours=impact.get('estimated_test_hours'),
                regulatory_deadline=change.get('customer_deadline'),
                org_implementation_deadline=change.get('customer_deadline'),
                urgency_level=self._calculate_urgency(impact, change),
                alert_status='new',
                peer_count_affected=peer_data.get('peer_count', 0),
                peer_response_avg_weeks=peer_data.get('avg_implementation_weeks'),
                created_at=datetime.utcnow()
            )

            self.db.add(alert)
            self.db.commit()

            logger.debug(f"Created alert {alert.alert_id}")
            return str(alert.alert_id)

        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            self.db.rollback()
            raise

    def _calculate_urgency(self, impact: Dict, change: Dict) -> str:
        """
        Calculate urgency level: low, medium, high, critical

        Based on:
        - Days until deadline
        - Portfolio impact %
        - Development effort
        """

        try:
            deadline = change.get('customer_deadline')
            if not deadline:
                return 'medium'

            days_until = (deadline - datetime.now().date()).days

            portfolio_impact_pct = (
                impact.get('portfolio_value_affected_eur', 0) /
                max(impact.get('total_portfolio_value_eur', 1), 1)
            ) * 100

            dev_hours = impact.get('estimated_dev_hours', 0)

            if days_until < 30 and portfolio_impact_pct > 25:
                return 'critical'
            elif days_until < 60 or portfolio_impact_pct > 50:
                return 'high'
            elif dev_hours > 80:
                return 'high'
            else:
                return 'medium'

        except Exception as e:
            logger.error(f"Error calculating urgency: {e}")
            return 'medium'

    def _queue_notification(
        self,
        org: Organization,
        alert_id: str,
        change: Dict,
        impact: Dict
    ):
        """
        Queue notification to be sent (email, dashboard, etc)
        Actual sending handled by notification worker
        """

        logger.debug(f"Queuing notification for {org.name}, alert {alert_id}")

        # This will be implemented in Phase 2, Week 3
        # For now, just log
        pass


async def run_daily_scan():
    """
    Entry point for scheduled job (APScheduler, Celery, etc)
    """
    scheduler = RegulatoryScheduler()
    result = scheduler.run_daily_scan()
    return result
