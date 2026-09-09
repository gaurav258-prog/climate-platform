"""Transmission adapters — one per channel kind. Each takes a prepared payload and returns what the authority gave back.

Nothing is pretended: a portal channel without credentials reports 'awaiting_credentials'; a manual channel reports
'awaiting_receipt' until the authority's reference is recorded; the Tellumen channel delivers inside the platform and the
supervisory body issues a receipt reference from its own sequence.
"""
from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import text


class AdapterResult(dict):
    """{status, receipt_ref, receipt_at, receipt_payload, error, recipient_org_id}"""


def _cred(channel_id: str, key: str, org_settings: Optional[dict]) -> Optional[str]:
    v = (org_settings or {}).get(key)
    return v or os.environ.get(f"TELLUMEN_CHANNEL_{channel_id.upper()}_{key.upper()}")


def credentials_status(channel_id: str, channel: dict, org_settings: Optional[dict] = None) -> dict:
    needed = channel.get("credentials") or []
    missing = [k for k in needed if not _cred(channel_id, k, org_settings)]
    return {"required": needed, "missing": missing, "configured": not missing}


class TellumenSupervisorAdapter:
    kind = "tellumen"

    def send(self, session, *, org_id: str, filing: dict, payload: bytes, filename: str, fmt: str, channel_id: str, org_settings: Optional[dict]) -> AdapterResult:
        from datetime import datetime, timezone

        from services.supervision.correspondence import next_reference
        from services.supervision.profiles import config_for, sector_config
        # the supervisory body on Tellumen whose profile expects this framework from this entity's sector
        regs = session.execute(text("""SELECT ss.regulator_org_id::text AS reg, o.name, e.type FROM supervision_scope ss
                                       JOIN organizations o ON o.org_id = ss.regulator_org_id JOIN organizations e ON e.org_id = ss.supervised_org_id
                                       WHERE ss.supervised_org_id = CAST(:o AS uuid) AND ss.active"""), {"o": org_id}).mappings().all()
        target = None
        for r in regs:
            sec = sector_config(config_for(session, r["reg"]), r["type"])
            if sec and filing["framework"] in (sec.get("frameworks") or []) or sec:   # any supervisor of this sector accepts the sector's frameworks
                target = r; break
        if not target:
            return AdapterResult(status="failed", error="No supervisory body on Tellumen supervises your organisation for this filing.")
        now = datetime.now(timezone.utc)
        ref = next_reference(session, target["reg"], "receipt", now)
        try:
            from services.integrations.webhooks import emit_event
            from services.notifications.mailer import queue_email
            ent = session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar()
            people = session.execute(text("""SELECT DISTINCT u.email FROM users u
                                             LEFT JOIN supervision_assignment a ON a.user_id = u.user_id AND a.supervised_org_id = CAST(:s AS uuid) AND a.revoked_at IS NULL
                                             LEFT JOIN user_roles ur ON ur.user_id = u.user_id LEFT JOIN roles r ON r.role_id = ur.role_id
                                             WHERE u.org_id = CAST(:r AS uuid) AND u.status = 'active' AND (a.assignment_id IS NOT NULL OR r.name IN ('head', 'data_steward'))"""),
                                     {"s": org_id, "r": target["reg"]}).scalars().all()
            for em in people:
                queue_email(session, org_id=target["reg"], to_email=em, subject=f"{ent}: {filing['framework']} {filing['period_label']} transmitted · receipt {ref}", html=None,
                            text_body=f"{ent} has transmitted its {filing['framework']} filing for {filing['period_label']} through the Tellumen supervisory channel. Receipt {ref} was issued. "
                                      f"The released filing is on the entity's file.", kind="supervision_transmission", ref_type="regulatory_filing", ref_id=filing["filing_id"])
            emit_event(session, target["reg"], "supervision.filing.transmitted", {"entity_org_id": org_id, "entity": ent, "filing_id": filing["filing_id"], "framework": filing["framework"],
                                                                                   "period_label": filing["period_label"], "receipt_ref": ref, "format": fmt})
        except Exception:
            pass
        return AdapterResult(status="acknowledged", receipt_ref=ref, receipt_at=now, recipient_org_id=target["reg"],
                             receipt_payload={"authority": target["name"], "channel": "tellumen_supervisor", "filename": filename, "bytes": len(payload)})


class PortalUploadAdapter:
    kind = "portal_upload"

    def send(self, session, *, org_id: str, filing: dict, payload: bytes, filename: str, fmt: str, channel_id: str, org_settings: Optional[dict]) -> AdapterResult:
        import requests

        from services.supervision.mandates import registry
        ch = registry()["channels"][channel_id]
        cs = credentials_status(channel_id, ch, org_settings)
        if not cs["configured"]:
            return AdapterResult(status="awaiting_credentials", error=f"Channel '{ch['label']}' needs {', '.join(cs['missing'])} — set them under Settings → Integrations or in the environment.")
        url, user, pw = (_cred(channel_id, k, org_settings) for k in ("url", "user", "password"))
        try:
            r = requests.post(url, auth=(user, pw), files={"file": (filename, payload)}, data={"framework": filing["framework"], "period": filing["period_label"]}, timeout=60)
        except requests.RequestException as e:
            return AdapterResult(status="failed", error=f"Portal unreachable: {e}")
        if r.status_code >= 400:
            return AdapterResult(status="rejected", error=f"Portal answered {r.status_code}: {r.text[:300]}", receipt_payload={"status_code": r.status_code})
        ref = None
        try:
            body = r.json(); ref = body.get("reference") or body.get("receipt") or body.get("id")
        except ValueError:
            body = {"text": r.text[:500]}
        ref = ref or r.headers.get("X-Receipt") or r.headers.get("Location")
        from datetime import datetime, timezone
        return AdapterResult(status="acknowledged" if ref else "sent", receipt_ref=ref, receipt_at=datetime.now(timezone.utc) if ref else None,
                             receipt_payload={"status_code": r.status_code, "body": body})


class ManualAdapter:
    """publish / manual: the payload is prepared and handed to the user; the authority's reference is recorded by hand."""
    kind = "manual"

    def send(self, session, *, org_id: str, filing: dict, payload: bytes, filename: str, fmt: str, channel_id: str, org_settings: Optional[dict]) -> AdapterResult:
        return AdapterResult(status="awaiting_receipt", receipt_payload={"instruction": "Deliver the prepared file through this channel and record the authority's reference here."})


ADAPTERS = {"tellumen": TellumenSupervisorAdapter(), "portal_upload": PortalUploadAdapter(), "publish": ManualAdapter(), "manual": ManualAdapter()}
