"""Regulatory filing lifecycle — the reporting cockpit's engine.

A filing is one regulatory submission (a framework, for a reference period, for an entity). It moves
through a controlled lifecycle, each step logged append-only:

    generate → draft
    submit_for_review → in_review     (raises a 4-eyes approval request)
    approve  → approved               (a *different* user clears the approval; wired via approvals router)
    return   → returned / reject → rejected
    attest   → attested               (a named accountable person certifies the frozen numbers)
    submit   → submitted              (transmitted to the regulator, with a reference)
    accept   → accepted               (regulator acknowledgement)
    supersede→ superseded             (a restatement replaces it)

The frozen numbers behind a filing are a `report_snapshots` row (immutable, hashed, versioned) — this
service never re-implements freezing; it wraps `report_snapshots.create_snapshot`. Honesty carries through
untouched: a euro is firm only where the chain is validated, "—" otherwise, and freezing launders nothing.

Obligations are the filing calendar: what is due, for which entity, by when. They are derived live from the
frameworks that apply to the org's sector, so the calendar is never stale.
"""
from __future__ import annotations

import json
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.report_snapshots import create_snapshot, get_snapshot, _BUILDERS

# framework (== report_snapshots report_type) -> filing metadata.
# `due` is (month, day) in the year AFTER period_end — the statutory filing deadline.
FRAMEWORKS = {
    "bank_tcfd": {"label": "TCFD · EU-Taxonomy disclosure", "sectors": ("bank",),
                  "frequency": "annual", "due": (4, 30),
                  "regulator": "National competent authority / EBA", "basis": "CSRD Art. 8 · TCFD"},
    "sfdr_pai": {"label": "SFDR Principal Adverse Impacts statement", "sectors": ("asset_manager",),
                 "frequency": "annual", "due": (6, 30),
                 "regulator": "National competent authority (SFDR)", "basis": "SFDR RTS 2022/1288 Annex I"},
    # ── agriculture (manufacturer) frameworks — builders already registered in report_snapshots._BUILDERS ──
    "csrd_e1": {"label": "CSRD · ESRS E1 physical-risk report", "sectors": ("manufacturer",),
                "frequency": "annual", "due": (3, 31),
                "regulator": "National competent authority (CSRD)", "basis": "ESRS E1"},
    "esrs_pack": {"label": "ESRS Climate & Nature pack (E1 · E3 · E4)", "sectors": ("manufacturer",),
                  "frequency": "annual", "due": (3, 31),
                  "regulator": "National competent authority (CSRD)", "basis": "ESRS E1 · E3 · E4"},
}

# machine-readable export formats available per framework (rendered from the FROZEN snapshot — see
# services/governance/filing_export.py). json is the universal record; xlsx/xbrl where a renderer exists.
EXPORT_FORMATS = {
    "bank_tcfd": ("json", "xlsx", "xbrl"),
    "sfdr_pai":  ("json", "xlsx", "xbrl"),
    "csrd_e1":   ("json",),
    "esrs_pack": ("json",),
}

# lifecycle: action -> (allowed from-states, resulting to-state)
_TRANSITIONS = {
    "submit_for_review": ({"draft", "returned"}, "in_review"),
    "approve":           ({"in_review"},         "approved"),
    "return":            ({"in_review"},         "returned"),
    "reject":            ({"in_review"},         "rejected"),
    "attest":            ({"approved"},          "attested"),
    "submit":            ({"attested"},          "submitted"),
    "accept":            ({"submitted"},         "accepted"),
    "supersede":         ({"submitted", "accepted", "rejected"}, "superseded"),
}


class FilingError(ValueError):
    """A lifecycle rule was violated (bad transition, missing filing, duplicate slot)."""


# ── framework catalog ──────────────────────────────────────────────────

def available_frameworks(org_type: str) -> list[dict]:
    """Frameworks that apply to this org-type sector, each with its cadence and statutory deadline shape."""
    out = []
    for key, f in FRAMEWORKS.items():
        if org_type in f["sectors"] and key in _BUILDERS:
            out.append({"framework": key, "label": f["label"], "frequency": f["frequency"],
                        "regulator": f["regulator"], "basis": f["basis"]})
    return out


