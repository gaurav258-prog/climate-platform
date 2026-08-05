"""Email outbox mailer — queue + best-effort delivery, and the task-@mention email ping. Requires PostgreSQL."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from core import config
from services.notifications import mailer
import services.governance.tasks as T

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _actor(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


@pytest.mark.integration
def test_outbox_off_transport_skips(monkeypatch):
    monkeypatch.setattr(config.settings, "EMAIL_TRANSPORT", "off", raising=False)
    with get_session() as s:
        oid = mailer.queue_email(s, org_id=BANK_ORG, to_email="x@demo.test", subject="hi",
                                 html="<p>hi</p>", text_body="hi", kind="test")
        tally = mailer.deliver(s, [oid])
        assert tally["skipped"] == 1
        row = s.execute(text("SELECT status, transport FROM email_outbox WHERE outbox_id=:i"), {"i": oid}).mappings().first()
        assert row["status"] == "skipped" and row["transport"] == "off"
        s.rollback()


@pytest.mark.integration
def test_outbox_console_transport_sends(monkeypatch):
    monkeypatch.setattr(config.settings, "EMAIL_TRANSPORT", "console", raising=False)
    with get_session() as s:
        oid = mailer.queue_email(s, org_id=BANK_ORG, to_email="x@demo.test", subject="hi",
                                 html=None, text_body="hi", kind="test")
        tally = mailer.deliver(s, [oid])
        assert tally["sent"] == 1
        row = s.execute(text("SELECT status, sent_at FROM email_outbox WHERE outbox_id=:i"), {"i": oid}).mappings().first()
        assert row["status"] == "sent" and row["sent_at"] is not None
        s.rollback()


@pytest.mark.integration
def test_mention_queues_email(monkeypatch):
    monkeypatch.setattr(config.settings, "EMAIL_TRANSPORT", "console", raising=False)
    with get_session() as s:
        maker = _actor(s)
        target = str(s.execute(text("SELECT user_id FROM users WHERE email='approver@meridian.demo'")).scalar())
        t = T.create_task(s, BANK_ORG, maker, title="Ping by email")
        T.comment(s, BANK_ORG, t["task_id"], maker, "@Pieter please confirm", mentions=[target])
        row = s.execute(text("""
            SELECT to_email, kind, status FROM email_outbox
            WHERE kind='task_mention' ORDER BY created_at DESC LIMIT 1
        """)).mappings().first()
        assert row["to_email"] == "approver@meridian.demo" and row["status"] == "sent"
        s.rollback()
