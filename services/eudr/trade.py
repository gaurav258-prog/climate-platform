"""What a downstream operator or trader holds and keeps for a movement (E122) — Regulation (EU) 2023/1115 Article 5 as in
force — and the new information or substantiated concerns any role must act on (Art. 4(5), 5(5)-(6)).

  5(1)  place, make available or export 'only if they are in possession of the information required under paragraph 3'
  5(2)  a non-SME downstream operator or trader registers in the information system first (SME: micro, small and medium,
        Art. 2(30) — so non-SME is 'large')
  5(3)  (a) each supplier's name, registered trade name or trade mark, postal address, email and, if available, web address,
        and — only where the supplier is an operator — the statements' reference numbers or the declaration identifiers;
        (b) the same of the downstream operators or traders they supplied
  5(4)  kept 'for at least five years from the date of the placing or making available on the market or export'
  5(5)  relevant new information or a substantiated concern: inform the competent authorities and those supplied, at once
  5(6)  non-SME, before placing: inform the authorities and, on a substantiated concern, verify — not placed unless the
        verification shows no or only a negligible risk
A trader 'makes relevant products available on the market' (Art. 2(17)); a downstream operator places on the market or
exports (Art. 2(15b)). Gathered here and judged in checks(); kept by keep() as a frozen, hashed record (eudr_trade_record).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

ROLES = ("downstream_operator", "trader")
SUPPLIER_ROLES = ("operator", "downstream_operator", "trader")
NON_SME = ("large",)                              # Art. 2(30): SMEs are micro, small and medium undertakings


class TradeError(ValueError):
    pass


def _f(rule: str, severity: str, passed: bool, message: str, ref: Optional[str] = None) -> dict:
    return {"rule": rule, "category": "eudr", "severity": severity, "passed": bool(passed), "message": message, "ref": ref}


def concerns(session: Session, movement_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT c.concern_id::text AS concern_id, c.kind, c.received_on, c.detail,
               COALESCE(json_agg(json_build_object('kind', s.kind, 'on_date', s.on_date, 'conclusion', s.conclusion,
                                                   'detail', s.detail) ORDER BY s.seq)
                        FILTER (WHERE s.step_id IS NOT NULL), '[]') AS steps
        FROM eudr_concern c LEFT JOIN eudr_concern_step s USING (concern_id)
        WHERE c.movement_id = CAST(:m AS uuid) GROUP BY c.concern_id, c.seq ORDER BY c.seq"""), {"m": movement_id}).mappings().all()
    return [{**dict(r), "received_on": r["received_on"].isoformat()} for r in rows]


def compute(session: Session, org_id: str, movement_id: str) -> dict:
    from services.eudr import records as REC
    from services.reference.eudr_refdata import scope
    m = session.execute(text("""
        SELECT m.movement_id::text AS movement_id, m.external_ref, m.kind, m.actor_role, m.planned_on, m.hs_code,
               m.description, m.supplier_role, m.upstream_refs, m.reporting_entity_id::text AS entity_id, m.scope_in,
               m.scope_basis,
               s.name AS s_name, s.trade_name AS s_trade, s.address AS s_address, s.contact_email AS s_email, s.web_address AS s_web,
               c.name AS c_name, c.trade_name AS c_trade, c.address AS c_address, c.contact_email AS c_email, c.web_address AS c_web,
               m.supplier_id IS NOT NULL AS has_supplier, m.customer_id IS NOT NULL AS has_customer
        FROM eudr_movement m LEFT JOIN sc_suppliers s USING (supplier_id) LEFT JOIN sc_customers c USING (customer_id)
        WHERE m.movement_id = CAST(:m AS uuid) AND m.org_id = CAST(:o AS uuid)"""), {"m": movement_id, "o": org_id}).mappings().first()
    if m is None:
        raise TradeError("no such movement in this organisation")
    on = m["planned_on"]
    status = REC.live_status(session, org_id, m["entity_id"], on)

    def party(p: str, present: bool) -> Optional[dict]:
        return {"name": m[f"{p}_name"], "trade_name": m[f"{p}_trade"], "postal_address": m[f"{p}_address"],
                "email": m[f"{p}_email"], "web_address": m[f"{p}_web"]} if present else None

    return {
        "movement": {"movement_id": m["movement_id"], "external_ref": m["external_ref"], "kind": m["kind"],
                     "actor_role": m["actor_role"], "on": on.isoformat(), "hs_code": m["hs_code"], "description": m["description"],
                     "scope_in": m["scope_in"], "scope_basis": m["scope_basis"]},
        "scope": scope(m["hs_code"], on),
        "status": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in status.items()} if status else None,
        "art5_3_a": {"supplier": party("s", m["has_supplier"]), "supplier_role": m["supplier_role"],
                     "references": list(m["upstream_refs"] or [])},
        "art5_3_b": {"customer": party("c", m["has_customer"])},
        "concerns": concerns(session, movement_id),
        "keep_until": _keep_until(on).isoformat(),
    }


def _keep_years() -> int:
    """Art. 5(4), read from the retention reference data (rule eudr_5_4) — never typed here."""
    from services.governance.record_retention import rules
    return int(rules()["frameworks"]["eudr_5_4"]["years"])


