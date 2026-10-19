"""Is the undertaking required to prepare a sustainability statement for a financial year — Directive (EU) 2022/2464
Art. 5(2) as amended by Directives (EU) 2025/794 and 2026/470 (data/reference/csrd/scope.json, every point quoted).

The answer is True, False or None (not determinable), with the point applied, each condition and what is missing. It
reads only the undertaking's attested statements for that year and undertaking (provided values, family 'esrs'): its
size class and PIE status are its own statements; the numbers are tested against the text's thresholds ('exceed' =
strictly more). A euro threshold is tested only against a figure stated in euro (outside the euro area the national
equivalent is set by the Member State — Directive 2013/34/EU Art. 3(9)).
"""
from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from core import messages

_REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "csrd" / "scope.json"


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads(_REF.read_text())


def _facts(session: Session, org_id: str, entity_id: str | None, period_end: date) -> dict:
    from services.governance.provided_data import ESRS, attested_values
    return {v["concept"]: v for v in attested_values(session, org_id, ESRS, period_end, reporting_entity_id=entity_id)
            if not v.get("member")}


def _within(fy: str, window: dict) -> bool:
    return window["from"] <= fy and (window["until"] is None or fy <= window["until"])


def _label(key: str) -> str:
    from services.governance.esrs_binding import label
    return label(key)


def _exceeds(facts: dict, key: str, threshold: float) -> tuple[bool | None, str]:
    v = facts.get(key)
    if v is None:
        return None, f"{key} not stated"
    if key == "csrd.net_turnover" and v.get("currency") != "EUR":
        return None, (f"net turnover is stated in {v.get('currency')}: the EUR {threshold:,.0f} threshold's national "
                      "equivalent is set by the Member State (Directive 2013/34/EU Art. 3(9))")
    return float(v["value"]) > threshold, f"{key} {float(v['value']):,.0f} {'>' if float(v['value']) > threshold else '≤'} {threshold:,.0f}"


def _condition_msg(facts: dict, key: str, threshold: float | None = None, want=None) -> dict:
    """A condition of the point applied, as a catalogue message: the fact by name, what it is, against what."""
    v = facts.get(key)
    if v is None:
        return messages.render("disclose.esrs.scope.fact_missing", fact=_label(key))
    if threshold is None:
        return messages.render("disclose.esrs.scope.fact_stated", fact=_label(key),
                               value="yes" if int(float(v["value"])) == 1 else "no", want="yes" if want == 1 else "no")
    if key == "csrd.net_turnover" and v.get("currency") != "EUR":
        return messages.render("disclose.esrs.scope.fact_currency", fact=_label(key), currency=v.get("currency") or "—",
                               threshold=f"{threshold:,.0f}")
    over = float(v["value"]) > threshold
    return messages.render("disclose.esrs.scope.fact_over" if over else "disclose.esrs.scope.fact_under", fact=_label(key),
                           value=f"{float(v['value']):,.0f}", threshold=f"{threshold:,.0f}")


def undertakings(session: Session, org_id: str, period_end: date, elections: dict | None = None) -> list[dict]:
    """Every undertaking of the organisation (each reporting entity; the organisation itself when it has none) with its
    stated CSRD role for the financial year and whether Art. 5(2) requires its statement: True / False / None (not
    determinable — the role or a fact is not stated). An exempt subsidiary (Directive 2013/34/EU Art. 19a(9) / 29a(8))
    and a voluntary reporter are not required. `issuer` is its attested csrd.transparency_issuer (the deadline's fact)."""
    from sqlalchemy import text

    from services.governance.csrd_roles import live_role
    rows = session.execute(text("SELECT entity_id::text, name FROM reporting_entities WHERE org_id = CAST(:o AS uuid) ORDER BY name"),
                           {"o": org_id}).all()
    if not rows:
        rows = [(None, session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                                       {"o": org_id}).scalar())]
    out = []
    for eid, name in rows:
        role = live_role(session, org_id, eid, period_end)
        r = role["role"] if role else None
        if r in ("individual", "consolidated"):
            sc = check(session, org_id, eid, period_end, r, elections)
        elif r == "exempt_subsidiary":
            sc = {"required": False, "reason": f"an exempt subsidiary — included in {role.get('parent_name')}'s report "
                                               "(Directive 2013/34/EU Art. 19a(9) / 29a(8))",
                  "msg": messages.render("disclose.esrs.scope.exempt", parent=role.get("parent_name") or "—")}
        elif r == "voluntary":
            sc = {"required": False, "reason": "stated as reporting voluntarily",
                  "msg": messages.render("disclose.esrs.scope.voluntary")}
        else:
            sc = {"required": None, "reason": "the undertaking's CSRD role for this financial year is not stated",
                  "msg": messages.render("disclose.esrs.scope.role_needed")}
        out.append({"entity_id": eid, "name": name, "role": r, **sc,
                    "issuer": _facts(session, org_id, eid, period_end).get("csrd.transparency_issuer")})
    return out


