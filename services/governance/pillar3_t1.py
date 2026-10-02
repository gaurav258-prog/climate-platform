"""Pillar 3 ESG Template 1, columns i, j and k — the financed emissions and the share derived from company reporting,
to the instructions (Annex XL, the same wording under ITS 2022/2453 and ITS 2024/3172; quoted in
data/reference/pillar3/t1_financed_emissions.json, every quote checked against the stored text by
tests/unit/test_t1_financed_emissions.py).

What the instructions leave to the institution is its own statement — two governed methodology switches
(services.calc_settings, four eyes where the organisation requires it, stamped on every filing), with no default:
  p3esg_t1_emissions_estimation  which counterparty emissions it estimates: scopes 1-3; scopes 1 and 2 (scope 3 is part
                                 of column i 'where the information is available'; column j is then left blank, as the
                                 instructions say); or not yet (columns i-k blank, the plans narrated)
  p3esg_t1_attribution           how a counterparty's emissions are attributed to the exposure: the proportion the
                                 instructions name — the exposure compared to the counterparty's total liabilities
                                 (accounting liabilities and shareholders' equity). PCAF's own per-asset-class attribution is
                                 not offered: the platform's PCAF computation is not it (see the reference file).
Not stated → the columns are a named gap and the filing is blocked (filing_validation).

Per exposure (its gross carrying amount x, the counterparty's total liabilities L, stated with its balance-sheet date):
  attributed emissions = x / L × the counterparty's emissions of the scopes the institution estimates
Column i sums them over the exposures stating every scope it estimates (a missing scope is never 0, E76/E79); column j
sums the attributed scope 3; column k is the share of the row's gross carrying amount whose column-i emissions the
counterparty reported (emissions_company_reported) — where an exposure in column i does not record its emissions'
source, k is a gap. An exposure stating emissions but not L is not attributable (counted; the filing is blocked until L
is stated); one whose exposure exceeds L cannot be right (counted; blocked).

The narrative the instructions require (data sources, methodology, which of reported / physical activity-based /
economic activity-based emissions, the plans) is answered in the one store of template answers (family bank_p3esg,
document qualitative, keys 't1.*'), frozen with the filing and checked by validation.

A filing frozen before this (no 't1_emissions' record) printed the counterparties' reported emissions un-attributed;
it is rendered as frozen, and says so.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "pillar3" / "t1_financed_emissions.json"
ESTIMATION, ATTRIBUTION = "p3esg_t1_emissions_estimation", "p3esg_t1_attribution"
ESTIMATING = ("scope_1_2_3", "scope_1_2")
SCOPES = {"scope_1_2_3": ("ghg1", "ghg2", "ghg3"), "scope_1_2": ("ghg1", "ghg2")}
RECORD = "t1_emissions"            # the payload key a filing freezes the statements and the narrative under


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(_REF.read_text())


def quote(qid: str) -> str:
    q = reference()["quotes"][qid]
    return f"“{q['quote']}” ({q['ref']})"


def switches() -> dict:
    """The two statements as interpretation switches: label, the quoted text as description, the allowed options."""
    out = {}
    for key, st in reference()["statements"].items():
        desc = " ".join(quote(q) for q in st["quotes"]) + " Options — " + "; ".join(
            f"'{k}': {v}" for k, v in st["options"].items())
        if st.get("not_offered"):
            desc += " Not offered — " + "; ".join(f"{k}: {v}" for k, v in st["not_offered"].items())
        out[key] = {"label": st["label"], "description": desc + " Not stated: Template 1 columns i-k are a gap and "
                    "the filing is blocked.", "allowed": list(st["options"])}
    return out


def narrative_items() -> list[dict]:
    return reference()["narrative"]


def required_narrative(estimation: str | None) -> list[dict]:
    """The narrative items the instructions require for the institution's statement (none until it is stated)."""
    return [n for n in narrative_items() if estimation in n["required_when"]]


def record(session, org_id: str) -> dict:
    """What a filing freezes: the two statements as stated now, and the authored narrative (template answers)."""
    from services.calc_settings import get_calc_settings
    from services.governance import pillar3_qualitative as Q
    s = get_calc_settings(session, org_id)
    answers = Q.read(session, org_id)
    return {"estimation": s.get(ESTIMATION), "attribution": s.get(ATTRIBUTION),
            "narrative": {n["key"]: answers[n["key"]] for n in narrative_items() if answers.get(n["key"])}}


def factor(a: dict) -> float | None:
    """The exposure compared to the counterparty's total liabilities (accounting liabilities and shareholders' equity) —
    None when the latter is not stated."""
    from services.governance.pillar3_grids import gross_of
    den = a.get("counterparty_total_liabilities_eur")
    if den in (None, "") or float(den) <= 0:
        return None
    return gross_of(a) / float(den)


def gaps(rec: dict | None) -> list[str]:
    """Why columns i-k cannot be printed as the institution's own method: each a named gap ([] when none)."""
    if rec is None:
        return []
    out = []
    est, att = rec.get("estimation"), rec.get("attribution")
    if est is None:
        out.append(f"not stated: which counterparty emissions the institution estimates (methodology — {ESTIMATION})")
    elif est in ESTIMATING and att is None:
        out.append(f"not stated: how counterparty emissions are attributed to the exposure (methodology — {ATTRIBUTION})")
    return out


def missing_narrative(rec: dict | None) -> list[dict]:
    """The required narrative items not authored when the filing was frozen."""
    if rec is None:
        return []
    have = rec.get("narrative") or {}
    return [n for n in required_narrative(rec.get("estimation")) if not (have.get(n["key"]) or "").strip()]


def describe(rec: dict | None) -> str:
    """The method note under Template 1, from what the filing froze."""
    if rec is None:
        return ("Method (frozen before the institution's statements were recorded): columns i and j are the "
                "counterparties' reported emissions, not attributed to the exposure; k the share of the row's gross "
                "carrying amount whose emissions the company reported itself.")
    g = gaps(rec)
    if g:
        return "Columns i-k not computed — " + "; ".join(g) + "."
    est = rec["estimation"]
    if est == "not_yet_estimating":
        return ("The institution states it is not yet estimating its counterparties' emissions: columns i, j and k are "
                "blank; its plans are in the narrative. " + quote("i_plans"))
    st = reference()["statements"]
    parts = [f"The institution estimates {st[ESTIMATION]['options'][est]}",
             f"Attribution: {st[ATTRIBUTION]['options'][rec['attribution']]} {quote('i_proportion')}"]
    if est == "scope_1_2":
        parts.append(quote("j_blank"))
    parts.append("Column k: " + quote("k_what") + " — read from each exposure's record of its emissions' source "
                 "(reported by the company or not).")
    return " ".join(parts)


def narrative_lines(rec: dict | None) -> list[str]:
    """The frozen narrative accompanying the template, item by item."""
    if not rec:
        return []
    have = rec.get("narrative") or {}
    return [f"{n['prompt']}: {have[n['key']]}" for n in narrative_items() if have.get(n["key"])]
