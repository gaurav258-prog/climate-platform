"""The checks of a due diligence statement (E107), on the frozen statement only (services.eudr.statement.compute), so
they reproduce. Each rule names its article of Regulation (EU) 2023/1115 as in force (consolidated 18.9.2026); a choice
the text leaves to the operator is the operator's statement, never a platform default. Severity: 'blocking' — the
statement cannot be filed; 'warning' — shown, the operator decides; 'info'.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

GENERAL_APPLICATION = date(2026, 12, 30)      # Art. 38(2): 'shall apply from 30 December 2026'
SMALL_APPLICATION = date(2027, 6, 30)         # Art. 38(3): '30 June 2027' — micro / small established by 31.12.2024
SMALL_ESTABLISHED_BY = date(2024, 12, 31)
FILERS = ("operator",)                        # Art. 4(2): operators submit a DDS; Art. 4a: micro/small primary operators a
                                              # simplified declaration; Art. 5: downstream operators and traders none


def _f(rule: str, severity: str, passed: bool, message: str, ref: Optional[str] = None) -> dict:
    return {"rule": rule, "category": "eudr", "severity": severity, "passed": bool(passed), "message": message, "ref": ref}


def _application(st: dict) -> dict:
    """Whether Arts. 3-13 apply on the movement's date (Art. 38)."""
    on = date.fromisoformat(st["movement"]["planned_on"])
    status = st.get("operator_status") or {}
    if on < GENERAL_APPLICATION:
        return _f("application", "info", True, f"on {on} the obligations do not apply yet (from {GENERAL_APPLICATION})", "Art. 38(2)")
    small = status.get("size_class") in ("micro", "small")
    est = status.get("established_on")
    if small and on < SMALL_APPLICATION:
        if est is None:
            return _f("application", "warning", False, "a micro or small undertaking: whether it was established as such by "
                      f"{SMALL_ESTABLISHED_BY} is not stated — that decides whether the obligations apply before {SMALL_APPLICATION}",
                      "Art. 38(3)")
        if date.fromisoformat(est) <= SMALL_ESTABLISHED_BY:
            wood = ((st.get("scope") or {}).get("entry") or {}).get("commodity") == "wood"
            if wood:
                return _f("application", "warning", False, "wood: the later date does not apply to 'products covered by the "
                          "Annex to Regulation (EU) No 995/2010' — whether this product is one is not determined here",
                          "Art. 38(3)")
            return _f("application", "info", True, f"micro / small, established by {SMALL_ESTABLISHED_BY}: the obligations "
                      f"apply from {SMALL_APPLICATION}", "Art. 38(3)")
    return _f("application", "info", True, f"the obligations apply on {on}", "Art. 38")


