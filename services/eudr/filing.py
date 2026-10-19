"""The EUDR due diligence statement as a filing (E108): prepared from its shipment, then the shared lifecycle — four eyes,
attestation, submission (services.governance.filings, by filing id) — and what the information system's rules add
(Implementing Regulation (EU) 2024/3084 as amended by 2026/1565):

  prepare     only when no check blocks (services.eudr.checks); one live statement per shipment; frozen as a snapshot
  reference   after submission: the reference and verification numbers made available (Art. 7) → 'accepted'
  events      grouped, check notified / ended, placed on the market or exported, given to customs, window extended by the
              authority (with its end), rejected (Art. 8) — append-only (eudr_dds_event)
  withdraw    'within 72 hours after the reference number … was made available' (Art. 5(1)) and not after grouping
              (5(2)), a notified check (5(3)(a), for its period), the placing or export (5(3)(b)) or customs (5(3)(c));
              an authority's extension ends the window at its stated end, never beyond 8 calendar days (5(4))
  amend       the same window: the statement is superseded by a new draft of the same shipment
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages
from services.eudr.words import EudrError, blocking_labels, name, state

WINDOW = timedelta(hours=72)                    # IR 2024/3084 Art. 5(1)
MAX_EXTENSION = timedelta(days=8)               # Art. 5(4): 'not … longer than 8 calendar days'
EVENTS = ("grouped", "check_notified", "check_ended", "placed_or_exported", "given_to_customs", "window_extended", "rejected")


class EudrFilingError(EudrError):
    """A refused step of a statement as a filing: a catalogue code (eudr.refused.*) with its values."""


def _filing(session: Session, org_id: str, filing_id: str) -> dict:
    r = session.execute(text("""SELECT filing_id::text AS filing_id, status, framework, eudr_movement_id::text AS movement_id
                                FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"""),
                        {"f": filing_id, "o": org_id}).mappings().first()
    if r is None or r["framework"] != "eudr_dds":
        raise EudrFilingError("eudr.refused.not_found.statement")
    return dict(r)


def prepare(session: Session, org_id: str, user_id: str, movement_id: str, note: Optional[str] = None,
            supersedes: Optional[str] = None) -> dict:
    """Freeze the statement of a shipment as a draft filing — refused while any check blocks."""
    from services.eudr.checks import checks
    from services.eudr.statement import compute
    from services.governance.filings import _log_event, get_filing
    from services.governance.report_snapshots import create_snapshot
    st = compute(session, org_id, movement_id)
    cs = checks(st)
    if any(not c["passed"] and c["severity"] == "blocking" for c in cs):
        raise EudrFilingError("eudr.refused.blocked.statement", checks=blocking_labels(cs))
    live = session.execute(text("""SELECT filing_id::text, status FROM regulatory_filing WHERE org_id = CAST(:o AS uuid)
                                   AND eudr_movement_id = CAST(:m AS uuid) AND status NOT IN ('superseded', 'withdrawn')"""),
                           {"o": org_id, "m": movement_id}).first()
    if live and live[0] != supersedes:
        raise EudrFilingError("eudr.refused.live.statement", state=state(live[1]))
    # a statement has no reporting period: it is dated by its shipment (placing, making available or export) and named by it
    period_end = date.fromisoformat(st["movement"]["planned_on"])
    label = f"{st['movement']['external_ref'] or 'shipment'} · {period_end.isoformat()}"
    snap = create_snapshot(session, org_id, "eudr_dds", user_id, note=note, period_end=period_end, movement_id=movement_id)
    if supersedes:                               # an amendment within the window: the old statement is superseded first
        session.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE filing_id = CAST(:f AS uuid)"),
                        {"f": supersedes})
    fid = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, note, created_by,
                                       entity_id, eudr_movement_id)
        VALUES (CAST(:o AS uuid), 'eudr_dds', :pe, :pl, 'draft', CAST(:s AS uuid), :n, CAST(:u AS uuid), CAST(:e AS uuid),
                CAST(:m AS uuid)) RETURNING filing_id::text"""),
        {"o": org_id, "pe": period_end, "pl": label, "s": str(snap["snapshot_id"]), "n": note,
         "u": user_id, "e": st["movement"]["reporting_entity_id"], "m": movement_id}).scalar()
    if supersedes:
        session.execute(text("UPDATE regulatory_filing SET superseded_by = CAST(:n AS uuid) WHERE filing_id = CAST(:f AS uuid)"),
                        {"n": fid, "f": supersedes})
        _log_event(session, supersedes, "accepted", "superseded", "amend", user_id, {"superseded_by": fid})
    _log_event(session, fid, None, "draft", "generate", user_id, {"movement_id": movement_id, "supersedes": supersedes})
    return get_filing(session, org_id, fid, with_payload=False)