def _keep_until(on: date) -> date:
    n = _keep_years()
    try:
        return on.replace(year=on.year + n)
    except ValueError:                             # 29 February
        return date(on.year + n, 2, 28)


def _party_checks(out: list, who: str, p: Optional[dict], ref: str) -> None:
    if p is None:
        out.append(_f(f"{who}", "blocking", False, f"no {who} on the movement", ref))
        return
    if not (p.get("name") or p.get("trade_name")):
        out.append(_f(f"{who}_name", "blocking", False, f"the {who}'s name, registered trade name or trade mark", ref))
    if not p.get("postal_address"):
        out.append(_f(f"{who}_address", "blocking", False, f"the {who}'s postal address", ref))
    if not p.get("email"):
        out.append(_f(f"{who}_email", "blocking", False, f"the {who}'s email address", ref))


def concern_checks(st: dict, non_sme: bool, severity: str = "blocking") -> list[dict]:
    """Art. 4(5) / 5(5): inform the authorities at once; Art. 5(6): a non-SME verifies before placing. An operator's
    statement shows an uninformed concern as a warning (its risk assessment weighs it, Art. 10); for Art. 5 it blocks the
    record, which is the possession 5(1) requires."""
    out = []
    on = st["movement"]["on"]
    art = "Art. 5(5)" if st["movement"]["actor_role"] in ROLES else "Art. 4(5)"
    for c in st["concerns"]:
        kinds = [s["kind"] for s in c["steps"]]
        if "authorities_informed" not in kinds:
            out.append(_f(f"informed:{c['concern_id']}", severity, False, f"{c['kind'].replace('_', ' ')} of {c['received_on']}: "
                          "the competent authorities are to be informed immediately — not recorded", art))
        if st["movement"]["actor_role"] in ROLES and non_sme and c["kind"] == "substantiated_concern" and c["received_on"] <= on:
            verified = [s for s in c["steps"] if s["kind"] == "verified"]
            if not verified or verified[-1]["conclusion"] != "negligible":
                out.append(_f(f"verified:{c['concern_id']}", "blocking", False, "a substantiated concern before placing: "
                              "not placed or made available unless the verification demonstrates no or only a negligible risk",
                              "Art. 5(6)"))
    return out


def checks(st: dict) -> list[dict]:
    out: list[dict] = []
    mv, status = st["movement"], st["status"]
    if mv["actor_role"] not in ROLES:
        out.append(_f("role", "blocking", False, "Article 5 is for downstream operators and traders — an operator submits a "
                      "due diligence statement (Art. 4(2)) or a simplified declaration (Art. 4a)", "Art. 4, 5"))
        return out
    if mv["actor_role"] == "trader" and mv["kind"] != "making_available":
        out.append(_f("trader_kind", "blocking", False, "a trader 'makes relevant products available on the market' — placing "
                      "on the market or export is done by an operator or a downstream operator", "Art. 2(15)-(17)"))
    sc = st["scope"]
    if sc.get("in_scope") is False:
        out.append(_f("scope", "blocking", False, f"not a relevant product on {mv['on']}: {sc.get('why')}", "Art. 2(2), Annex I"))
    elif sc.get("in_scope") is None and mv.get("scope_in") is None:
        out.append(_f("scope", "blocking", False, f"Annex I leaves this product's scope open ({sc.get('why')}) — state whether "
                      "it is in scope, and why", "Annex I"))
    non_sme = False
    if status is None:
        out.append(_f("status", "blocking", False, "state the undertaking's EUDR status (its size decides Art. 5(2) and 5(6))",
                      "Art. 2(30), 5(2)"))
    else:
        non_sme = status["size_class"] in NON_SME
        if non_sme and not (status.get("is_registration") or "").strip():
            out.append(_f("registration", "blocking", False, "a non-SME downstream operator or trader registers in the "
                          "information system before placing, making available or export — not stated", "Art. 5(2)"))
    a = st["art5_3_a"]
    _party_checks(out, "supplier", a["supplier"], "Art. 5(3)(a)")
    if a["supplier_role"] is None:
        out.append(_f("supplier_role", "blocking", False, "state whether the supplier is an operator — its statements' reference "
                      "numbers or declaration identifiers are then held", "Art. 5(3)(a)"))
    elif a["supplier_role"] == "operator" and not a["references"]:
        out.append(_f("references", "blocking", False, "the supplier is an operator: the reference numbers of the due diligence "
                      "statements or the declaration identifiers associated with the products", "Art. 5(3)(a)"))
    if mv["kind"] == "making_available":
        _party_checks(out, "customer", st["art5_3_b"]["customer"], "Art. 5(3)(b)")
    elif st["art5_3_b"]["customer"] is None:
        out.append(_f("customer", "info", True, "no downstream operator or trader supplied on this movement", "Art. 5(3)(b)"))
    out += concern_checks(st, non_sme)
    if not any(not f["passed"] and f["severity"] == "blocking" for f in out):
        out.append(_f("ready", "info", True, "the Article 5(3) information is held — the record can be kept"))
    return out


