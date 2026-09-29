"""Demo data: give every demo bank's loan book the per-exposure facts a real loan tape carries for Pillar 3 Templates 2
and 7-9 (GAR / BTAR / energy efficiency of the collateral), so the demo shows those templates filled.

Demo only — for organisations of type 'bank' whose name ends '(demo)'. Deterministic: every value is derived from the
exposure's own id and attributes, so re-runs give the same book. Fills only facts that are empty — a stated value is
never overwritten. It never sets Taxonomy alignment (that stays whatever the Taxonomy classification says); for an
exposure already classified eligible or aligned it states the environmental objective the activity contributes to.

    venv/bin/python -m scripts.seed_demo_gar_facts
"""
from __future__ import annotations

import hashlib

from sqlalchemy import text

from core.db.session import get_session
from services.reference import nace as _nace

_EP_FROM_EPC = {"A": 45, "B": 85, "C": 135, "D": 185, "E": 245, "F": 330, "G": 440}   # typical kWh/m² per label (demo)


def _u(entity_id: str, salt: str) -> float:
    """A stable number in [0, 1) for this exposure and purpose."""
    return int(hashlib.sha256(f"{entity_id}:{salt}".encode()).hexdigest()[:8], 16) / 0x100000000


def facts_for(r: dict) -> dict:
    eid, nace, atype = r["entity_id"], r["nace_code"], r["entity_type"]
    gross = float(r["outstanding_loan_balance_eur"] or r["primary_value_eur"] or 0)
    sec = _nace.section(nace)
    hit = _nace.lookup(nace)
    if sec == "K":
        cp = "credit_institution" if hit and hit["dotted"].startswith("64.1") else "other_financial_corporation"
    elif sec == "O":
        cp = "general_government"
    elif sec:
        cp = "non_financial_corporation"
    elif atype == "residential_real_estate":
        cp = "household"
    else:
        cp = "non_financial_corporation"
    out = {"counterparty_sector": cp}
    if cp == "other_financial_corporation":
        out["counterparty_subsector"] = ("investment_firm", "management_company", "insurance_undertaking")[int(_u(eid, "sub") * 3)]
    if cp == "non_financial_corporation":
        out["nfrd_subject"] = gross >= 20_000_000 or _u(eid, "nfrd") < 0.3
    u = _u(eid, "instr")
    out["instrument_type"] = ("loans_and_advances" if u < 0.86 or cp == "household" else
                              "debt_securities" if u < 0.95 else "equity_instruments")
    out["trading_book"] = False
    if atype == "residential_real_estate":
        out["immovable_collateral"] = "residential"
    elif atype in ("commercial_real_estate", "office"):
        out["immovable_collateral"] = "commercial"
    if cp == "household":
        p = _u(eid, "purpose")
        out["loan_purpose"] = "building_renovation" if p < 0.12 else "other"
    if cp == "general_government":
        out["loan_purpose"] = "housing" if _u(eid, "purpose") < 0.4 else "other"
    if cp == "non_financial_corporation" and out["instrument_type"] == "loans_and_advances":
        out["specialised_lending"] = gross >= 10_000_000 and _u(eid, "sl") < 0.25
    if (r["taxonomy_status"] or "") in ("eligible", "aligned"):
        out["taxonomy_objective"] = "cca" if _u(eid, "obj") < 0.15 else "ccm"
    if out.get("immovable_collateral"):
        epc = (r["epc_label"] or "").strip().upper()
        if epc in _EP_FROM_EPC:
            out["ep_score_kwh_m2"] = round(_EP_FROM_EPC[epc] * (0.85 + 0.3 * _u(eid, "ep")), 1)
            out["ep_score_estimated"] = False
        else:
            out["ep_score_kwh_m2"] = round(120 + 260 * _u(eid, "ep"), 1)
            out["ep_score_estimated"] = True
    return out


def main() -> None:
    with get_session() as s:
        rows = s.execute(text("""
            SELECT e.entity_id::text AS entity_id, e.nace_code, e.entity_type, CAST(e.primary_value_eur AS FLOAT) AS primary_value_eur,
                   CAST(x.outstanding_loan_balance_eur AS FLOAT) AS outstanding_loan_balance_eur, x.taxonomy_status, x.epc_label
            FROM portfolio_entities e
            JOIN organizations o ON o.org_id = e.org_id
            JOIN ext_banking x ON x.entity_id = e.entity_id
            WHERE e.vertical = 'banking' AND o.type = 'bank' AND o.name LIKE '%(demo)'""")).mappings().all()
        n = 0
        for r in rows:
            f = facts_for(dict(r))
            sets = ", ".join(f"{k} = COALESCE({k}, :{k})" for k in f)          # never overwrite a stated fact
            s.execute(text(f"UPDATE ext_banking SET {sets} WHERE entity_id = CAST(:e AS uuid)"), {**f, "e": r["entity_id"]})
            n += 1
        s.commit()
    print(f"demo GAR facts: {n} exposures across the demo banks")


if __name__ == "__main__":
    main()
