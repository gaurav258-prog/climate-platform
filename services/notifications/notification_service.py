"""
Notification Service
Sends alerts via email, dashboard, and Slack
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Multi-channel notification delivery:
    - Email (SendGrid/SES)
    - Dashboard in-app alerts
    - Slack (optional)
    - SMS (future)
    """

    def __init__(self, db: Session, config: Dict = None):
        self.db = db
        self.config = config or {}
        self.email_provider = self._init_email_provider()

    def _init_email_provider(self):
        """Initialize email provider (SendGrid or AWS SES)"""
        provider = self.config.get('email_provider', 'sendgrid')

        if provider == 'sendgrid':
            try:
                import sendgrid  # noqa: F401  — availability probe; ImportError below disables email
                from sendgrid.helpers.mail import Mail  # noqa: F401
                return SendGridProvider(self.config.get('sendgrid_api_key'))
            except ImportError:
                logger.warning("SendGrid not installed, email disabled")
                return None

        elif provider == 'ses':
            try:
                import boto3  # noqa: F401  — availability probe; ImportError below disables email
                return SESProvider(
                    self.config.get('aws_access_key'),
                    self.config.get('aws_secret_key'),
                    self.config.get('aws_region', 'us-east-1')
                )
            except ImportError:
                logger.warning("boto3 not installed, SES disabled")
                return None

        return None

    def send_alert_notification(
        self,
        org_id: str,
        alert_id: str,
        channel: str = 'all'
    ) -> Dict:
        """
        Send alert via specified channel(s)
        channel: 'email', 'dashboard', 'slack', 'all'
        """
        logger.info(f"Sending alert {alert_id} to org {org_id} via {channel}")

        try:
            from core.db.models_regulatory_complete import Organization, RegulatoryAlert

            # Get alert details
            alert = self.db.query(RegulatoryAlert).filter_by(alert_id=alert_id).first()
            if not alert:
                return {'status': 'error', 'message': 'Alert not found'}

            org = self.db.query(Organization).filter_by(org_id=org_id).first()
            if not org:
                return {'status': 'error', 'message': 'Organization not found'}

            results = {}

            # Send via requested channels
            if channel in ['email', 'all']:
                results['email'] = self._send_email(org, alert)

            if channel in ['dashboard', 'all']:
                results['dashboard'] = self._create_dashboard_alert(org, alert)

            if channel in ['slack', 'all']:
                results['slack'] = self._send_slack(org, alert)

            # Update alert status
            alert.email_sent_at = datetime.utcnow()
            alert.alert_status = 'sent'
            self.db.commit()

            logger.info(f"Alert {alert_id} sent: {results}")
            return {
                'status': 'success',
                'alert_id': str(alert_id),
                'channels': results
            }

        except Exception as e:
            logger.error(f"Error sending notification: {e}", exc_info=True)
            self.db.rollback()
            return {
                'status': 'error',
                'message': str(e)
            }

    def _send_email(self, org, alert) -> Dict:
        """Send email notification to compliance team"""
        logger.info(f"Sending email for {org.name}")

        try:
            if not self.email_provider:
                logger.warning("Email provider not configured")
                return {'status': 'skipped', 'reason': 'provider_not_configured'}

            # Get org's compliance email recipients
            recipients = self._get_email_recipients(org)
            if not recipients:
                logger.warning(f"No email recipients for {org.name}")
                return {'status': 'skipped', 'reason': 'no_recipients'}

            # Build email content
            email_body = self._build_email_body(org, alert)

            # Send via provider
            result = self.email_provider.send(
                to_addresses=recipients,
                subject=f"⚠️ Regulatory Change: {alert.framework_id}",
                html_body=email_body,
                org_name=org.name
            )

            return {
                'status': 'sent',
                'recipients': recipients,
                'message_id': result.get('message_id')
            }

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return {'status': 'failed', 'error': str(e)}

    def _create_dashboard_alert(self, org, alert) -> Dict:
        """Create in-app dashboard notification"""
        logger.info(f"Creating dashboard alert for {org.name}")

        try:
            from uuid import uuid4

            from core.db.models_regulatory_complete import DashboardNotification

            notification = DashboardNotification(
                notification_id=uuid4(),
                org_id=org.org_id,
                alert_id=alert.alert_id,
                title=f"New Regulatory Requirement: {alert.framework_id}",
                message=f"Framework updated. {alert.affected_asset_count} assets affected. "
                        f"Deadline: {alert.org_implementation_deadline}",
                notification_type='regulatory_change',
                severity=alert.urgency_level,
                is_read=False,
                action_url=f"/dashboard/alerts/{alert.alert_id}",
                created_at=datetime.utcnow()
            )

            self.db.add(notification)
            self.db.commit()

            logger.info(f"Dashboard alert created: {notification.notification_id}")
            return {
                'status': 'created',
                'notification_id': str(notification.notification_id)
            }

        except Exception as e:
            logger.error(f"Dashboard alert creation failed: {e}")
            self.db.rollback()
            return {'status': 'failed', 'error': str(e)}

    def _send_slack(self, org, alert) -> Dict:
        """Send Slack notification (if configured)"""
        logger.info(f"Sending Slack notification for {org.name}")

        try:
            slack_webhook = self._get_slack_webhook(org)
            if not slack_webhook:
                logger.debug(f"No Slack webhook for {org.name}")
                return {'status': 'skipped', 'reason': 'not_configured'}

            import requests

            slack_message = self._build_slack_message(org, alert)

            response = requests.post(
                slack_webhook,
                json=slack_message,
                timeout=10
            )

            if response.status_code == 200:
                return {'status': 'sent'}
            else:
                logger.warning(f"Slack send failed: {response.status_code}")
                return {'status': 'failed', 'status_code': response.status_code}

        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return {'status': 'failed', 'error': str(e)}

    def _build_email_body(self, org, alert) -> str:
        """Build HTML email content"""
        from .email_templates import render_alert_email

        try:
            from core.db.models_regulatory_complete import RegulatoryChange, RegulatoryFramework

            change = self.db.query(RegulatoryChange).filter_by(
                change_id=alert.change_id
            ).first()

            framework = self.db.query(RegulatoryFramework).filter_by(
                framework_id=alert.framework_id
            ).first()

            return render_alert_email({
                'org_name': org.name,
                'framework_name': framework.framework_name if framework else 'Unknown',
                'change_date': change.detected_date.isoformat() if change else None,
                'affected_assets': alert.affected_asset_count,
                'total_assets': alert.total_assets,
                'portfolio_value_affected': alert.portfolio_value_affected_eur,
                'dev_hours': alert.estimated_dev_hours,
                'deadline': alert.org_implementation_deadline.isoformat() if alert.org_implementation_deadline else None,
                'urgency': alert.urgency_level,
                'peer_count': alert.peer_count_affected,
                'peer_avg_weeks': alert.peer_response_avg_weeks,
                'dashboard_url': f"https://climate-platform.com/dashboard/alerts/{alert.alert_id}"
            })

        except Exception as e:
            logger.error(f"Error building email: {e}")
            return "<p>Regulatory alert notification</p>"

    def _build_slack_message(self, org, alert) -> Dict:
        """Build Slack message payload"""
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⚠️ Regulatory Change Detected"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Organization:*\n{org.name}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Affected Assets:*\n{alert.affected_asset_count} of {alert.total_assets}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Dev Effort:*\n{alert.estimated_dev_hours} hours"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Deadline:*\n{alert.org_implementation_deadline}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Urgency:* {alert.urgency_level.upper()}\n"
                               f"*Portfolio at Risk:* €{alert.portfolio_value_affected_eur:,.0f}\n"
                               f"*Peers Affected:* {alert.peer_count_affected} banks"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "View in Dashboard"
                            },
                            "url": f"https://climate-platform.com/dashboard/alerts/{alert.alert_id}"
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Create JIRA Ticket"
                            },
                            "value": str(alert.alert_id)
                        }
                    ]
                }
            ]
        }

    def _get_email_recipients(self, org) -> List[str]:
        """Get compliance team email addresses for org"""
        try:
            from core.db.models_regulatory_complete import User

            # Get users with 'analyst' or 'admin' role
            users = self.db.query(User).filter(
                User.org_id == org.org_id,
                User.role.in_(['analyst', 'admin', 'compliance'])
            ).all()

            return [u.email for u in users if u.email]

        except Exception as e:
            logger.error(f"Error getting recipients: {e}")
            return []

    def _get_slack_webhook(self, org) -> Optional[str]:
        """Get Slack webhook URL for org"""
        # TODO: Store in org integration config
        # For now, return None (Slack optional)
        return None


