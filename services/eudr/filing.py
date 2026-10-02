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

WINDOW = timedelta(hours=72)                    # IR 2024/3084 Art. 5(1)
MAX_EXTENSION = timedelta(days=8)               # Art. 5(4): 'not … longer than 8 calendar days'
EVENTS = ("grouped", "check_notified", "check_ended", "placed_or_exported", "given_to_customs", "window_extended", "rejected")


class EudrFilingError(ValueError):
    pass


def _filing(session: Session, org_id: str, filing_id: str) -> dict:
    r = session.execute(text("""SELECT filing_id::text AS filing_id, status, framework, eudr_movement_id::text AS movement_id
                                FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"""),
                        {"f": filing_id, "o": org_id}).mappings().first()
    if r is None or r["framework"] != "eudr_dds":
        raise EudrFilingError("no such EUDR statement in this organisation")
    return dict(r)


def prepare(session: Session, org_id: str, user_id: str, movement_id: str, note: Optional[str] = None,
            supersedes: Optional[str] = None) -> dict:
    """Freeze the statement of a shipment as a draft filing — refused while any check blocks."""
    from services.eudr.checks import checks
    from services.eudr.statement import compute
    from services.governance.filings import _log_event, get_filing
    from services.governance.report_snapshots import create_snapshot
    st = compute(session, org_id, movement_id)
    blocking = [c["message"] for c in checks(st) if not c["passed"] and c["severity"] == "blocking"]
    if blocking:
        raise EudrFilingError("the statement cannot be prepared yet: " + "; ".join(blocking[:6]))
    live = session.execute(text("""SELECT filing_id::text, status FROM regulatory_filing WHERE org_id = CAST(:o AS uuid)
                                   AND eudr_movement_id = CAST(:m AS uuid) AND status NOT IN ('superseded', 'withdrawn')"""),
                           {"o": org_id, "m": movement_id}).first()
    if live and live[0] != supersedes:
        raise EudrFilingError(f"this shipment already has a live statement ({live[1]})")
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


def events(session: Session, filing_id: str) -> list[dict]:
    rows = session.execute(text("""SELECT kind, at, until, detail FROM eudr_dds_event WHERE filing_id = CAST(:f AS uuid)
                                   ORDER BY seq"""), {"f": filing_id}).mappings().all()
    return [{"kind": r["kind"], "at": r["at"].isoformat(), "until": r["until"] and r["until"].isoformat(),
             "detail": r["detail"]} for r in rows]


def record_reference(session: Session, org_id: str, user_id: str, filing_id: str, *, reference_number: str,
                     verification_number: Optional[str], source: str) -> dict:
    """The numbers the information system made available (Art. 7) — the statement is then 'accepted'."""
    from services.governance.filings import _apply_transition
    f = _filing(session, org_id, filing_id)
    if f["status"] != "submitted":
        raise EudrFilingError(f"a reference is recorded for a submitted statement (this one is '{f['status']}')")
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
        raise EudrFilingError(f"event is one of {EVENTS}")
    f = _filing(session, org_id, filing_id)
    if f["status"] not in ("submitted", "accepted"):
        raise EudrFilingError("events are recorded on a submitted statement")
    if kind == "rejected" and (f["status"] != "submitted" or _received_at(session, filing_id) is not None):
        raise EudrFilingError("a statement can be rejected only before its reference number is available (IR 2024/3084 "
                              "Art. 8(1))")
    if kind == "window_extended":
        received = _received_at(session, filing_id)
        if received is None or until is None:
            raise EudrFilingError("an extension needs the reference received and the end the authority set")
        if until > received + MAX_EXTENSION:
            raise EudrFilingError("an extension ends no later than 8 calendar days after the reference (Art. 5(4))")
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
    """Whether the statement may still be amended or withdrawn now, and why not."""
    now = now or datetime.now(timezone.utc)
    received = _received_at(session, filing_id)
    if received is None:
        return {"open": False, "why": "no reference number has been made available yet"}
    evs = events(session, filing_id)
    kinds = [e["kind"] for e in evs]
    ext = [datetime.fromisoformat(e["until"]) for e in evs if e["kind"] == "window_extended"]
    closes = max([received + WINDOW, *ext])
    for k, why in (("grouped", "it was used for grouping (Art. 5(2))"), ("placed_or_exported", "the product was placed "
                   "on the market or exported (Art. 5(3)(b))"), ("given_to_customs", "the reference number was given to "
                   "customs (Art. 5(3)(c))"), ("rejected", "it was rejected (Art. 8)")):
        if k in kinds:
            return {"open": False, "closes": closes.isoformat(), "why": why}
    if kinds.count("check_notified") > kinds.count("check_ended"):
        return {"open": False, "closes": closes.isoformat(), "why": "a check is notified, for its period (Art. 5(3)(a))"}
    if now > closes:
        return {"open": False, "closes": closes.isoformat(), "why": f"the window closed at {closes.isoformat()} (Art. 5(1), (4))"}
    return {"open": True, "closes": closes.isoformat()}


def withdraw(session: Session, org_id: str, user_id: str, filing_id: str, reason: str) -> dict:
    from services.governance.filings import _log_event, get_filing
    f = _filing(session, org_id, filing_id)
    if f["status"] != "accepted":
        raise EudrFilingError("a statement with its reference number is withdrawn here; a draft is withdrawn in the register")
    w = window(session, filing_id)
    if not w["open"]:
        raise EudrFilingError(f"it can no longer be withdrawn: {w['why']}")
    if len((reason or "").strip()) < 10:
        raise EudrFilingError("say why it is withdrawn")
    session.execute(text("UPDATE regulatory_filing SET status = 'withdrawn' WHERE filing_id = CAST(:f AS uuid)"), {"f": filing_id})
    _log_event(session, filing_id, "accepted", "withdrawn", "withdraw", user_id, {"reason": reason, "window": w})
    return get_filing(session, org_id, filing_id, with_payload=False)


def refresh(session: Session, org_id: str, user_id: str, filing_id: str, note: Optional[str] = None) -> dict:
    """A draft (or returned) statement after its shipment was corrected: replaced by a freshly frozen draft."""
    from services.governance.filings import _log_event
    f = _filing(session, org_id, filing_id)
    if f["status"] not in ("draft", "returned"):
        raise EudrFilingError("only a draft or returned statement is refreshed")
    session.execute(text("UPDATE regulatory_filing SET status = 'withdrawn' WHERE filing_id = CAST(:f AS uuid)"), {"f": filing_id})
    _log_event(session, filing_id, f["status"], "withdrawn", "refresh", user_id, {})
    return prepare(session, org_id, user_id, f["movement_id"], note=note)


def amend(session: Session, org_id: str, user_id: str, filing_id: str, note: Optional[str] = None) -> dict:
    f = _filing(session, org_id, filing_id)
    if f["status"] != "accepted":
        raise EudrFilingError("only a statement with its reference number is amended")
    w = window(session, filing_id)
    if not w["open"]:
        raise EudrFilingError(f"it can no longer be amended: {w['why']}")
    return prepare(session, org_id, user_id, f["movement_id"], note=note, supersedes=filing_id)
