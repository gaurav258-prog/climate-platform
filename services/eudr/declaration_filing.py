"""The simplified declaration as a filing (E115) — Implementing Regulation (EU) 2024/3084 as amended by 2026/1565:

  prepare      from the undertaking's records, refused while a check blocks; one live declaration per undertaking
  four eyes, attest, submit                                                  (the filings cockpit, as for every filing)
  identifier   the declaration identifier and verification number the information system assigns (Art. 7(1)-(2)) —
               or, where the Member State makes the information available, the identifier it communicates (Art. 4a(2))
  update       'following any major changes' (Reg. Art. 4a(3)): a new declaration supersedes the accepted one; 'the
               declaration identifier … shall be maintained in case of an update' (IR Art. 4a(3)) — the update is accepted
               only with the same identifier
  withdraw     'shall enable Information System users to withdraw' (IR Art. 4a(6)) — not once 'used as a reference' in a
               grouping (Art. 4a(7))
  events       grouped (Art. 8a), check notified / ended, rejected (Art. 8: no limit by identifier, unlike a statement)
The database holds the same rules (eudr_declaration_20261002).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.eudr.words import EudrError, blocking_labels, state

FRAMEWORK = "eudr_simplified"
EVENTS = ("grouped", "check_notified", "check_ended", "rejected")
LIVE = "status NOT IN ('superseded', 'withdrawn', 'rejected')"


class DeclarationFilingError(EudrError):
    """A refused step of the declaration as a filing: a catalogue code (eudr.refused.*) with its values."""


def _filing(session: Session, org_id: str, filing_id: str) -> dict:
    f = session.execute(text("""SELECT filing_id::text AS filing_id, status, entity_id::text AS entity_id, supersedes
                                FROM (SELECT f.*, (SELECT o.filing_id::text FROM regulatory_filing o
                                                   WHERE o.superseded_by = f.filing_id LIMIT 1) AS supersedes
                                      FROM regulatory_filing f) x
                                WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid) AND framework = :fw"""),
                        {"f": filing_id, "o": org_id, "fw": FRAMEWORK}).mappings().first()
    if f is None:
        raise DeclarationFilingError("eudr.refused.not_found.declaration")
    return dict(f)


def identifier_of(session: Session, filing_id: str) -> Optional[str]:
    return session.execute(text("SELECT declaration_identifier FROM eudr_declaration_identifier WHERE filing_id = CAST(:f AS uuid)"),
                           {"f": filing_id}).scalar()


def prepare(session: Session, org_id: str, user_id: str, entity_id: Optional[str], note: Optional[str] = None,
            supersedes: Optional[str] = None) -> dict:
    from services.eudr import declaration as D
    from services.governance.filings import _log_event, get_filing
    from services.governance.report_snapshots import create_snapshot
    on = date.today()
    st = D.compute(session, org_id, entity_id, on)
    cs = D.checks(st)
    if any(not c["passed"] and c["severity"] == "blocking" for c in cs):
        raise DeclarationFilingError("eudr.refused.blocked.declaration", checks=blocking_labels(cs))
    live = session.execute(text(f"""SELECT filing_id::text, status FROM regulatory_filing WHERE org_id = CAST(:o AS uuid)
                                    AND framework = :fw AND entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) AND {LIVE}"""),
                           {"o": org_id, "fw": FRAMEWORK, "e": entity_id}).first()
    if live and live[0] != supersedes:
        raise DeclarationFilingError("eudr.refused.live.declaration", state=state(live[1]))
    snap = create_snapshot(session, org_id, FRAMEWORK, user_id, note=note, period_end=on, declaration_entity=entity_id)
    if supersedes:
        session.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE filing_id = CAST(:f AS uuid)"),
                        {"f": supersedes})
    fid = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, note, created_by, entity_id)
        VALUES (CAST(:o AS uuid), :fw, :pe, :pl, 'draft', CAST(:s AS uuid), :n, CAST(:u AS uuid), CAST(:e AS uuid))
        RETURNING filing_id::text"""),
        {"o": org_id, "fw": FRAMEWORK, "pe": on, "pl": f"simplified declaration · {on.isoformat()}",
         "s": str(snap["snapshot_id"]), "n": note, "u": user_id, "e": entity_id}).scalar()
    if supersedes:
        session.execute(text("UPDATE regulatory_filing SET superseded_by = CAST(:n AS uuid) WHERE filing_id = CAST(:f AS uuid)"),
                        {"n": fid, "f": supersedes})
        _log_event(session, supersedes, "accepted", "superseded", "update", user_id, {"superseded_by": fid})
    _log_event(session, fid, None, "draft", "generate", user_id, {"entity_id": entity_id, "updates": supersedes})
    return get_filing(session, org_id, fid, with_payload=False)


def update(session: Session, org_id: str, user_id: str, filing_id: str, note: Optional[str] = None) -> dict:
    """After a major change (Reg. Art. 4a(3)): a new declaration that supersedes the accepted one."""
    f = _filing(session, org_id, filing_id)
    if f["status"] != "accepted":
        raise DeclarationFilingError("eudr.refused.update.not_accepted")
    if _grouped(session, filing_id):
        raise DeclarationFilingError("eudr.refused.grouped.update")
    return prepare(session, org_id, user_id, f["entity_id"], note=note, supersedes=filing_id)