def _due_date(framework: str, period_end: date) -> date:
    m, d = FRAMEWORKS[framework]["due"]
    return date(period_end.year + 1, m, d)


def _period_label(period_end: date) -> str:
    return f"FY{period_end.year}"


# ── obligations calendar (derived live, upserted so history persists) ───

def ensure_obligations(session: Session, org_id: str, org_type: str) -> None:
    """Make sure an obligation row exists for every framework applicable to this org, for the current
    reference period (last completed year-end). Idempotent — safe to call on every calendar read."""
    period_end = date(date.today().year - 1, 12, 31)
    for f in available_frameworks(org_type):
        fk = f["framework"]
        # entity_id is NULL for org-level obligations; a UNIQUE(...) treats NULLs as distinct, so we can't
        # rely on ON CONFLICT here — check existence explicitly (org-level obligation, entity_id IS NULL).
        exists = session.execute(text("""
            SELECT 1 FROM regulatory_obligation
            WHERE org_id = :o AND framework = :fk AND period_end = :pe AND entity_id IS NULL
        """), {"o": org_id, "fk": fk, "pe": period_end}).first()
        if exists:
            continue
        session.execute(text("""
            INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency)
            VALUES (:o, :fk, :pe, :pl, :due, :freq)
        """), {"o": org_id, "fk": fk, "pe": period_end, "pl": _period_label(period_end),
               "due": _due_date(fk, period_end), "freq": FRAMEWORKS[fk]["frequency"]})


def list_obligations(session: Session, org_id: str, org_type: str) -> list[dict]:
    """The filing calendar — each obligation with the live filing that satisfies it (if any) and its status."""
    ensure_obligations(session, org_id, org_type)
    rows = session.execute(text("""
        SELECT ob.obligation_id, ob.framework, ob.period_end, ob.period_label, ob.due_date, ob.frequency,
               f.filing_id, f.status AS filing_status
        FROM regulatory_obligation ob
        LEFT JOIN LATERAL (
            SELECT filing_id, status FROM regulatory_filing rf
            WHERE rf.org_id = ob.org_id AND rf.framework = ob.framework
              AND rf.period_end = ob.period_end AND rf.status <> 'superseded'
            ORDER BY rf.created_at DESC LIMIT 1
        ) f ON TRUE
        WHERE ob.org_id = :o
        ORDER BY ob.due_date
    """), {"o": org_id}).mappings().all()
    today = date.today()
    out = []
    for r in rows:
        status = r["filing_status"] or "not_started"
        done = status in ("submitted", "accepted")
        days_left = (r["due_date"] - today).days
        out.append({
            "obligation_id": str(r["obligation_id"]), "framework": r["framework"],
            "label": FRAMEWORKS.get(r["framework"], {}).get("label", r["framework"]),
            "period_end": r["period_end"].isoformat(), "period_label": r["period_label"],
            "due_date": r["due_date"].isoformat(), "frequency": r["frequency"],
            "filing_id": str(r["filing_id"]) if r["filing_id"] else None,
            "filing_status": status, "days_to_due": days_left,
            "overdue": (not done and days_left < 0),
        })
    return out


# ── filing register ────────────────────────────────────────────────────

def _row_to_summary(r) -> dict:
    return {
        "filing_id": str(r["filing_id"]), "framework": r["framework"],
        "label": FRAMEWORKS.get(r["framework"], {}).get("label", r["framework"]),
        "period_end": r["period_end"].isoformat(), "period_label": r["period_label"],
        "status": r["status"], "snapshot_id": str(r["snapshot_id"]) if r["snapshot_id"] else None,
        "snapshot_version": r.get("snapshot_version"),
        "submission_ref": r["submission_ref"],
        "superseded_by": str(r["superseded_by"]) if r["superseded_by"] else None,
        "note": r["note"], "created_by": r.get("created_by_name"),
        "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat(),
    }


