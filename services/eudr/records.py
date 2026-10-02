"""The operator's own EUDR records (E94): its status per date (four eyes), the legality evidence (Art. 9(1)(h), 2(40)) and
its risk assessment per movement (Art. 10, 11, 13; four eyes). Every quote below is checked against the stored text
(tests/unit/test_eudr_texts.py)."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

ACT = "02023R1115-20260918"

# Art. 10(2): 'the risk assessment shall take into account, in particular, the following risk assessment criteria'
CRITERIA = {
    "a": "the assignment of risk to the relevant country of production or parts thereof in accordance with Article 29",
    "b": "presence of forests",
    "c": "presence of indigenous peoples",
    "d": "consultation and cooperation in good faith with indigenous peoples",
    "e": "duly reasoned claims by indigenous peoples",
    "f": "prevalence of deforestation or forest degradation",
    "g": "the source, reliability, validity, and links to other available documentation of the information referred to in Article 9(1)",
    "h": "level of corruption, prevalence of document and data falsification, lack of law enforcement, violations of "
         "international human rights, armed conflict or presence of sanctions imposed by the UN Security Council or the Council",
    "i": "complexity of the relevant supply chain and the stage of processing",
    "j": "risk of circumvention",
    "k": "conclusions of the meetings of the Commission expert groups",
    "l": "substantiated concerns submitted under Article 31",
    "m": "any information that would point to a risk",
    "n": "complementary information",
}
# Art. 11(1): risk mitigation 'may include' — the operator states what it adopted
MITIGATION = {
    "a": "requiring additional information, data or documents",
    "b": "carrying out independent surveys or audits",
    "c": "taking other measures pertaining to information requirements set out in Article 9",
}
# Art. 2(40): 'relevant legislation of the country of production' — the aspects (a)-(h); Art. 10(3): a FLEGT licence
ASPECTS = ("land_use_rights", "environmental_protection", "forest_rules", "third_party_rights", "labour_rights",
           "human_rights", "fpic", "tax_anticorruption_trade_customs", "flegt_licence")
SIZE_CLASSES = ("micro", "small", "medium", "large")


class RecordError(ValueError):
    pass


def _request(session: Session, org_id: str, user_id: str, kind: str, title: str, payload: dict) -> dict:
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), :k, :t, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id::text"""),
        {"o": org_id, "k": kind, "t": title, "p": json.dumps(payload, default=str), "m": user_id}).scalar()
    return {"status": "pending", "approval_request_id": rid}


def _maker(session: Session, request_id: str) -> str:
    return session.execute(text("SELECT maker_user_id::text FROM approval_requests WHERE request_id = CAST(:r AS uuid)"),
                           {"r": request_id}).scalar()


# ── the undertaking's status ──

def request_status(session: Session, org_id: str, user_id: str, *, entity_id: Optional[str], effective_from: date,
                   size_class: str, country: str, address: str, eori: Optional[str] = None,
                   established_on: Optional[date] = None, basis: Optional[str] = None,
                   primary_own_produce: Optional[bool] = None, other_system: Optional[str] = None) -> dict:
    """Size class within the meaning of Directive 2013/34/EU Art. 3 (Art. 2(30) 'SME'), the date established as such
    (Art. 38(3)), country, EORI (Annex II point 1). For the simplified regime (Art. 4a; E115): whether the undertaking
    places products it itself grew, harvested, obtained from or raised on plots in its country (Art. 2(15a)) — None: not
    stated — and the Union or Member State system holding all its Annex III information, where it states one (Art. 4a(4)).
    A second person approves it."""
    if not str(address or "").strip():
        raise RecordError("the operator's address is required (Annex II point 1)")
    if size_class not in SIZE_CLASSES:
        raise RecordError(f"size class is one of {SIZE_CLASSES} (Directive 2013/34/EU Art. 3)")
    if entity_id and not session.execute(text("SELECT 1 FROM reporting_entities WHERE entity_id = CAST(:e AS uuid) "
                                              "AND org_id = CAST(:o AS uuid)"), {"e": entity_id, "o": org_id}).first():
        raise RecordError("that undertaking is not one of this organisation's entities")
    payload = {"entity_id": entity_id, "effective_from": effective_from.isoformat(), "size_class": size_class,
               "country": (country or "").upper(), "address": address.strip(), "eori": (eori or "").upper() or None,
               "established_on": established_on.isoformat() if established_on else None, "basis": basis,
               "primary_own_produce": primary_own_produce, "other_system": (other_system or "").strip() or None}
    return _request(session, org_id, user_id, "eudr.status", f"EUDR status from {effective_from}: {size_class}", payload)