def refresh(session: Session, org_id: str, user_id: str, filing_id: str, note: Optional[str] = None) -> dict:
    """A draft (or returned) declaration after the records were corrected: replaced by a freshly frozen draft."""
    from services.governance.filings import _log_event
    f = _filing(session, org_id, filing_id)
    if f["status"] not in ("draft", "returned"):
        raise DeclarationFilingError("eudr.refused.refresh.not_draft", state=state(f["status"]))
    session.execute(text("UPDATE regulatory_filing SET status = 'withdrawn' WHERE filing_id = CAST(:f AS uuid)"), {"f": filing_id})
    _log_event(session, filing_id, f["status"], "withdrawn", "refresh", user_id, {})
    return prepare(session, org_id, user_id, f["entity_id"], note=note, supersedes=f["supersedes"])


def record_identifier(session: Session, org_id: str, user_id: str, filing_id: str, *, identifier: str,
                      verification_number: Optional[str], source: str) -> dict:
    from services.governance.filings import _apply_transition
    f = _filing(session, org_id, filing_id)
    if f["status"] != "submitted":
        raise DeclarationFilingError("eudr.refused.identifier.not_submitted", state=state(f["status"]))
    identifier = identifier.strip()
    if f["supersedes"]:
        kept = identifier_of(session, f["supersedes"])
        if kept and kept != identifier:
            raise DeclarationFilingError("eudr.refused.identifier.changed", kept=kept)
    session.execute(text("""INSERT INTO eudr_declaration_identifier (filing_id, declaration_identifier, verification_number,
                                                                     source, recorded_by)
                            VALUES (CAST(:f AS uuid), :i, :v, :s, CAST(:u AS uuid))"""),
                    {"f": filing_id, "i": identifier, "v": (verification_number or "").strip() or None, "s": source, "u": user_id})
    session.execute(text("INSERT INTO eudr_dds_event (filing_id, kind, detail, recorded_by) VALUES (CAST(:f AS uuid), "
                         "'reference_received', :d, CAST(:u AS uuid))"), {"f": filing_id, "d": identifier, "u": user_id})
    return _apply_transition(session, org_id, filing_id, "accept", user_id, {"declaration_identifier": identifier})


def _grouped(session: Session, filing_id: str) -> bool:
    return bool(session.execute(text("SELECT 1 FROM eudr_dds_event WHERE filing_id = CAST(:f AS uuid) AND kind = 'grouped'"),
                                {"f": filing_id}).first())


def record_event(session: Session, org_id: str, user_id: str, filing_id: str, kind: str, detail: Optional[str] = None) -> dict:
    from services.governance.filings import _log_event
    if kind not in EVENTS:
        raise DeclarationFilingError("eudr.refused.event.unknown")
    f = _filing(session, org_id, filing_id)
    if f["status"] not in ("submitted", "accepted"):
        raise DeclarationFilingError("eudr.refused.event.not_filed", state=state(f["status"]))
    session.execute(text("INSERT INTO eudr_dds_event (filing_id, kind, detail, recorded_by) VALUES (CAST(:f AS uuid), :k, :d, "
                         "CAST(:u AS uuid))"), {"f": filing_id, "k": kind, "d": detail, "u": user_id})
    if kind == "rejected":                       # Art. 8(2): 'deemed not covered by a … Simplified Declaration'
        session.execute(text("UPDATE regulatory_filing SET status = 'rejected' WHERE filing_id = CAST(:f AS uuid)"), {"f": filing_id})
        _log_event(session, filing_id, f["status"], "rejected", "rejected_by_authority", user_id, {"detail": detail})
    return {"recorded": kind}


def withdraw(session: Session, org_id: str, user_id: str, filing_id: str, reason: str) -> dict:
    from services.governance.filings import _log_event, get_filing
    f = _filing(session, org_id, filing_id)
    if f["status"] not in ("submitted", "accepted"):
        raise DeclarationFilingError("eudr.refused.withdraw.declaration_not_filed", state=state(f["status"]))
    if _grouped(session, filing_id):
        raise DeclarationFilingError("eudr.refused.grouped.withdraw")
    if len((reason or "").strip()) < 10:
        raise DeclarationFilingError("eudr.refused.reason_needed")
    session.execute(text("UPDATE regulatory_filing SET status = 'withdrawn' WHERE filing_id = CAST(:f AS uuid)"), {"f": filing_id})
    _log_event(session, filing_id, f["status"], "withdrawn", "withdraw", user_id, {"reason": reason})
    return get_filing(session, org_id, filing_id, with_payload=False)


def history(session: Session, org_id: str, entity_id: Optional[str]) -> list[dict]:
    """The undertaking's declarations, newest first, with identifier and events."""
    rows = session.execute(text("""
        SELECT f.filing_id::text AS filing_id, f.status, f.period_end, i.declaration_identifier, i.verification_number,
               i.source
        FROM regulatory_filing f LEFT JOIN eudr_declaration_identifier i USING (filing_id)
        WHERE f.org_id = CAST(:o AS uuid) AND f.framework = :fw AND f.entity_id IS NOT DISTINCT FROM CAST(:e AS uuid)
        ORDER BY f.seq DESC"""), {"o": org_id, "fw": FRAMEWORK, "e": entity_id}).mappings().all()
    from services.eudr.filing import events
    out = []
    for r in rows:
        evs = events(session, r["filing_id"], declaration=True)
        out.append({**dict(r), "period_end": r["period_end"].isoformat(), "events": evs,
                    "grouped": any(e["kind"] == "grouped" for e in evs)})
    return out