def list_filings(session: Session, org_id: str) -> list[dict]:
    """Every filing for the org — the register, newest first."""
    rows = session.execute(text("""
        SELECT rf.filing_id, rf.framework, rf.period_end, rf.period_label, rf.status, rf.snapshot_id,
               rf.submission_ref, rf.superseded_by, rf.note, rf.created_at, rf.updated_at,
               rs.version AS snapshot_version, u.full_name AS created_by_name
        FROM regulatory_filing rf
        LEFT JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        LEFT JOIN users u ON u.user_id = rf.created_by
        WHERE rf.org_id = :o
        ORDER BY rf.created_at DESC
    """), {"o": org_id}).mappings().all()
    return [_row_to_summary(r) for r in rows]


def get_filing(session: Session, org_id: str, filing_id: str, with_payload: bool = True) -> dict | None:
    """One filing with its full lifecycle history and (optionally) the frozen report payload."""
    r = session.execute(text("""
        SELECT rf.filing_id, rf.framework, rf.period_end, rf.period_label, rf.status, rf.snapshot_id,
               rf.approval_request_id, rf.submission_ref, rf.superseded_by, rf.note,
               rf.created_at, rf.updated_at, rs.version AS snapshot_version, u.full_name AS created_by_name
        FROM regulatory_filing rf
        LEFT JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        LEFT JOIN users u ON u.user_id = rf.created_by
        WHERE rf.org_id = :o AND rf.filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        return None
    out = _row_to_summary(r)
    out["approval_request_id"] = str(r["approval_request_id"]) if r["approval_request_id"] else None
    out["regulator"] = FRAMEWORKS.get(r["framework"], {}).get("regulator")
    out["basis"] = FRAMEWORKS.get(r["framework"], {}).get("basis")

    events = session.execute(text("""
        SELECT e.from_status, e.to_status, e.action, e.detail, e.created_at, u.full_name AS actor_name, u.email AS actor_email
        FROM regulatory_filing_event e
        LEFT JOIN users u ON u.user_id = e.actor_user_id
        WHERE e.filing_id = :f
        ORDER BY e.created_at, e.event_id
    """), {"f": filing_id}).mappings().all()
    out["events"] = [{"from": e["from_status"], "to": e["to_status"], "action": e["action"],
                      "detail": e["detail"], "at": e["created_at"].isoformat(),
                      "actor": e["actor_name"], "actor_email": e["actor_email"]} for e in events]

    # machine-readable exports are only meaningful once the report is frozen
    out["export_formats"] = list(EXPORT_FORMATS.get(r["framework"], ("json",))) if r["snapshot_id"] else []

    if with_payload and r["snapshot_id"]:
        snap = get_snapshot(session, org_id, str(r["snapshot_id"]))
        if snap:
            out["snapshot"] = {"version": snap["version"], "reporting_basis": snap["reporting_basis"],
                               "payload": snap["payload"], "payload_sha256": snap["payload_sha256"],
                               "hash_verified": snap["hash_verified"], "engine_versions": snap["engine_versions"],
                               "created_at": snap["created_at"]}
    return out


def _log_event(session: Session, filing_id: str, from_status: str | None, to_status: str,
               action: str, actor_user_id: str | None, detail: dict | None = None) -> None:
    session.execute(text("""
        INSERT INTO regulatory_filing_event (filing_id, from_status, to_status, action, actor_user_id, detail)
        VALUES (:f, :fs, :ts, :a, :u, CAST(:d AS jsonb))
    """), {"f": filing_id, "fs": from_status, "ts": to_status, "a": action,
           "u": actor_user_id, "d": json.dumps(detail or {}, default=str)})


# ── lifecycle operations ────────────────────────────────────────────────

def preflight(session: Session, org_id: str, org_type: str, framework: str) -> dict:
    """The confirm-data step before freezing: shows the basis, the data coverage, the headline figures and
    any gaps, so a preparer confirms 'this is my data' before a filing is frozen. Computes but freezes nothing."""
    if framework not in FRAMEWORKS or framework not in _BUILDERS:
        raise FilingError(f"unknown framework '{framework}'")
    if org_type not in FRAMEWORKS[framework]["sectors"]:
        raise FilingError(f"framework '{framework}' does not apply to a {org_type}")
    period_end = date(date.today().year - 1, 12, 31)
    existing = session.execute(text("""
        SELECT status FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end = :pe AND status <> 'superseded'
    """), {"o": org_id, "fk": framework, "pe": period_end}).scalar()
    from services.governance.reporting_settings import get_settings
    basis = get_settings(session, org_id)
    summary = _preflight_summary(session, org_id, framework, basis)
    return {"framework": framework, "label": FRAMEWORKS[framework]["label"],
            "period_label": _period_label(period_end), "basis": basis,
            "can_generate": existing is None, "existing_status": existing, **summary}


def _preflight_summary(session: Session, org_id: str, framework: str, basis: dict) -> dict:
    """Live coverage + headline for the confirm-data step. Honest gaps, no freeze."""
    gaps: list[str] = []
    if framework == "bank_tcfd":
        from api.routers.bank import build_disclosure_snapshot
        snap = build_disclosure_snapshot(session, org_id, basis["scenario"], basis["horizon"])
        r = snap["rollup"]
        n_total, n_done = r.get("n_assets", 0), r.get("n_scored", 0)
        if n_total and n_done < n_total:
            gaps.append(f"{n_total - n_done} of {n_total} assets not yet scored — they'd be excluded from exposure")
        return {"coverage": {"label": "assets scored", "done": n_done, "total": n_total,
                             "pct": round(100 * n_done / n_total, 1) if n_total else 0},
                "total_value_eur": r.get("total_value_eur"), "value_at_risk_eur": r.get("value_at_risk_eur"),
                "noun": "assets", "gaps": gaps}
    if framework == "sfdr_pai":
        from ml.regulatory.sfdr_pai import entity_pai_statement
        st = entity_pai_statement(session, org_id)
        if st.get("error"):
            return {"coverage": {"label": "positions", "done": 0, "total": 0, "pct": 0},
                    "total_value_eur": None, "noun": "positions", "gaps": [st["error"]]}
        cs, ent, fr = st["coverage_summary"], st["entity"], st.get("filing_readiness", {})
        if not fr.get("ready_to_file"):
            gaps.append("Manager identity/narratives incomplete: " + ", ".join(fr.get("missing", [])))
        mand, done = cs.get("mandatory_indicators", 0), cs.get("computed", 0)
        if mand and done < mand:
            gaps.append(f"{done}/{mand} mandatory PAI indicators computed — the rest await issuer input")
        return {"coverage": {"label": "PAI indicators computed", "done": done, "total": mand,
                             "pct": round(100 * done / mand, 1) if mand else 0},
                "total_value_eur": ent.get("total_value_eur"), "value_at_risk_eur": None,
                "noun": "positions", "positions": ent.get("positions"), "gaps": gaps}
    # agri (csrd_e1 / esrs_pack) & any other framework — the report assembles from the org's own footprint;
    # no single coverage ratio, so present it cleanly (basis + confirm) rather than a fake 0%.
    return {"coverage": None, "total_value_eur": None, "noun": "sites & sourcing plots", "gaps": []}


def generate_filing(session: Session, org_id: str, org_type: str, framework: str,
                    actor_user_id: str, note: str | None = None, confirmed: bool = False) -> dict:
    """Freeze the report at the org's current basis and open a DRAFT filing over it. One live filing per
    (framework, period) — regenerating while one is live is refused (supersede it first via a restatement)."""
    if framework not in FRAMEWORKS or framework not in _BUILDERS:
        raise FilingError(f"unknown framework '{framework}'")
    if org_type not in FRAMEWORKS[framework]["sectors"]:
        raise FilingError(f"framework '{framework}' does not apply to a {org_type}")
    # the confirm-data step is mandatory — a filing is never frozen without an explicit human confirmation
    if not confirmed:
        raise FilingError("data must be confirmed (via the pre-filing check) before a filing is frozen")
    period_end = date(date.today().year - 1, 12, 31)
    existing = session.execute(text("""
        SELECT filing_id, status FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end = :pe AND status <> 'superseded'
    """), {"o": org_id, "fk": framework, "pe": period_end}).mappings().first()
    if existing:
        raise FilingError(f"a live {framework} filing for {_period_label(period_end)} already exists "
                          f"(status {existing['status']}); supersede it to restate.")

    snap = create_snapshot(session, org_id, framework, actor_user_id, note=note)
    row = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, note, created_by)
        VALUES (:o, :fk, :pe, :pl, 'draft', :snap, :note, :u)
        RETURNING filing_id
    """), {"o": org_id, "fk": framework, "pe": period_end, "pl": _period_label(period_end),
           "snap": snap["snapshot_id"], "note": note, "u": actor_user_id}).mappings().first()
    fid = str(row["filing_id"])
    _log_event(session, fid, None, "draft", "generate", actor_user_id,
               {"snapshot_id": snap["snapshot_id"], "version": snap["version"],
                "payload_sha256": snap["payload_sha256"], "data_confirmed": bool(confirmed)})
    return get_filing(session, org_id, fid, with_payload=False)