def apply_status(session: Session, org_id: str, request_id: str, payload: dict, decision: str, checker: str) -> dict:
    if decision != "approved":
        return {"applied": False, "decision": decision}
    session.execute(text("""
        INSERT INTO eudr_undertaking_statement (org_id, reporting_entity_id, effective_from, size_class, established_on,
                                                country, address, eori, basis, requested_by, approved_by, approval_request_id,
                                                primary_own_produce, other_system)
        VALUES (CAST(:o AS uuid), CAST(:e AS uuid), CAST(:f AS date), :s, CAST(:est AS date), :c, :addr, :eori, :b,
                CAST(:m AS uuid), CAST(:a AS uuid), CAST(:q AS uuid), :pop, :os)"""),
        {"o": org_id, "e": payload.get("entity_id"), "f": payload["effective_from"], "s": payload["size_class"],
         "est": payload.get("established_on"), "c": payload["country"], "addr": payload.get("address"), "eori": payload.get("eori"), "b": payload.get("basis"),
         "m": _maker(session, request_id), "a": checker, "q": request_id, "pop": payload.get("primary_own_produce"),
         "os": payload.get("other_system")})
    return {"applied": True}


def live_status(session: Session, org_id: str, entity_id: Optional[str], on: date) -> Optional[dict]:
    r = session.execute(text("""
        SELECT size_class, established_on, country, address, eori, effective_from, primary_own_produce, other_system
        FROM eudr_undertaking_statement
        WHERE org_id = CAST(:o AS uuid) AND reporting_entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) AND effective_from <= :d
        ORDER BY effective_from DESC, seq DESC LIMIT 1"""), {"o": org_id, "e": entity_id, "d": on}).mappings().first()
    return dict(r) if r else None


# ── legality evidence ──

def add_evidence(session: Session, org_id: str, user_id: str, *, aspect: str, document_kind: str,
                 plot_id: Optional[str] = None, supplier_id: Optional[str] = None, movement_id: Optional[str] = None,
                 document_ref: Optional[str] = None, file_sha256: Optional[str] = None, issued_by: Optional[str] = None,
                 valid_from: Optional[date] = None, valid_until: Optional[date] = None, note: Optional[str] = None,
                 withdraws: Optional[str] = None) -> str:
    if aspect not in ASPECTS:
        raise RecordError(f"aspect is one of {ASPECTS} (Art. 2(40) (a)-(h); a FLEGT licence, Art. 10(3))")
    if sum(x is not None for x in (plot_id, supplier_id, movement_id)) != 1:
        raise RecordError("evidence is for one plot, one supplier or one movement")
    for table, col, v in (("sc_sourcing_plots", "plot_id", plot_id), ("sc_suppliers", "supplier_id", supplier_id),
                          ("eudr_movement", "movement_id", movement_id)):
        if v and not session.execute(text(f"SELECT 1 FROM {table} WHERE {col} = CAST(:v AS uuid) AND org_id = CAST(:o AS uuid)"),
                                     {"v": v, "o": org_id}).first():
            raise RecordError(f"no such {col.removesuffix('_id')} in this organisation")
    return session.execute(text("""
        INSERT INTO eudr_legality_evidence (org_id, plot_id, supplier_id, movement_id, aspect, document_kind, document_ref,
                                            file_sha256, issued_by, valid_from, valid_until, note, withdraws, recorded_by)
        VALUES (CAST(:o AS uuid), CAST(:p AS uuid), CAST(:s AS uuid), CAST(:m AS uuid), :a, :k, :r, :sha, :by, :vf, :vu, :n,
                CAST(:w AS uuid), CAST(:u AS uuid)) RETURNING evidence_id::text"""),
        {"o": org_id, "p": plot_id, "s": supplier_id, "m": movement_id, "a": aspect, "k": document_kind, "r": document_ref,
         "sha": file_sha256, "by": issued_by, "vf": valid_from, "vu": valid_until, "n": note, "w": withdraws, "u": user_id}).scalar()


def evidence_for(session: Session, org_id: str, *, plot_ids: list[str], supplier_ids: list[str], movement_id: str,
                 on: date) -> list[dict]:
    """The evidence in force on a date for these plots, suppliers and the movement (a withdrawn one is left out)."""
    rows = session.execute(text("""
        SELECT e.evidence_id::text AS evidence_id, e.aspect, e.document_kind, e.document_ref, e.issued_by, e.valid_from,
               e.valid_until, e.plot_id::text AS plot_id, e.supplier_id::text AS supplier_id, e.movement_id::text AS movement_id
        FROM eudr_legality_evidence e
        WHERE e.org_id = CAST(:o AS uuid) AND e.withdraws IS NULL
          AND NOT EXISTS (SELECT 1 FROM eudr_legality_evidence w WHERE w.withdraws = e.evidence_id)
          AND (e.plot_id = ANY(CAST(:p AS uuid[])) OR e.supplier_id = ANY(CAST(:s AS uuid[])) OR e.movement_id = CAST(:m AS uuid))
          AND (e.valid_from IS NULL OR e.valid_from <= :d) AND (e.valid_until IS NULL OR e.valid_until >= :d)
        ORDER BY e.seq"""), {"o": org_id, "p": plot_ids, "s": supplier_ids, "m": movement_id, "d": on}).mappings().all()
    return [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in rows]


