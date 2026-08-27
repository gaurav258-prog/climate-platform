"""Scheduled live EUR-Lex change scan — the automation behind the regulatory outlook's live dates.

Celery beat fires `reg.scan_eurlex` daily (see celery_app.beat_schedule). It queries the EU Cellar SPARQL
endpoint for each tracked framework's governing act, updates the stored legal-date snapshot, and records any
that moved at the source as a pending-review detected change. Network-tolerant: unreachable sources are
skipped, never guessed. No operator action required.
"""
from __future__ import annotations

import logging

from services.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="reg.scan_eurlex")
def scan_eurlex() -> dict:
    from core.db.session import get_session
    from services.regulatory_monitoring.eurlex_detector import scan
    with get_session() as s:
        res = scan(s)
    if res["changed"]:
        logger.warning("EUR-Lex scan: detected changes in %s", res["changed"])
    if res["errors"]:
        logger.info("EUR-Lex scan: %d source(s) unreachable (%s)", len(res["errors"]), res["errors"])
    return res


@celery_app.task(name="reg.alert_sweep")
def alert_sweep() -> dict:
    """Raise proactive alerts (task + email + webhook) for detected changes and approaching deadlines."""
    from core.db.session import get_session
    from services.governance.reg_alerts import sweep_all
    with get_session() as s:
        res = sweep_all(s)
    if res["raised"]:
        logger.warning("regulatory alert sweep: raised %d alert(s) across %d orgs", res["raised"], res["orgs"])
    return res