def check(session: Session, org_id: str, entity_id: str | None, period_end: date, role: str | None,
          elections: dict | None = None) -> dict:
    """role: 'individual' or 'consolidated' — the stated CSRD role decides which point applies."""
    from services.regspec import fy_start
    fy = fy_start(period_end).isoformat()
    r = rules()
    if fy <= r["before"]["until"]:
        return {"required": False, "point": None, "reason": r["before"]["reading"], "fy_start": fy,
                "msg": messages.render("disclose.esrs.scope.before", reading=r["before"]["reading"])}
    points = [p for p in r["points"] if _within(fy, p["fy_start"]) and p["role"] == role]
    if not points:
        return {"required": None, "point": None, "fy_start": fy,
                "reason": "state the undertaking's CSRD role (individual or consolidated) for this financial year",
                "msg": messages.render("disclose.esrs.scope.role_needed")}
    p = points[0]
    facts = _facts(session, org_id, entity_id, period_end)
    conds, missing, ok = [], [], True
    for key, want in (p.get("requires") or {}).items():
        v = facts.get(key)
        if v is None:
            missing.append(key)
            conds.append({"fact": key, "met": None, "label": _label(key), "msg": _condition_msg(facts, key)})
            continue
        met = int(float(v["value"])) == want
        conds.append({"fact": key, "met": met, "label": _label(key), "msg": _condition_msg(facts, key, want=want)})
        ok = ok and met
    for key, thr in (p.get("exceeds") or {}).items():
        met, why = _exceeds(facts, key, thr)
        conds.append({"fact": key, "met": met, "detail": why, "label": _label(key), "msg": _condition_msg(facts, key, thr)})
        if met is None:
            missing.append(key)
        else:
            ok = ok and met
    required = False if any(c["met"] is False for c in conds) else (None if missing else ok)
    out = {"required": required, "point": p["id"], "ref": p["ref"], "quote": p["quote"], "conditions": conds,
           "missing": missing, "fy_start": fy,
           "msg": messages.render("disclose.esrs.scope.required" if required else "disclose.esrs.scope.not_required"
                                  if required is False else "disclose.esrs.scope.facts_missing",
                                  facts=", ".join(_label(k) for k in missing) or "—")}
    der = r["member_state_derogation"]
    if required and p["id"] in der["points"] and _within(fy, der["fy_start"]):
        below = [(_exceeds(facts, k, t)[0]) for k, t in (("csrd.net_turnover", 450000000), ("csrd.employees_average", 1000))]
        if any(b is False for b in below):                       # does not exceed one of them: the derogation can apply
            choice = (elections or {}).get(der["switch"], "not_stated")
            out["derogation"] = {"ref": der["ref"], "quote": der["quote"], "stated": choice}
            if choice == der["elected_value"]:
                out["required"] = False
                out["reason"] = "exempted by the Member State for this financial year (derogation stated by the undertaking)"
                out["msg"] = messages.render("disclose.esrs.scope.derogation_applied")
            elif choice == "not_stated":
                out["required"] = None
                out["reason"] = "state whether the undertaking's Member State applied the derogation for 2025-2026"
                out["msg"] = messages.render("disclose.esrs.scope.derogation_unstated")
    return out