def events(session: Session, filing_id: str, declaration: bool = False) -> list[dict]:
    """What happened to a filed statement (or declaration), in order, each with its message (eudr.event.*): its name
    for the screen, what it means and its legal basis behind the ⓘ. A declaration's 'reference_received' is its
    identifier being assigned."""
    rows = session.execute(text("""SELECT kind, at, until, detail FROM eudr_dds_event WHERE filing_id = CAST(:f AS uuid)
                                   ORDER BY seq"""), {"f": filing_id}).mappings().all()
    def kind(k: str) -> str:                     # a declaration's reference is its identifier
        return "identifier_received" if declaration and k == "reference_received" else k
    return [{"kind": r["kind"], "at": r["at"].isoformat(), "until": r["until"] and r["until"].isoformat(),
             "detail": r["detail"], "msg": messages.render(f"eudr.event.{kind(r['kind'])}", name=name("event", kind(r["kind"])),
                                                         until=_when(r["until"]))}
            for r in rows]


def _when(t: Optional[datetime]) -> str:
    """A moment as a reader writes it, in UTC (21 Jan 2027, 14:05 UTC)."""
    return f"{t.astimezone(timezone.utc):%d %b %Y, %H:%M} UTC" if t else ""


def record_reference(session: Session, org_id: str, user_id: str, filing_id: str, *, reference_number: str,
                     verification_number: Optional[str], source: str) -> dict:
    """The numbers the information system made available (Art. 7) — the statement is then 'accepted'."""
    from services.governance.filings import _apply_transition
    f = _filing(session, org_id, filing_id)
    if f["status"] != "submitted":
        raise EudrFilingError("eudr.refused.reference.not_submitted", state=state(f["status"]))
    session.execute(text("""INSERT INTO eudr_dds_reference (filing_id, reference_number, verification_number, source, recorded_by)
                            VALUES (CAST(:f AS uuid), :r, :v, :s, CAST(:u AS uuid))"""),
                    {"f": filing_id, "r": reference_number.strip(), "v": (verification_number or "").strip() or None,
                     "s": source, "u": user_id})
    session.execute(text("INSERT INTO eudr_dds_event (filing_id, kind, detail, recorded_by) VALUES (CAST(:f AS uuid), "
                         "'reference_received', :d, CAST(:u AS uuid))"), {"f": filing_id, "d": reference_number, "u": user_id})
    return _apply_transition(session, org_id, filing_id, "accept", user_id, {"reference_number": reference_number})


def record_event(session: Session, org_id: str, user_id: str, filing_id: str, kind: str, *, detail: Optional[str] = None,
                 until: Optional[datetime] = None) -> dict:
    if kind not in EVENTS:
        raise EudrFilingError("eudr.refused.event.unknown")
    f = _filing(session, org_id, filing_id)
    if f["status"] not in ("submitted", "accepted"):
        raise EudrFilingError("eudr.refused.event.not_filed", state=state(f["status"]))
    if kind == "rejected" and (f["status"] != "submitted" or _received_at(session, filing_id) is not None):
        raise EudrFilingError("eudr.refused.event.reject_after_reference")
    if kind == "window_extended":
        received = _received_at(session, filing_id)
        if received is None or until is None:
            raise EudrFilingError("eudr.refused.event.extension_incomplete")
        if until > received + MAX_EXTENSION:
            raise EudrFilingError("eudr.refused.event.extension_too_long", latest=_when(received + MAX_EXTENSION))
    session.execute(text("""INSERT INTO eudr_dds_event (filing_id, kind, until, detail, recorded_by)
                            VALUES (CAST(:f AS uuid), :k, :u2, :d, CAST(:u AS uuid))"""),
                    {"f": filing_id, "k": kind, "u2": until, "d": detail, "u": user_id})
    if kind == "rejected":                       # Art. 8: 'deemed not covered by a Due Diligence Statement'
        from services.governance.filings import _log_event
        session.execute(text("UPDATE regulatory_filing SET status = 'rejected' WHERE filing_id = CAST(:f AS uuid)"),
                        {"f": filing_id})
        _log_event(session, filing_id, f["status"], "rejected", "rejected_by_authority", user_id, {"detail": detail})
    return {"recorded": kind}