def _load(session: Session, org_id: str, filing_id: str) -> dict:
    r = session.execute(text("""
        SELECT filing_id, status, framework, period_label, snapshot_id, approval_request_id
        FROM regulatory_filing WHERE org_id = :o AND filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        raise FilingError("filing not found")
    return dict(r)


def _apply_transition(session: Session, org_id: str, filing_id: str, action: str,
                     actor_user_id: str, detail: dict | None = None,
                     extra_sets: dict | None = None) -> dict:
    allowed_from, to_status = _TRANSITIONS[action]
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in allowed_from:
        raise FilingError(f"cannot {action} a filing that is '{cur['status']}' "
                          f"(needs one of {sorted(allowed_from)})")
    sets = {"status": to_status}
    if extra_sets:
        sets.update(extra_sets)
    set_sql = ", ".join(f"{k} = :{k}" for k in sets)
    params = {**sets, "f": filing_id}
    session.execute(text(f"UPDATE regulatory_filing SET {set_sql} WHERE filing_id = :f"), params)
    _log_event(session, filing_id, cur["status"], to_status, action, actor_user_id, detail)
    return get_filing(session, org_id, filing_id, with_payload=False)


def submit_for_review(session: Session, org_id: str, filing_id: str, actor_user_id: str) -> dict:
    """Move a draft into review and raise a 4-eyes approval request. A *different* user must approve it.
    Refuses if the filing has an open BLOCKING validation issue — a broken filing never reaches a reviewer."""
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in ("draft", "returned"):
        raise FilingError(f"cannot submit a filing that is '{cur['status']}' for review")
    from services.governance.filing_validation import validate_filing, blocking_messages
    vr = validate_filing(session, org_id, filing_id)
    if not vr["passed"]:
        raise FilingError("cannot submit for approval — resolve the blocking validation issue(s): "
                          + "; ".join(blocking_messages(vr)))
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o, 'filing.approve', :ti, CAST(:p AS jsonb), :m)
        RETURNING request_id
    """), {"o": org_id, "ti": f"Approve {FRAMEWORKS[cur['framework']]['label']} · {cur['period_label']}",
           "p": json.dumps({"filing_id": filing_id, "framework": cur["framework"]}),
           "m": actor_user_id}).scalar()
    return _apply_transition(session, org_id, filing_id, "submit_for_review", actor_user_id,
                             detail={"approval_request_id": str(rid),
                                     "validation": {"blocking": vr["blocking"], "warnings": vr["warnings"],
                                                    "checks": vr["checks"]}},
                             extra_sets={"approval_request_id": rid})


