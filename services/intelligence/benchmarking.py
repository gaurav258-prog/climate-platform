"""
Competitive Benchmarking Service
Analyzes what peer banks are doing with regulatory changes
"""

import logging
from typing import Dict

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class CompetitiveBenchmarking:
    """
    Competitive intelligence: Help banks understand peer responses

    Questions answered:
    - How many banks are affected by this framework change?
    - What's the average implementation timeline?
    - Are competitors fast movers or slow movers?
    """

    def __init__(self, db: Session):
        self.db = db

    def get_peer_status(self, org_id: str, framework_id: str) -> Dict:
        """
        Get peer bank status for a framework
        Returns: benchmarking data
        """
        logger.info(f"Getting peer status for org {org_id}, framework {framework_id}")

        try:
            from core.db.models_regulatory_complete import (
                Organization,
                RegulatoryAlert,
            )

            # Get this org
            org = self.db.query(Organization).filter_by(org_id=org_id).first()
            if not org:
                return {'peer_count': 0, 'avg_implementation_weeks': 0}

            # Find peers (same sector/region, similar size)
            peers = self.db.query(Organization).filter(
                Organization.org_id != org_id,
                Organization.country == org.country,  # Same region for now
                Organization.type == org.type  # Same type (bank, insurer, etc)
            ).all()

            if not peers:
                return {
                    'peer_count': 0,
                    'avg_implementation_weeks': 0,
                    'peer_details': []
                }

            # For this framework, check peer status
            peer_details = []
            implementation_weeks = []

            for peer in peers:
                try:
                    # Check if peer has alerts for this framework
                    alerts = self.db.query(RegulatoryAlert).filter_by(
                        org_id=peer.org_id,
                        framework_id=framework_id
                    ).all()

                    if alerts:
                        for alert in alerts:
                            if alert.estimated_test_hours:
                                weeks = int((alert.estimated_dev_hours or 40) / (8 * 5))  # 8h/day, 5 days/week
                                implementation_weeks.append(weeks)

                                peer_details.append({
                                    'peer_name': peer.name,
                                    'framework_version': alert.framework_id,
                                    'estimated_weeks': weeks,
                                    'alert_status': alert.alert_status
                                })
                except Exception as e:
                    logger.debug(f"Error analyzing peer {peer.name}: {e}")
                    continue

            avg_weeks = int(sum(implementation_weeks) / len(implementation_weeks)) if implementation_weeks else 0

            return {
                'peer_count': len(peers),
                'peer_count_affected': len([p for p in peer_details if p]),
                'avg_implementation_weeks': avg_weeks,
                'peer_details': peer_details[:5]  # Top 5 peers
            }

        except Exception as e:
            logger.error(f"Error getting peer status: {e}")
            return {
                'peer_count': 0,
                'avg_implementation_weeks': 0,
                'error': str(e)
            }

    def get_framework_adoption(self, framework_id: str) -> Dict:
        """
        Get adoption status of a framework across all customers
        """
        logger.info(f"Getting framework adoption for {framework_id}")

        try:
            from core.db.models_regulatory_complete import Organization, RegulatoryAlert

            # Count orgs with alerts for this framework
            affected_orgs = self.db.query(Organization).join(
                RegulatoryAlert,
                Organization.org_id == RegulatoryAlert.org_id
            ).filter(
                RegulatoryAlert.framework_id == framework_id
            ).distinct().count()

            total_orgs = self.db.query(Organization).count()

            # Get alert status breakdown
            alerts = self.db.query(RegulatoryAlert).filter_by(
                framework_id=framework_id
            ).all()

            status_breakdown = {
                'new': len([a for a in alerts if a.alert_status == 'new']),
                'acknowledged': len([a for a in alerts if a.alert_status == 'acknowledged']),
                'in_progress': len([a for a in alerts if a.alert_status == 'in_progress']),
                'complete': len([a for a in alerts if a.alert_status == 'complete'])
            }

            return {
                'framework_id': str(framework_id),
                'total_customers': total_orgs,
                'affected_customers': affected_orgs,
                'adoption_rate_pct': int((affected_orgs / max(total_orgs, 1)) * 100),
                'status_breakdown': status_breakdown,
                'avg_implementation_priority': self._calculate_avg_urgency(framework_id)
            }

        except Exception as e:
            logger.error(f"Error getting framework adoption: {e}")
            return {'error': str(e)}

    def get_speed_comparison(self, org_id: str) -> Dict:
        """
        Is this bank a fast mover or slow mover vs peers?
        """
        logger.info(f"Calculating speed comparison for org {org_id}")

        try:
            from core.db.models_regulatory_complete import Organization, RegulatoryAlert

            org = self.db.query(Organization).filter_by(org_id=org_id).first()
            if not org:
                return {}

            # Get this org's alert acknowledgement time
            org_alerts = self.db.query(RegulatoryAlert).filter_by(org_id=org_id).all()

            org_ack_times = []
            for alert in org_alerts:
                if alert.created_at and alert.dashboard_viewed_at:
                    ack_time = (alert.dashboard_viewed_at - alert.created_at).days
                    org_ack_times.append(ack_time)

            org_avg_ack_time = int(sum(org_ack_times) / len(org_ack_times)) if org_ack_times else None

            # Compare to peers
            peers = self.db.query(Organization).filter(
                Organization.org_id != org_id,
                Organization.country == org.country,
                Organization.type == org.type
            ).all()

            peer_ack_times = []
            for peer in peers:
                peer_alerts = self.db.query(RegulatoryAlert).filter_by(org_id=peer.org_id).all()
                for alert in peer_alerts:
                    if alert.created_at and alert.dashboard_viewed_at:
                        ack_time = (alert.dashboard_viewed_at - alert.created_at).days
                        peer_ack_times.append(ack_time)

            peer_avg_ack_time = int(sum(peer_ack_times) / len(peer_ack_times)) if peer_ack_times else None

            if org_avg_ack_time and peer_avg_ack_time:
                speed_percentile = int(
                    (len([t for t in peer_ack_times if t > org_avg_ack_time]) / len(peer_ack_times)) * 100
                )
            else:
                speed_percentile = None

            return {
                'org_avg_acknowledgement_days': org_avg_ack_time,
                'peer_avg_acknowledgement_days': peer_avg_ack_time,
                'speed_percentile': speed_percentile,  # Higher = faster
                'assessment': self._speed_assessment(speed_percentile)
            }

        except Exception as e:
            logger.error(f"Error calculating speed comparison: {e}")
            return {}

    def _calculate_avg_urgency(self, framework_id: str) -> str:
        """Calculate average urgency across all customers for a framework"""
        try:
            from core.db.models_regulatory_complete import RegulatoryAlert

            alerts = self.db.query(RegulatoryAlert).filter_by(
                framework_id=framework_id
            ).all()

            if not alerts:
                return 'medium'

            urgency_scores = {
                'critical': 4,
                'high': 3,
                'medium': 2,
                'low': 1
            }

            avg_score = sum(
                urgency_scores.get(a.urgency_level, 2) for a in alerts
            ) / len(alerts)

            if avg_score > 3.5:
                return 'critical'
            elif avg_score > 2.5:
                return 'high'
            else:
                return 'medium'

        except Exception as e:
            logger.error(f"Error calculating avg urgency: {e}")
            return 'medium'

    def _speed_assessment(self, percentile: int) -> str:
        """Provide qualitative assessment of speed"""
        if percentile is None:
            return 'unknown'
        elif percentile >= 75:
            return 'fast mover'
        elif percentile >= 50:
            return 'average'
        elif percentile >= 25:
            return 'slow'
        else:
            return 'very slow'