# ============================================================================
# EMAIL PROVIDERS
# ============================================================================

class SendGridProvider:
    """SendGrid email provider"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        try:
            from sendgrid import SendGridAPIClient
            self.client = SendGridAPIClient(api_key)
        except ImportError:
            logger.error("SendGrid not installed")
            self.client = None

    def send(self, to_addresses: List[str], subject: str, html_body: str, org_name: str) -> Dict:
        """Send email via SendGrid"""
        if not self.client:
            return {'status': 'error', 'message': 'SendGrid not configured'}

        try:
            from sendgrid.helpers.mail import Email, Mail, To

            message = Mail(
                from_email=Email('alerts@climate-platform.com', 'Climate Intelligence Platform'),
                to_emails=[To(addr) for addr in to_addresses],
                subject=subject,
                html_content=html_body
            )

            response = self.client.send(message)

            return {
                'status': 'sent' if response.status_code == 202 else 'failed',
                'message_id': response.headers.get('Server')
            }

        except Exception as e:
            logger.error(f"SendGrid send error: {e}")
            return {'status': 'error', 'message': str(e)}


class SESProvider:
    """AWS SES email provider"""

    def __init__(self, access_key: str, secret_key: str, region: str):
        self.region = region
        try:
            import boto3
            self.client = boto3.client(
                'ses',
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
            )
        except ImportError:
            logger.error("boto3 not installed")
            self.client = None

    def send(self, to_addresses: List[str], subject: str, html_body: str, org_name: str) -> Dict:
        """Send email via AWS SES"""
        if not self.client:
            return {'status': 'error', 'message': 'SES not configured'}

        try:
            response = self.client.send_email(
                Source='alerts@climate-platform.com',
                Destination={'ToAddresses': to_addresses},
                Message={
                    'Subject': {'Data': subject},
                    'Body': {'Html': {'Data': html_body}}
                }
            )

            return {
                'status': 'sent',
                'message_id': response['MessageId']
            }

        except Exception as e:
            logger.error(f"SES send error: {e}")
            return {'status': 'error', 'message': str(e)}


# ============================================================================
# NOTIFICATION QUEUE (for async processing)
# ============================================================================

class NotificationQueue:
    """Queue notifications for async delivery"""

    def __init__(self, db: Session):
        self.db = db

    def enqueue(self, org_id: str, alert_id: str, channels: List[str] = None) -> str:
        """Add notification to queue"""
        from uuid import uuid4

        try:
            queue_id = str(uuid4())

            # TODO: Store in notification_queue table
            # For now, just log
            logger.info(f"Queued notification {queue_id}: org={org_id}, alert={alert_id}, channels={channels}")

            return queue_id

        except Exception as e:
            logger.error(f"Error enqueueing notification: {e}")
            raise

    def process_queue(self) -> Dict:
        """Process pending notifications"""
        # TODO: Implement background worker
        # This will be called by Celery/APScheduler worker
        logger.info("Processing notification queue...")
        return {'processed': 0}
