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


def _exceeds(facts: dict, key: str, threshold: float) -> tuple[bool | None, str]:
    v = facts.get(key)
    if v is None:
        return None, f"{key} not stated"
    if key == "csrd.net_turnover" and v.get("currency") != "EUR":
        return None, (f"net turnover is stated in {v.get('currency')}: the EUR {threshold:,.0f} threshold's national "
                      "equivalent is set by the Member State (Directive 2013/34/EU Art. 3(9))")
    return float(v["value"]) > threshold, f"{key} {float(v['value']):,.0f} {'>' if float(v['value']) > threshold else '≤'} {threshold:,.0f}"


def check(session: Session, org_id: str, entity_id: str | None, period_end: date, role: str | None,
          elections: dict | None = None) -> dict:
    """role: 'individual' or 'consolidated' — the stated CSRD role decides which point applies."""
    from services.regspec import fy_start
    fy = fy_start(period_end).isoformat()
    r = rules()
    if fy <= r["before"]["until"]:
        return {"required": False, "point": None, "reason": r["before"]["reading"], "fy_start": fy}
    points = [p for p in r["points"] if _within(fy, p["fy_start"]) and p["role"] == role]
    if not points:
        return {"required": None, "point": None, "fy_start": fy,
                "reason": "state the undertaking's CSRD role (individual or consolidated) for this financial year"}
    p = points[0]
    facts = _facts(session, org_id, entity_id, period_end)
    conds, missing, ok = [], [], True
    for key, want in (p.get("requires") or {}).items():
        v = facts.get(key)
        if v is None:
            missing.append(key)
            conds.append({"fact": key, "met": None})
            continue
        met = int(float(v["value"])) == want
        conds.append({"fact": key, "met": met})
        ok = ok and met
    for key, thr in (p.get("exceeds") or {}).items():
        met, why = _exceeds(facts, key, thr)
        conds.append({"fact": key, "met": met, "detail": why})
        if met is None:
            missing.append(key)
        else:
            ok = ok and met
    required = False if any(c["met"] is False for c in conds) else (None if missing else ok)
    out = {"required": required, "point": p["id"], "ref": p["ref"], "quote": p["quote"], "conditions": conds,
           "missing": missing, "fy_start": fy}
    der = r["member_state_derogation"]
    if required and p["id"] in der["points"] and _within(fy, der["fy_start"]):
        below = [(_exceeds(facts, k, t)[0]) for k, t in (("csrd.net_turnover", 450000000), ("csrd.employees_average", 1000))]
        if any(b is False for b in below):                       # does not exceed one of them: the derogation can apply
            choice = (elections or {}).get(der["switch"], "not_stated")
            out["derogation"] = {"ref": der["ref"], "quote": der["quote"], "stated": choice}
            if choice == der["elected_value"]:
                out["required"] = False
                out["reason"] = "exempted by the Member State for this financial year (derogation stated by the undertaking)"
            elif choice == "not_stated":
                out["required"] = None
                out["reason"] = "state whether the undertaking's Member State applied the derogation for 2025-2026"
    return out