def checks(st: dict) -> list[dict]:
    out: list[dict] = []
    mv, status, a2 = st["movement"], st.get("operator_status"), st["annex_ii"]
    app = _application(st)
    out.append(app)

    # who files: an operator submits a due diligence statement (Art. 4(2))
    if mv["actor_role"] not in FILERS:
        out.append(_f("filer", "blocking", False, {"micro_small_primary_operator": "a micro or small primary operator submits a "
                      "one-time simplified declaration (Annex III), not a due diligence statement",
                      "downstream_operator": "a downstream operator submits no due diligence statement — it keeps its "
                      "suppliers' reference numbers and the records of Art. 5(3)",
                      "trader": "a trader submits no due diligence statement — it keeps the records of Art. 5(3)"}[mv["actor_role"]],
                      "Art. 4(2), 4a, 5"))

    # scope (Annex I on the date): True / False / open — an open one is the operator's statement
    sc = st.get("scope") or {}
    if sc.get("in_scope") is False:
        out.append(_f("scope", "blocking", False, f"not a relevant product on {mv['planned_on']}: {sc.get('why')}", "Art. 2(2), Annex I"))
    elif sc.get("in_scope") is None:
        stated = mv.get("scope_in")
        if stated is None:
            out.append(_f("scope", "blocking", False, f"Annex I leaves this product's scope open ({sc.get('why')}) — state "
                          "whether it is in scope, and why", "Annex I"))
        elif stated is False:
            out.append(_f("scope", "blocking", False, f"stated out of scope: {mv.get('scope_basis')}", "Annex I"))
        else:
            out.append(_f("scope", "info", True, f"stated in scope: {mv.get('scope_basis')}", "Annex I"))

    # Annex II point 1: name, address and, entering or leaving the market, the EORI number
    if status is None:
        out.append(_f("annex_ii_1", "blocking", False, "state the undertaking's EUDR status (size, country, address) for "
                      "the movement's date", "Annex II point 1"))
    else:
        if not a2["1"].get("address"):
            out.append(_f("annex_ii_1", "blocking", False, "the operator's address is not stated", "Annex II point 1"))
        if mv["customs_flow"] and not a2["1"].get("eori"):
            out.append(_f("annex_ii_1_eori", "blocking", False, "goods entering or leaving the market: the EORI number is "
                          "required", "Annex II point 1"))

    # Annex II point 2: HS code, description, scientific names (where applicable), quantity
    q = a2["2"]["quantity"]
    commodity = ((sc.get("entry") or {}).get("commodity"))
    if commodity == "wood" and not a2["2"]["scientific_names"]:
        out.append(_f("annex_ii_2_species", "blocking", False, "wood: the full scientific names of the species are required",
                      "Annex II point 2; Art. 9(1)(a)"))
    if not mv["customs_flow"] and q.get("net_mass_kg") is not None and q.get("mass_deviation_pct") is None:
        out.append(_f("annex_ii_2_quantity", "blocking", False, "outside customs, net mass is stated 'specifying a percentage "
                      "estimate or deviation'", "Annex II point 2"))

    # Annex II point 3 / Art. 2(28): country and the geolocation of all plots
    plots = st["plots"]
    if not plots:
        out.append(_f("annex_ii_3", "blocking", False, "no plot of land is linked to the movement", "Annex II point 3"))
    for p in plots:
        name = p["plot_name"] or p["plot_id"]
        if not p["country"]:
            out.append(_f(f"country:{p['plot_id']}", "blocking", False, f"{name}: country of production not stated", "Annex II point 3"))
        if p["coordinate_decimals"] is None:
            out.append(_f(f"decimals:{p['plot_id']}", "blocking", False, f"{name}: how many decimals its coordinates were "
                          "given with is not known — send them again (at least six)", "Art. 2(28)"))
        elif p["coordinate_decimals"] < 6:
            out.append(_f(f"decimals:{p['plot_id']}", "blocking", False, f"{name}: coordinates given with "
                          f"{p['coordinate_decimals']} decimals — at least six", "Art. 2(28)"))
        if p["polygon_required"] and not p["has_polygon"]:
            out.append(_f(f"polygon:{p['plot_id']}", "blocking", False, f"{name}: more than four hectares — its perimeter "
                          "is given as a polygon", "Art. 2(28)"))
        if p["area_unknown"]:
            out.append(_f(f"area:{p['plot_id']}", "blocking", False, f"{name}: area not stated and no polygon — whether a "
                          "polygon is required cannot be known", "Art. 2(28)"))
        r = p.get("reading")
        if r is None:
            out.append(_f(f"reading:{p['plot_id']}", "warning", False, f"{name}: no satellite reading of its current "
                          "geometry — the deforestation-free information must come from elsewhere", "Art. 9(1)(g)"))
        elif r["outcome"] == "loss_after_cutoff":
            out.append(_f(f"reading:{p['plot_id']}", "warning", False, f"{name}: tree-cover loss after 31 December 2020 in "
                          f"the reading ({r['loss_ha']} ha, first {r['first_loss_year']}) — a risk the assessment weighs",
                          "Art. 2(13), 10(2)(f)"))
        elif r["outcome"] == "not_assessable":
            out.append(_f(f"reading:{p['plot_id']}", "warning", False, f"{name}: not assessable — {r['reason']}", "Art. 9(1)(g)"))

    # Art. 9(1)(e)-(f): supplier and customer
    a9 = st["art9"]
    sup = a9.get("supplier")
    if not sup or not all(sup.get(k) for k in ("name", "address", "email")):
        out.append(_f("supplier", "blocking", False, "the supplier's name, postal address and email are required", "Art. 9(1)(e)"))
    if not a9.get("customer"):
        out.append(_f("customer", "warning", False, "no customer on the movement — record it once supplied", "Art. 9(1)(f)"))

    # Art. 9(1)(h): legality evidence
    if not st["legality_evidence"]:
        out.append(_f("legality", "blocking", False, "no legality evidence for the plots, the supplier or the movement",
                      "Art. 3(b), 9(1)(h), 2(40)"))

    # Art. 10-13: the operator's assessment — no placing unless no or only a negligible risk
    ra = st.get("risk_assessment")
    if ra is None:
        out.append(_f("risk_assessment", "blocking", False, "no risk assessment for this movement", "Art. 10(1)"))
    else:
        if ra["conclusion"] != "negligible":
            out.append(_f("risk_assessment", "blocking", False, "the assessment does not conclude 'no or only a negligible "
                          "risk' — Art. 11 mitigation first", "Art. 10(1), 11"))
        if ra["path"] == "simplified" and any(r != "low" for r in st["countries"].values()):
            out.append(_f("simplified", "blocking", False, "the simplified path rests on every country of production being "
                          f"low risk — now: {st['countries']}", "Art. 13(1)"))
        recorded = date.fromisoformat(ra["recorded_at"][:10])
        if (date.fromisoformat(mv["planned_on"]) - recorded).days > 366:
            out.append(_f("risk_review", "warning", False, f"the assessment dates from {recorded}: reviewed at least annually",
                          "Art. 10(4)"))
    # Art. 4(5): relevant new information or a substantiated concern — the authorities are informed at once
    from services.eudr.trade import concern_checks
    out += concern_checks({"movement": {"actor_role": mv["actor_role"], "on": mv["planned_on"]},
                           "concerns": st.get("concerns") or []}, False, severity="warning")
    if not any(not f["passed"] and f["severity"] == "blocking" for f in out):
        out.append(_f("ready", "info", True, "every blocking check passes"))
    return out