def mark_approved(session: Session, org_id: str, filing_id: str, checker_user_id: str,
                  reason: str | None = None) -> dict:
    """Called by the approvals router when a filing.approve request is approved (checker ≠ maker enforced there)."""
    return _apply_transition(session, org_id, filing_id, "approve", checker_user_id,
                             detail={"reason": reason})


def mark_returned(session: Session, org_id: str, filing_id: str, checker_user_id: str,
                  reason: str | None = None, rejected: bool = False) -> dict:
    """Approval sent back (returned→draft) or rejected outright. Both re-open the draft for the preparer
    unless explicitly rejected (terminal-ish; a new filing supersedes)."""
    action = "reject" if rejected else "return"
    return _apply_transition(session, org_id, filing_id, action, checker_user_id, detail={"reason": reason})


def attest(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           attestor_name: str, statement: str) -> dict:
    """A named accountable person certifies the frozen numbers. Distinct from the 4-eyes approval:
    approval is process control; attestation is personal accountability for the filing."""
    if not attestor_name or not statement:
        raise FilingError("attestation needs the accountable person's name and a certification statement")
    return _apply_transition(session, org_id, filing_id, "attest", actor_user_id,
                             detail={"attestor_name": attestor_name, "statement": statement})


def submit(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           submission_ref: str | None = None) -> dict:
    """Transmit to the regulator. Records the submission reference; the record freezes here (guard trigger)."""
    return _apply_transition(session, org_id, filing_id, "submit", actor_user_id,
                             detail={"submission_ref": submission_ref},
                             extra_sets={"submission_ref": submission_ref})


