"""Notification services.

The live email path is `mailer.py` — a durable `email_outbox` queue with SMTP delivery and a
drain worker (used by the Celery email tasks and the @mention path). Event/webhook push is handled
by `services.integrations.webhooks`. Import those modules directly.
"""
