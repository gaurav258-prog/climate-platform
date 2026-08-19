"""A small, transport-agnostic mailer over a durable outbox.

`queue_email` records an email in the `email_outbox` table (transactionally with whatever triggered it).
`deliver` attempts to send queued rows via the configured transport and records the outcome — so nothing is
lost, delivery can be retried, and dev/demo runs can render mail without an SMTP server.

Transports (settings.EMAIL_TRANSPORT; "" = auto → smtp if SMTP_HOST set, else off):
  • smtp    — real delivery via SMTP (stdlib smtplib). Credentials come from the environment only.
  • console — render + log the message, mark it sent (dev / demo, no external delivery).
  • off     — record intent only, mark 'skipped' (no mail server configured).
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings

logger = logging.getLogger("tellumen.mailer")


def transport() -> str:
    t = (settings.EMAIL_TRANSPORT or "").strip().lower()
    if t:
        return t
    return "smtp" if settings.SMTP_HOST else "off"


def queue_email(session: Session, *, org_id: str | None, to_email: str, subject: str,
                html: str | None, text_body: str | None, kind: str,
                ref_type: str | None = None, ref_id: str | None = None) -> str | None:
    if not (to_email or "").strip():
        return None
    oid = session.execute(text("""
        INSERT INTO email_outbox (org_id, to_email, subject, body_html, body_text, kind, ref_type, ref_id)
        VALUES (CAST(:o AS uuid), :to, :sub, :html, :txt, :kind, :rt, CAST(:ri AS uuid))
        RETURNING outbox_id
    """), {"o": org_id, "to": to_email.strip(), "sub": subject, "html": html, "txt": text_body,
           "kind": kind, "rt": ref_type, "ri": ref_id}).scalar()
    return str(oid)


def _send_smtp(to_email: str, subject: str, html: str | None, text_body: str | None) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg.set_content(text_body or (html or ""))
    if html:
        msg.add_alternative(html, subtype="html")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as srv:
        if settings.SMTP_STARTTLS:
            srv.starttls(context=ssl.create_default_context())
        if settings.SMTP_USER:
            srv.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        srv.send_message(msg)


def deliver(session: Session, outbox_ids: list[str] | None = None, limit: int = 100) -> dict:
    """Attempt delivery of pending outbox rows (a specific set, or the oldest `limit` pending).
    Never raises — each row's outcome is recorded on the row. Returns a small tally.

    Rows are claimed with FOR UPDATE SKIP LOCKED so concurrent drainers (the request's BackgroundTask and
    the Celery beat sweep) never grab the same row — no double-send."""
    if outbox_ids:
        rows = session.execute(text("""
            SELECT outbox_id, to_email, subject, body_html, body_text FROM email_outbox
            WHERE outbox_id = ANY(CAST(:ids AS uuid[])) AND status IN ('pending','failed')
            FOR UPDATE SKIP LOCKED
        """), {"ids": outbox_ids}).mappings().all()
    else:
        rows = session.execute(text("""
            SELECT outbox_id, to_email, subject, body_html, body_text FROM email_outbox
            WHERE status IN ('pending','failed') ORDER BY created_at LIMIT :n
            FOR UPDATE SKIP LOCKED
        """), {"n": limit}).mappings().all()

    mode = transport()
    tally = {"sent": 0, "skipped": 0, "failed": 0}
    for r in rows:
        status, err = "sent", None
        try:
            if mode == "off":
                status, err = "skipped", "no email transport configured"
            elif mode == "console":
                logger.info("EMAIL[console] to=%s | %s\n%s", r["to_email"], r["subject"], r["body_text"] or r["body_html"] or "")
            elif mode == "smtp":
                _send_smtp(r["to_email"], r["subject"], r["body_html"], r["body_text"])
            else:
                status, err = "skipped", f"unknown transport '{mode}'"
        except Exception as e:  # delivery must never break the caller's transaction intent
            status, err = "failed", str(e)[:500]
            logger.warning("email delivery failed to %s: %s", r["to_email"], e)
        tally[status] = tally.get(status, 0) + 1
        session.execute(text("""
            UPDATE email_outbox SET status = :s, transport = :tr, attempts = attempts + 1,
                   last_error = :e, sent_at = CASE WHEN :s = 'sent' THEN now() ELSE sent_at END
            WHERE outbox_id = :id
        """), {"s": status, "tr": mode, "e": err, "id": r["outbox_id"]})
    return tally


def drain_outbox(limit: int = 200) -> dict:
    """Open a session, deliver the pending outbox, commit. Used by the Celery worker (the beat sweep and the
    on-demand drain) — never on the request path."""
    from core.db.session import get_session
    try:
        with get_session() as s:
            return deliver(s, limit=limit)
    except Exception:  # a background drain must never surface
        logger.exception("outbox drain failed")
        return {"sent": 0, "skipped": 0, "failed": 0}


def request_async_drain() -> None:
    """Best-effort: ask the Celery worker to drain the outbox now (so SMTP delivery is near-real-time without
    touching the request). Enqueued from a daemon thread so a slow/unreachable broker never blocks the caller;
    if it can't be enqueued the Celery beat sweep is the backstop. The worker runs AFTER the request has
    committed, so it always sees the queued row (no read-your-writes race)."""
    import threading

    def _enqueue() -> None:
        try:
            from services.tasks.email_tasks import drain_outbox as task
            task.delay()
        except Exception:
            logger.debug("async drain not enqueued (no broker?); beat sweep will deliver", exc_info=True)

    threading.Thread(target=_enqueue, name="email-drain-enqueue", daemon=True).start()


def dispatch(session: Session) -> None:
    """Deliver queued email for the just-committed action. Fast transports (console / off) go inline in this
    same transaction — instant, no request latency, and they see their own uncommitted rows. SMTP is handed to
    the Celery worker so its network handshake never blocks the request; the beat sweep guarantees delivery."""
    if transport() == "smtp":
        request_async_drain()
    else:
        deliver(session)
