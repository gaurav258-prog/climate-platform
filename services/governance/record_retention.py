"""CRCS record retention: how long each filed report must be kept, and when it may be archived.

The periods are reference data — data/reference/retention/retention_rules.json, each rule cited to the official text
(act, article, URL, the sentence that sets the period). Nothing here states a period of its own.

For one filing:
  document    what the filing legally is (retention_rules.json "documents"): part of the management / annual report
              (the CSRD sustainability statement, Taxonomy Art. 8 KPIs), a Pillar 3 disclosure, a Solvency and
              Financial Condition Report, an EUDR due-diligence record, a website disclosure
  rules       the framework's own rule(s), plus — for a document that is part of the management / annual report — the
              accounting law of the country whose law governs the filer's records (the reporting entity's country, else
              the organisation's)
  keep until  the latest date any applicable rule reaches, never earlier than the organisation's own policy
              (governed setting retention_minimum_years); a legal hold keeps it regardless
  runs from   as each rule says: the end of the calendar year the document was prepared in, its publication (the
              filing's submission), or the reporting period end. A filing not yet submitted is provisional.
Frozen filings are write-once and never deleted; 'may be archived' means it may leave the active register.
What a screen reads is in customer words: each gap is a catalogue message (intake.retention.gap.*), each rule says when
it runs from in the reference file's own words, and a refusal is a catalogue error (core/errors.UserError).
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.errors import UserError
from core.messages import name, names, render
from services.reference.countries import english_name

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "retention" / "retention_rules.json"


class RetentionError(UserError):
    """A legal-hold step that cannot be taken: a catalogue code (intake.retention.refused.*) with its values."""
    def __init__(self, code: str, status: int = 409, **params):
        super().__init__(code, status, **params)


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads(_FILE.read_text())


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:                                         # 29 February
        return d.replace(year=d.year + years, day=28)


def _start(runs_from: str, *, frozen: date, published: Optional[date], period_end: date) -> tuple[date, bool]:
    """(the date the period runs from, provisional?)"""
    if runs_from == "end_of_calendar_year_prepared":
        return date(frozen.year, 12, 31), False
    if runs_from == "publication":
        return (published, False) if published else (frozen, True)
    if runs_from == "movement_date":            # an EUDR movement: a statement's period end is its shipment's date (E122)
        return period_end, False
    if runs_from == "period_end":
        return period_end, False
    if runs_from == "end_of_period_year":
        return date(period_end.year, 12, 31), False
    raise ValueError(f"the retention reference names a start rule it does not define: {runs_from!r}")


def _facts(session: Session, org_id: str, filing_id: str) -> dict:
    r = session.execute(text("""
        SELECT rf.filing_id::text, rf.framework, rf.status, rf.period_end, rf.legal_hold, rf.legal_hold_reason,
               rf.legal_hold_since, rs.created_at AS frozen_at, o.country AS org_country, re.country AS entity_country,
               re.name AS entity_name,
               (SELECT min(e.created_at) FROM regulatory_filing_event e WHERE e.filing_id = rf.filing_id AND e.to_status = 'submitted') AS published_at
        FROM regulatory_filing rf
        JOIN organizations o ON o.org_id = rf.org_id
        LEFT JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        LEFT JOIN reporting_entities re ON re.entity_id = rf.entity_id
        WHERE rf.filing_id = CAST(:f AS uuid) AND rf.org_id = CAST(:o AS uuid)
    """), {"f": filing_id, "o": org_id}).mappings().first()
    if not r:
        raise RetentionError("error.not_found", 404)
    return dict(r)


def _listed(session: Session, org_id: str) -> Optional[bool]:
    """Whether the organisation has securities listed on a regulated market (its recorded regulatory attribute)."""
    v = session.execute(text("""SELECT value_bool FROM org_regulatory_attribute WHERE org_id = CAST(:o AS uuid) AND attribute = 'listed'"""),
                        {"o": org_id}).scalar()
    return v


def _org_policy_years(session: Session, org_id: str) -> int:
    from services.calc_settings import get_calc_settings
    return int(get_calc_settings(session, org_id).get("retention_minimum_years") or 0)


def retention_for(session: Session, org_id: str, filing_id: str) -> dict:
    f = _facts(session, org_id, filing_id)
    ref = rules()
    doc = ref["documents"].get(f["framework"])
    country = (f["entity_country"] or f["org_country"] or "").strip().upper() or None
    frozen = (f["frozen_at"] or f["period_end"]).date() if hasattr(f["frozen_at"] or f["period_end"], "date") else f["period_end"]
    published = f["published_at"].date() if f["published_at"] else None
    applied, gaps = [], []
    where = english_name(country) if country else None
    if doc is None:
        gaps.append(render("intake.retention.gap.no_mapping"))
        doc = {"document": "unknown", "rules": [], "national": False}
    nat = ref["national"].get(country or "") or []

    def _national_gap():
        ns = ref.get("no_statute", {}).get(country or "")
        gaps.append(render("intake.retention.gap.no_statute", country=where or country, law=f"{ns['act']} {ns['article']}",
                           note=ns["note"]) if ns else
                    render("intake.retention.gap.no_national", country=where or "the country of your records"))

    for key in doc.get("rules", []):
        r = ref["frameworks"][key]
        if r.get("condition") == "listed":
            listed = _listed(session, org_id)
            if listed is None:
                gaps.append(render("intake.retention.gap.listed_unknown", law=f"{r['act']} {r['article']}", years=r["years"]))
                continue
            if not listed:
                continue
        if r.get("equals_national"):
            base = [n for n in nat if r["equals_national"] in n["covers"]]
            if not base:
                _national_gap()
                gaps.append(render("intake.retention.gap.national_period", law=f"{r['act']} {r['article']}"))
                continue
            applied += [{**n, "key": f"{r['key']}:{n['key']}", "act": f"{r['act']} {r['article']} → {n['act']}",
                         "covers_label": r.get("covers_label"), "quote": f"{r['quote']} / {n['quote']}"} for n in base]
            continue
        applied.append(r)
    if doc.get("national"):
        mine = [r for r in nat if doc["document"] in r["covers"]]
        if mine:
            applied += mine
        else:
            _national_gap()
    out_rules, provisional = [], False
    for r in applied:
        if r.get("years") is None:
            gaps.append(render("intake.retention.gap.no_period", law=f"{r['act']} {r['article']}",
                               note=r.get("note") or "It sets no period of its own."))
            continue
        start, prov = _start(r["runs_from"], frozen=frozen, published=published, period_end=f["period_end"])
        provisional |= prov
        out_rules.append({"key": r["key"], "years": r["years"], "runs_from": r["runs_from"], "from": start.isoformat(),
                          "runs_from_label": (ref.get("runs_from") or {}).get(r["runs_from"]),
                          "until": _add_years(start, r["years"]).isoformat(), "act": r["act"], "article": r["article"],
                          "url": r["url"], "quote": r["quote"], "covers": r.get("covers_label"),
                          "coverage": r.get("coverage", "named"), "note": r.get("note"),
                          "scope": "national" if r.get("country") else "eu"})
    legal_until = max((r["until"] for r in out_rules), default=None)
    policy = _org_policy_years(session, org_id)
    policy_from = date(frozen.year, 12, 31)
    policy_until = _add_years(policy_from, policy).isoformat() if policy else None
    keep_until = max([d for d in (legal_until, policy_until) if d], default=None)
    today = date.today().isoformat()
    eligible = bool(keep_until and keep_until < today and not f["legal_hold"] and f["status"] in ("submitted", "accepted", "superseded"))
    docs = names().get("intake.retention_document", {})
    return {"filing_id": filing_id, "framework": f["framework"], "document": doc["document"], "country": country,
            "document_label": docs.get(doc["document"]) or name("intake.retention_document", "unknown"), "country_name": where,
            "rules": out_rules, "legal_until": legal_until, "policy_years": policy, "policy_until": policy_until,
            "policy_from": policy_from.isoformat() if policy else None,
            "keep_until": keep_until, "provisional": provisional, "gaps": gaps,
            "legal_hold": {"on": bool(f["legal_hold"]), "reason": f["legal_hold_reason"],
                           "since": f["legal_hold_since"].isoformat() if f["legal_hold_since"] else None},
            "may_be_archived": eligible, "reference_version": ref["version"]}


def register(session: Session, org_id: str) -> list[dict]:
    """Every live or superseded filing with its retention — the archive view."""
    ids = [r[0] for r in session.execute(text("""
        SELECT filing_id::text FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND snapshot_id IS NOT NULL
        ORDER BY period_end DESC, seq DESC
    """), {"o": org_id}).all()]
    return [retention_for(session, org_id, i) for i in ids]


# ───────────────────────────── legal hold ─────────────────────────────

def set_hold(session: Session, org_id: str, filing_id: str, actor_user_id: str, reason: str) -> dict:
    from services.governance.filings import _log_event
    reason = (reason or "").strip()
    if not reason:
        raise RetentionError("intake.retention.refused.hold_reason", 422)
    f = _facts(session, org_id, filing_id)
    if f["legal_hold"]:
        raise RetentionError("intake.retention.refused.already_held")
    session.execute(text("""UPDATE regulatory_filing SET legal_hold = TRUE, legal_hold_reason = :r, legal_hold_since = now()
                            WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"""), {"r": reason, "f": filing_id, "o": org_id})
    _log_event(session, filing_id, f["status"], f["status"], "legal_hold.set", actor_user_id, {"reason": reason})
    return retention_for(session, org_id, filing_id)


def request_lift(session: Session, org_id: str, filing_id: str, actor_user_id: str, reason: str) -> dict:
    """Lifting a hold is a second person's decision (approval type filing.legal_hold_lift)."""
    reason = (reason or "").strip()
    if not reason:
        raise RetentionError("intake.retention.refused.lift_reason", 422)
    f = _facts(session, org_id, filing_id)
    if not f["legal_hold"]:
        raise RetentionError("intake.retention.refused.not_held")
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), 'filing.legal_hold_lift', :t, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id
    """), {"o": org_id, "t": f"Lift the legal hold on a {f['framework']} filing",
           "p": json.dumps({"filing_id": filing_id, "reason": reason, "held_for": f["legal_hold_reason"]}), "m": actor_user_id}).scalar()
    return {"status": "pending", "approval_request_id": str(rid)}


def apply_lift(session: Session, org_id: str, payload: dict, decision: str, checker_user_id: str) -> dict:
    from services.governance.filings import _log_event
    fid = payload["filing_id"]
    f = _facts(session, org_id, fid)
    if decision != "approved" or not f["legal_hold"]:
        return {"applied": False}
    session.execute(text("""UPDATE regulatory_filing SET legal_hold = FALSE, legal_hold_reason = NULL, legal_hold_since = NULL
                            WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"""), {"f": fid, "o": org_id})
    _log_event(session, fid, f["status"], f["status"], "legal_hold.lifted", checker_user_id,
               {"reason": payload.get("reason"), "was_held_for": payload.get("held_for")})
    return {"applied": True}