# ── the operator's risk assessment of a movement ──

def request_assessment(session: Session, org_id: str, user_id: str, *, movement_id: str, path: str, conclusion: str,
                       criteria: Optional[dict] = None, mitigation: Optional[dict] = None,
                       circumvention_mixing: Optional[str] = None) -> dict:
    """path 'full': every Art. 10(2) criterion answered in the operator's words; 'simplified' (Art. 13(1)): only where
    all was produced in low-risk countries, with the assessment of circumvention and mixing. Four eyes."""
    if path not in ("full", "simplified"):
        raise RecordError("path is 'full' (Art. 10-11) or 'simplified' (Art. 13)")
    if conclusion not in ("negligible", "not_negligible"):
        raise RecordError("conclusion is 'negligible' (Art. 10(1): no or only a negligible risk) or 'not_negligible'")
    if not session.execute(text("SELECT 1 FROM eudr_movement WHERE movement_id = CAST(:m AS uuid) AND org_id = CAST(:o AS uuid)"),
                           {"m": movement_id, "o": org_id}).first():
        raise RecordError("no such movement in this organisation")
    criteria, mitigation = criteria or {}, mitigation or {}
    if path == "full":
        missing = [k for k in CRITERIA if not str(criteria.get(k) or "").strip()]
        if missing:
            raise RecordError("answer every Art. 10(2) criterion — missing: " + ", ".join(f"({k})" for k in missing))
        if set(mitigation) - set(MITIGATION) - {"other"}:
            raise RecordError(f"mitigation keys are {sorted(MITIGATION)} or 'other' (Art. 11(1))")
    else:
        if not str(circumvention_mixing or "").strip():
            raise RecordError("the simplified path rests on the assessment of circumvention and mixing (Art. 13(1))")
        from services.eudr.statement import countries_of
        risk = countries_of(session, org_id, movement_id)
        not_low = sorted(c for c, r in risk.items() if r != "low")
        if not risk or not_low:
            raise RecordError("the simplified path is only for products all produced in low-risk countries (Art. 13(1)) — "
                              + ("no country of production is known" if not risk else "not low risk: " + ", ".join(not_low)))
    payload = {"movement_id": movement_id, "path": path, "conclusion": conclusion, "criteria": criteria,
               "mitigation": mitigation, "circumvention_mixing": circumvention_mixing}
    return _request(session, org_id, user_id, "eudr.risk", f"EUDR risk assessment ({path}): {conclusion}", payload)


def apply_assessment(session: Session, org_id: str, request_id: str, payload: dict, decision: str, checker: str) -> dict:
    if decision != "approved":
        return {"applied": False, "decision": decision}
    session.execute(text("""
        INSERT INTO eudr_risk_assessment (org_id, movement_id, path, criteria, conclusion, mitigation, circumvention_mixing,
                                          requested_by, approved_by, approval_request_id)
        VALUES (CAST(:o AS uuid), CAST(:m AS uuid), :p, CAST(:c AS jsonb), :con, CAST(:mit AS jsonb), :cm,
                CAST(:mk AS uuid), CAST(:a AS uuid), CAST(:q AS uuid))"""),
        {"o": org_id, "m": payload["movement_id"], "p": payload["path"], "c": json.dumps(payload.get("criteria") or {}),
         "con": payload["conclusion"], "mit": json.dumps(payload.get("mitigation") or {}),
         "cm": payload.get("circumvention_mixing"), "mk": _maker(session, request_id), "a": checker, "q": request_id})
    return {"applied": True}


def live_assessment(session: Session, movement_id: str) -> Optional[dict]:
    r = session.execute(text("""
        SELECT a.path, a.conclusion, a.criteria, a.mitigation, a.circumvention_mixing, a.recorded_at,
               rq.email AS requested_by, ap.email AS approved_by
        FROM eudr_risk_assessment a LEFT JOIN users rq ON rq.user_id = a.requested_by LEFT JOIN users ap ON ap.user_id = a.approved_by
        WHERE a.movement_id = CAST(:m AS uuid) ORDER BY a.seq DESC LIMIT 1"""), {"m": movement_id}).mappings().first()
    return {**dict(r), "recorded_at": r["recorded_at"].isoformat()} if r else None
