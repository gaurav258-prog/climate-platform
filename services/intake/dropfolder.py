"""Drop-folder channels: the landing side of an SFTP feed, for any sector's template.

    <INTAKE_DROP_DIR>/<org_id>/<template>/incoming/   the customer's system (via SFTP) writes files here
                                          processed/  after the pipeline took the file (imported, awaiting approval, held)
                                          refused/    refused files, each with <name>.reason.txt saying why

A sweep (Celery beat every 5 minutes, or 'sweep now') takes every file that has stopped changing for
INTAKE_DROP_MIN_AGE_SECONDS — a file still being written is left for the next sweep — and submits it through the SAME
intake pipeline as an upload: security, malware scan, mapping (the pinned one, or the confirmed layout), checks,
matching, 4-eyes. The channel's owner stands as the sender, so a batch with a failed check goes to a DIFFERENT person.
Each file is its own transaction: one bad file never blocks the rest.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings
from services.intake import inbox
from services.intake.catalog import TEMPLATES

logger = logging.getLogger(__name__)


class ChannelError(ValueError):
    pass


def create_channel(session: Session, org_id: str, template: str, owner_user_id: str, created_by: str,
                   mapping_profile_id: Optional[str] = None) -> dict:
    tpl = TEMPLATES.get(template)
    if tpl is None:
        raise ChannelError(f"No template '{template}'.")
    org_type = session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar()
    if org_type != tpl.org_type:
        raise ChannelError(f"The {tpl.label} template is for '{tpl.org_type}' organisations, not '{org_type}'.")
    owner = session.execute(text("SELECT 1 FROM users WHERE user_id = CAST(:u AS uuid) AND org_id = CAST(:o AS uuid)"),
                            {"u": owner_user_id, "o": org_id}).first()
    if not owner:
        raise ChannelError("The owner must be a user of this organisation.")
    folder = f"{org_id}/{template}"
    row = session.execute(text("""
        INSERT INTO intake_channels (org_id, template, folder, owner_user_id, mapping_profile_id, created_by)
        VALUES (CAST(:o AS uuid), :t, :f, CAST(:u AS uuid), CAST(:m AS uuid), CAST(:c AS uuid))
        ON CONFLICT (org_id, template, kind) DO NOTHING RETURNING channel_id::text
    """), {"o": org_id, "t": template, "f": folder, "u": owner_user_id, "m": mapping_profile_id, "c": created_by}).scalar()
    if not row:
        raise ChannelError(f"A drop folder for {tpl.label} already exists.")
    inbox.backend().ensure(folder)
    return get_channel(session, org_id, row)


def get_channel(session: Session, org_id: str, channel_id: str) -> Optional[dict]:
    r = session.execute(text("""
        SELECT c.channel_id::text, c.template, c.folder, c.owner_user_id::text, u.email AS owner_email,
               c.mapping_profile_id::text, c.enabled, c.created_at, c.last_swept_at
        FROM intake_channels c JOIN users u ON u.user_id = c.owner_user_id
        WHERE c.org_id = CAST(:o AS uuid) AND c.channel_id = CAST(:c AS uuid)
    """), {"o": org_id, "c": channel_id}).mappings().first()
    return _shape(dict(r)) if r else None


def list_channels(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT c.channel_id::text, c.template, c.folder, c.owner_user_id::text, u.email AS owner_email,
               c.mapping_profile_id::text, c.enabled, c.created_at, c.last_swept_at
        FROM intake_channels c JOIN users u ON u.user_id = c.owner_user_id
        WHERE c.org_id = CAST(:o AS uuid) ORDER BY c.template
    """), {"o": org_id}).mappings().all()
    return [_shape(dict(r)) for r in rows]


def _shape(d: dict) -> dict:
    try:
        waiting = inbox.backend().ready(d["folder"], min_age=0)
    except inbox.InboxError:
        waiting = []
    return {**d, "label": TEMPLATES[d["template"]].label, "created_at": str(d["created_at"])[:19],
            "last_swept_at": str(d["last_swept_at"])[:19] if d["last_swept_at"] else None,
            "sftp_path": f"/{d['template']}/incoming", "n_waiting": len(waiting)}


def sweep_channel(channel: dict, org_id: str, min_age: Optional[float] = None) -> list[dict]:
    """Submit every finished file in one channel's inbox. Each file in its own session/transaction.
    One sweep per channel at a time, across every server: a session advisory lock on the channel; a second sweep
    (scheduled + 'pick up now', or two instances) finds it held and does nothing, so no file is ever taken twice."""
    from core.db.session import get_session
    from services.intake.pipeline import IntakeError, submit
    box = inbox.backend()
    box.ensure(channel["folder"])
    age = settings.INTAKE_DROP_MIN_AGE_SECONDS if min_age is None else min_age
    results: list[dict] = []
    with get_session() as guard:
        got = guard.execute(text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": f"dropfolder:{channel['channel_id']}"}).scalar()
        if not got:
            return [{"file": None, "state": "busy", "reason": "another pick-up of this folder is running"}]
        try:
            for e in box.ready(channel["folder"], age):
                results.append(_take(box, channel, org_id, e.name, get_session, submit, IntakeError))
            guard.execute(text("UPDATE intake_channels SET last_swept_at = now() WHERE channel_id = CAST(:c AS uuid)"),
                          {"c": channel["channel_id"]})
            guard.commit()
        finally:
            guard.execute(text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": f"dropfolder:{channel['channel_id']}"})
            guard.commit()
    return results


def _take(box, channel: dict, org_id: str, name: str, get_session, submit, IntakeError) -> dict:
    folder = channel["folder"]
    raw = box.read(folder, name)
    with get_session() as s:
        try:
            out = submit(s, org_id, channel["template"], raw, name, via="sftp", user_id=channel["owner_user_id"],
                         mapping_profile_id=channel.get("mapping_profile_id"), channel_id=channel["channel_id"])
            s.commit()
            return {"file": name, "state": out["state"], "batch_id": out.get("batch_id"),
                    "moved_to": "processed/" + box.file_away(folder, name, "processed")}
        except IntakeError as e:
            if e.body.get("batch_id"):
                s.commit()   # the refused attempt stays on the ledger
            else:
                s.rollback()
            msg = e.body.get("message") or e.body.get("error") or "refused"
            return {"file": name, "state": "refused", "batch_id": e.body.get("batch_id"), "reason": msg,
                    "moved_to": "refused/" + box.file_away(folder, name, "refused", msg)}
        except Exception as e:  # noqa: BLE001 — never lose a file: leave it in place and report
            s.rollback()
            logger.exception("drop-folder: %s/%s failed", folder, name)
            return {"file": name, "state": "error", "reason": type(e).__name__}


def sweep_all() -> dict:
    """Every enabled channel, every organisation — the Celery beat entry point."""
    from core.db.session import get_session
    with get_session() as s:
        chans = s.execute(text("""SELECT channel_id::text, org_id::text, template, folder, owner_user_id::text,
                                         mapping_profile_id::text FROM intake_channels WHERE enabled""")).mappings().all()
    out = {"channels": 0, "files": 0, "by_state": {}}
    for c in chans:
        for r in sweep_channel(dict(c), c["org_id"]):
            out["files"] += 1
            out["by_state"][r["state"]] = out["by_state"].get(r["state"], 0) + 1
        out["channels"] += 1
    return out