def _received_at(session: Session, filing_id: str) -> Optional[datetime]:
    return session.execute(text("SELECT min(at) FROM eudr_dds_event WHERE filing_id = CAST(:f AS uuid) AND kind = 'reference_received'"),
                           {"f": filing_id}).scalar()


def window(session: Session, filing_id: str, now: Optional[datetime] = None) -> dict:
    """Whether the statement may still be amended or withdrawn now: {open, opened, closes, closed_by, msg} — closed_by
    names what closed it (no_reference, grouped, placed_or_exported, given_to_customs, rejected, check_notified,
    expired), msg says it in the catalogue's words (eudr.window.*)."""
    now = now or datetime.now(timezone.utc)
    received = _received_at(session, filing_id)
    if received is None:
        return _window(None, None, "no_reference")
    kinds = [r[0] for r in session.execute(text("SELECT kind FROM eudr_dds_event WHERE filing_id = CAST(:f AS uuid) ORDER BY seq"),
                                           {"f": filing_id}).all()]
    ext = session.execute(text("SELECT max(until) FROM eudr_dds_event WHERE filing_id = CAST(:f AS uuid) "
                               "AND kind = 'window_extended'"), {"f": filing_id}).scalar()
    closes = max(received + WINDOW, ext) if ext else received + WINDOW
    for k in ("grouped", "placed_or_exported", "given_to_customs", "rejected"):
        if k in kinds:
            return _window(received, closes, k)
    if kinds.count("check_notified") > kinds.count("check_ended"):
        return _window(received, closes, "check_notified")
    if now > closes:
        return _window(received, closes, "expired")
    return _window(received, closes, None)


def _window(opened: Optional[datetime], closes: Optional[datetime], closed_by: Optional[str]) -> dict:
    return {"open": closed_by is None, "opened": opened and opened.isoformat(), "closes": closes and closes.isoformat(),
            "closed_by": closed_by, "msg": messages.render(f"eudr.window.{closed_by or 'open'}", closes=_when(closes))}


def withdraw(session: Session, org_id: str, user_id: str, filing_id: str, reason: str) -> dict:
    from services.governance.filings import _log_event, get_filing
    f = _filing(session, org_id, filing_id)
    if f["status"] != "accepted":
        raise EudrFilingError("eudr.refused.withdraw.not_accepted", state=state(f["status"]))
    w = window(session, filing_id)
    if not w["open"]:
        raise EudrFilingError("eudr.refused.window.withdraw", reason=w["msg"]["detail"]["what"])
    if len((reason or "").strip()) < 10:
        raise EudrFilingError("eudr.refused.reason_needed")
    session.execute(text("UPDATE regulatory_filing SET status = 'withdrawn' WHERE filing_id = CAST(:f AS uuid)"), {"f": filing_id})
    _log_event(session, filing_id, "accepted", "withdrawn", "withdraw", user_id,
               {"reason": reason, "window": {k: w[k] for k in ("open", "opened", "closes")}})
    return get_filing(session, org_id, filing_id, with_payload=False)


def refresh(session: Session, org_id: str, user_id: str, filing_id: str, note: Optional[str] = None) -> dict:
    """A draft (or returned) statement after its shipment was corrected: replaced by a freshly frozen draft."""
    from services.governance.filings import _log_event
    f = _filing(session, org_id, filing_id)
    if f["status"] not in ("draft", "returned"):
        raise EudrFilingError("eudr.refused.refresh.not_draft", state=state(f["status"]))
    session.execute(text("UPDATE regulatory_filing SET status = 'withdrawn' WHERE filing_id = CAST(:f AS uuid)"), {"f": filing_id})
    _log_event(session, filing_id, f["status"], "withdrawn", "refresh", user_id, {})
    return prepare(session, org_id, user_id, f["movement_id"], note=note)


def amend(session: Session, org_id: str, user_id: str, filing_id: str, note: Optional[str] = None) -> dict:
    f = _filing(session, org_id, filing_id)
    if f["status"] != "accepted":
        raise EudrFilingError("eudr.refused.amend.not_accepted", state=state(f["status"]))
    w = window(session, filing_id)
    if not w["open"]:
        raise EudrFilingError("eudr.refused.window.amend", reason=w["msg"]["detail"]["what"])
    return prepare(session, org_id, user_id, f["movement_id"], note=note, supersedes=filing_id)