def accept(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           ack_ref: str | None = None) -> dict:
    """Record the regulator's acknowledgement — the filing is accepted."""
    return _apply_transition(session, org_id, filing_id, "accept", actor_user_id,
                             detail={"ack_ref": ack_ref})


def restate_filing(session: Session, org_id: str, filing_id: str, actor_user_id: str, reason: str) -> dict:
    """Restate a filed (submitted/accepted) filing: freeze a fresh snapshot at the current basis into a NEW
    draft, and supersede the old one pointing at the new. Both are preserved — the correction is a new
    version that runs the full lifecycle again, never an edit of the filed record."""
    if not reason:
        raise FilingError("a restatement needs a reason")
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in ("submitted", "accepted"):
        raise FilingError(f"only a filed (submitted/accepted) filing can be restated — this is '{cur['status']}'")

    # period_end of the filing being restated (restatement keeps the same reference period)
    period = session.execute(text(
        "SELECT period_end, period_label FROM regulatory_filing WHERE filing_id = :f"),
        {"f": filing_id}).mappings().first()
    snap = create_snapshot(session, org_id, cur["framework"], actor_user_id,
                           note=f"Restatement of {period['period_label']}: {reason}")
    # supersede the old FIRST so the single-live-slot frees up before the restatement is inserted
    _apply_transition(session, org_id, filing_id, "supersede", actor_user_id, detail={"reason": reason})
    new_fid = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, note, created_by)
        VALUES (:o, :fk, :pe, :pl, 'draft', :snap, :note, :u)
        RETURNING filing_id
    """), {"o": org_id, "fk": cur["framework"], "pe": period["period_end"], "pl": period["period_label"],
           "snap": snap["snapshot_id"], "note": f"Restates {period['period_label']}: {reason}",
           "u": actor_user_id}).scalar()
    _log_event(session, str(new_fid), None, "draft", "generate", actor_user_id,
               {"restates": filing_id, "reason": reason, "snapshot_id": snap["snapshot_id"]})
    # link the superseded old → the restatement (allowed: a superseded row is no longer guard-frozen)
    session.execute(text("UPDATE regulatory_filing SET superseded_by = :n WHERE filing_id = :f"),
                    {"n": new_fid, "f": filing_id})
    return get_filing(session, org_id, str(new_fid), with_payload=False)


def prior_filing_id(session: Session, org_id: str, filing_id: str) -> str | None:
    """The filing this one restates (i.e. the one it superseded), if any — for a variance comparison."""
    r = session.execute(text(
        "SELECT filing_id::text FROM regulatory_filing WHERE org_id = :o AND superseded_by = :f"),
        {"o": org_id, "f": filing_id}).scalar()
    if r:
        return r
    # else: the most recent accepted/submitted filing for the same framework with an EARLIER period
    cur = session.execute(text(
        "SELECT framework, period_end FROM regulatory_filing WHERE filing_id = :f"), {"f": filing_id}).mappings().first()
    if not cur:
        return None
    return session.execute(text("""
        SELECT filing_id::text FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end < :pe AND status IN ('submitted','accepted','superseded')
        ORDER BY period_end DESC, created_at DESC LIMIT 1
    """), {"o": org_id, "fk": cur["framework"], "pe": cur["period_end"]}).scalar()