# ── keeping the record (Art. 5(4)) ──

def keep(session: Session, org_id: str, user_id: str, movement_id: str) -> dict:
    """Freeze the movement's Art. 5(3) information as a hashed record, kept until five years after the movement's date."""
    st = compute(session, org_id, movement_id)
    cs = checks(st)
    blocking = [c["message"] for c in cs if not c["passed"] and c["severity"] == "blocking"]
    if blocking:
        raise TradeError("the record cannot be kept yet: " + "; ".join(blocking[:6]))
    payload = {"record": st, "checks": cs}
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    rid = session.execute(text("""
        INSERT INTO eudr_trade_record (org_id, movement_id, payload, payload_sha256, keep_until, recorded_by)
        VALUES (CAST(:o AS uuid), CAST(:m AS uuid), CAST(:p AS jsonb), :h, :k, CAST(:u AS uuid)) RETURNING record_id::text"""),
        {"o": org_id, "m": movement_id, "p": body, "h": hashlib.sha256(body.encode()).hexdigest(), "k": st["keep_until"],
         "u": user_id}).scalar()
    return get(session, org_id, rid)


def get(session: Session, org_id: str, record_id: str) -> dict:
    r = session.execute(text("""SELECT record_id::text AS record_id, movement_id::text AS movement_id, payload, payload_sha256,
                                       keep_until, recorded_at, seq FROM eudr_trade_record
                                WHERE record_id = CAST(:r AS uuid) AND org_id = CAST(:o AS uuid)"""),
                        {"r": record_id, "o": org_id}).mappings().first()
    if r is None:
        raise TradeError("no such record in this organisation")
    body = json.dumps(r["payload"], sort_keys=True, separators=(",", ":"), default=str)
    return {**{k: r[k] for k in ("record_id", "movement_id", "payload", "payload_sha256")},
            "keep_until": r["keep_until"].isoformat(), "recorded_at": r["recorded_at"].isoformat(),
            "hash_verified": hashlib.sha256(body.encode()).hexdigest() == r["payload_sha256"]}


def kept(session: Session, org_id: str, movement_id: str) -> list[dict]:
    rows = session.execute(text("""SELECT record_id::text AS record_id, keep_until, recorded_at FROM eudr_trade_record
                                   WHERE movement_id = CAST(:m AS uuid) AND org_id = CAST(:o AS uuid) ORDER BY seq DESC"""),
                           {"m": movement_id, "o": org_id}).mappings().all()
    return [{"record_id": r["record_id"], "keep_until": r["keep_until"].isoformat(), "recorded_at": r["recorded_at"].isoformat()}
            for r in rows]


# ── new information and substantiated concerns (Art. 4(5), 5(5)-(6)) ──

def add_concern(session: Session, org_id: str, user_id: str, movement_id: str, *, kind: str, received_on: date, detail: str) -> str:
    if kind not in ("new_information", "substantiated_concern"):
        raise TradeError("kind is 'new_information' or 'substantiated_concern' (Art. 2(31))")
    if not session.execute(text("SELECT 1 FROM eudr_movement WHERE movement_id = CAST(:m AS uuid) AND org_id = CAST(:o AS uuid)"),
                           {"m": movement_id, "o": org_id}).first():
        raise TradeError("no such movement in this organisation")
    if len((detail or "").strip()) < 10:
        raise TradeError("describe what was learned")
    return session.execute(text("""INSERT INTO eudr_concern (org_id, movement_id, kind, received_on, detail, recorded_by)
                                   VALUES (CAST(:o AS uuid), CAST(:m AS uuid), :k, :d, :t, CAST(:u AS uuid))
                                   RETURNING concern_id::text"""),
                           {"o": org_id, "m": movement_id, "k": kind, "d": received_on, "t": detail.strip(), "u": user_id}).scalar()


def add_step(session: Session, org_id: str, user_id: str, concern_id: str, *, kind: str, on_date: date,
             conclusion: Optional[str] = None, detail: Optional[str] = None) -> str:
    c = session.execute(text("SELECT received_on FROM eudr_concern WHERE concern_id = CAST(:c AS uuid) AND org_id = CAST(:o AS uuid)"),
                        {"c": concern_id, "o": org_id}).first()
    if c is None:
        raise TradeError("no such concern in this organisation")
    if kind not in ("authorities_informed", "downstream_informed", "verified"):
        raise TradeError("step is authorities_informed, downstream_informed or verified")
    if (kind == "verified") != (conclusion is not None):
        raise TradeError("a verification states its conclusion (negligible / not_negligible) — and only a verification does")
    if on_date < c[0]:
        raise TradeError("a step cannot come before the information was received")
    return session.execute(text("""INSERT INTO eudr_concern_step (concern_id, kind, on_date, conclusion, detail, recorded_by)
                                   VALUES (CAST(:c AS uuid), :k, :d, :cn, :t, CAST(:u AS uuid)) RETURNING step_id::text"""),
                           {"c": concern_id, "k": kind, "d": on_date, "cn": conclusion, "t": detail, "u": user_id}).scalar()
