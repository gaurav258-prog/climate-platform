"""The checks of a due diligence statement (E107), on the frozen statement only (services.eudr.statement.compute), so
they reproduce. Each rule names its article of Regulation (EU) 2023/1115 as in force (consolidated 18.9.2026); a choice
the text leaves to the operator is the operator's statement, never a platform default. Severity: 'blocking' — the
statement cannot be filed; 'warning' — shown, the operator decides; 'info'. Each check is a catalogue message
(services/eudr/words.finding, codes eudr.check.*): its label for the screen, its explanation and legal basis one click
away; category is its family on the filings checklist (scope, completeness, plausibility).
"""
from __future__ import annotations

from datetime import date

from services.eudr.words import finding as _f
from services.eudr.words import hectares, name, reading_msg, scope_msg

GENERAL_APPLICATION = date(2026, 12, 30)      # Art. 38(2): 'shall apply from 30 December 2026'
SMALL_APPLICATION = date(2027, 6, 30)         # Art. 38(3): '30 June 2027' — micro / small established by 31.12.2024
SMALL_ESTABLISHED_BY = date(2024, 12, 31)
FILERS = ("operator",)                        # Art. 4(2): operators submit a DDS; Art. 4a: micro/small primary operators a
                                              # simplified declaration; Art. 5: downstream operators and traders none


def _application(st: dict) -> dict:
    """Whether Arts. 3-13 apply on the movement's date (Art. 38)."""
    on = date.fromisoformat(st["movement"]["planned_on"])
    status = st.get("operator_status") or {}
    if on < GENERAL_APPLICATION:
        return _f("application", "scope", "info", True, "eudr.check.application.not_yet", "Art. 38(2)",
                  on=on.isoformat(), start=GENERAL_APPLICATION.isoformat())
    small = status.get("size_class") in ("micro", "small")
    est = status.get("established_on")
    if small and on < SMALL_APPLICATION:
        if est is None:
            return _f("application", "scope", "warning", False, "eudr.check.application.established_unknown", "Art. 38(3)",
                      by=SMALL_ESTABLISHED_BY.isoformat(), start=SMALL_APPLICATION.isoformat())
        if date.fromisoformat(est) <= SMALL_ESTABLISHED_BY:
            wood = ((st.get("scope") or {}).get("entry") or {}).get("commodity") == "wood"
            if wood:
                return _f("application", "scope", "warning", False, "eudr.check.application.wood", "Art. 38(3)")
            return _f("application", "scope", "info", True, "eudr.check.application.small_later", "Art. 38(3)",
                      by=SMALL_ESTABLISHED_BY.isoformat(), start=SMALL_APPLICATION.isoformat())
    return _f("application", "scope", "info", True, "eudr.check.application.applies", "Art. 38", on=on.isoformat())


def checks(st: dict) -> list[dict]:
    out: list[dict] = []
    mv, status, a2 = st["movement"], st.get("operator_status"), st["annex_ii"]
    app = _application(st)
    out.append(app)

    # who files: an operator submits a due diligence statement (Art. 4(2))
    if mv["actor_role"] not in FILERS:
        out.append(_f("filer", "scope", "blocking", False, f"eudr.check.filer.{mv['actor_role']}", "Art. 4(2), 4a, 5"))

    # scope (Annex I on the date): True / False / open — an open one is the operator's statement
    sc = st.get("scope") or {}
    basis = scope_msg(sc, a2["2"]["hs_code"])["detail"]["what"] if sc else ""
    if sc.get("in_scope") is False:
        out.append(_f("scope", "scope", "blocking", False, "eudr.check.scope.out", "Art. 2(2), Annex I",
                      on=mv["planned_on"], basis=basis))
    elif sc.get("in_scope") is None:
        stated = mv.get("scope_in")
        if stated is None:
            out.append(_f("scope", "scope", "blocking", False, "eudr.check.scope.open", "Annex I", basis=basis))
        elif stated is False:
            out.append(_f("scope", "scope", "blocking", False, "eudr.check.scope.stated_out", "Annex I",
                          stated=mv.get("scope_basis") or ""))
        else:
            out.append(_f("scope", "scope", "info", True, "eudr.check.scope.stated_in", "Annex I",
                          stated=mv.get("scope_basis") or ""))

    # Annex II point 1: name, address and, entering or leaving the market, the EORI number
    if status is None:
        out.append(_f("annex_ii_1", "completeness", "blocking", False, "eudr.check.status.missing", "Annex II point 1"))
    else:
        if not a2["1"].get("address"):
            out.append(_f("annex_ii_1", "completeness", "blocking", False, "eudr.check.operator.address", "Annex II point 1"))
        if mv["customs_flow"] and not a2["1"].get("eori"):
            out.append(_f("annex_ii_1_eori", "completeness", "blocking", False, "eudr.check.operator.eori", "Annex II point 1"))

    # Annex II point 2: HS code, description, scientific names (where applicable), quantity
    q = a2["2"]["quantity"]
    commodity = ((sc.get("entry") or {}).get("commodity"))
    if commodity == "wood" and not a2["2"]["scientific_names"]:
        out.append(_f("annex_ii_2_species", "completeness", "blocking", False, "eudr.check.product.species",
                      "Annex II point 2; Art. 9(1)(a)"))
    if not mv["customs_flow"] and q.get("net_mass_kg") is not None and q.get("mass_deviation_pct") is None:
        out.append(_f("annex_ii_2_quantity", "completeness", "blocking", False, "eudr.check.product.deviation",
                      "Annex II point 2"))

    # Annex II point 3 / Art. 2(28): country and the geolocation of all plots
    plots = st["plots"]
    if not plots:
        out.append(_f("annex_ii_3", "completeness", "blocking", False, "eudr.check.plots.none", "Annex II point 3"))
    for p in plots:
        plot = p["plot_name"] or p.get("external_ref") or "A plot"
        if not p["country"]:
            out.append(_f(f"country:{p['plot_id']}", "completeness", "blocking", False, "eudr.check.plot.country",
                          "Annex II point 3", plot=plot))
        if p["coordinate_decimals"] is None:
            out.append(_f(f"decimals:{p['plot_id']}", "completeness", "blocking", False, "eudr.check.plot.decimals_unknown",
                          "Art. 2(28)", plot=plot))
        elif p["coordinate_decimals"] < 6:
            out.append(_f(f"decimals:{p['plot_id']}", "completeness", "blocking", False, "eudr.check.plot.decimals_low",
                          "Art. 2(28)", plot=plot, n=p["coordinate_decimals"]))
        if p["polygon_required"] and not p["has_polygon"]:
            out.append(_f(f"polygon:{p['plot_id']}", "completeness", "blocking", False, "eudr.check.plot.polygon",
                          "Art. 2(28)", plot=plot))
        if p["area_unknown"]:
            out.append(_f(f"area:{p['plot_id']}", "completeness", "blocking", False, "eudr.check.plot.area_unknown",
                          "Art. 2(28)", plot=plot))
        r = p.get("reading")
        if r is None:
            out.append(_f(f"reading:{p['plot_id']}", "plausibility", "warning", False, "eudr.check.plot.unread",
                          "Art. 9(1)(g)", plot=plot))
        elif r["outcome"] == "loss_after_cutoff":
            out.append(_f(f"reading:{p['plot_id']}", "plausibility", "warning", False, "eudr.check.plot.loss",
                          "Art. 2(13), 10(2)(f)", plot=plot, loss_ha=hectares(r["loss_ha"]), year=r["first_loss_year"]))
        elif r["outcome"] == "not_assessable":
            out.append(_f(f"reading:{p['plot_id']}", "plausibility", "warning", False, "eudr.check.plot.not_assessable",
                          "Art. 9(1)(g)", plot=plot, reason=reading_msg(r)["detail"]["what"]))

    # Art. 9(1)(e)-(f): supplier and customer
    a9 = st["art9"]
    sup = a9.get("supplier")
    if not sup or not all(sup.get(k) for k in ("name", "address", "email")):
        out.append(_f("supplier", "completeness", "blocking", False, "eudr.check.supplier.incomplete", "Art. 9(1)(e)"))
    if not a9.get("customer"):
        out.append(_f("customer", "completeness", "warning", False, "eudr.check.customer.none", "Art. 9(1)(f)"))

    # Art. 9(1)(h): legality evidence
    if not st["legality_evidence"]:
        out.append(_f("legality", "completeness", "blocking", False, "eudr.check.legality.none", "Art. 3(b), 9(1)(h), 2(40)"))

    # Art. 10-13: the operator's assessment — no placing unless no or only a negligible risk
    ra = st.get("risk_assessment")
    if ra is None:
        out.append(_f("risk_assessment", "completeness", "blocking", False, "eudr.check.risk.none", "Art. 10(1)"))
    else:
        if ra["conclusion"] != "negligible":
            out.append(_f("risk_assessment", "completeness", "blocking", False, "eudr.check.risk.not_negligible",
                          "Art. 10(1), 11"))
        if ra["path"] == "simplified" and any(r != "low" for r in st["countries"].values()):
            not_low = ", ".join(f"{c} ({name('country_risk', r) if r else '—'})" for c, r in sorted(st["countries"].items())
                                if r != "low")
            out.append(_f("simplified", "scope", "blocking", False, "eudr.check.risk.simplified_countries", "Art. 13(1)",
                          countries=not_low))
        recorded = date.fromisoformat(ra["recorded_at"][:10])
        if (date.fromisoformat(mv["planned_on"]) - recorded).days > 366:
            out.append(_f("risk_review", "plausibility", "warning", False, "eudr.check.risk.review", "Art. 10(4)",
                          since=recorded.isoformat()))
    # Art. 4(5): relevant new information or a substantiated concern — the authorities are informed at once
    from services.eudr.trade import concern_checks
    out += concern_checks({"movement": {"actor_role": mv["actor_role"], "on": mv["planned_on"]},
                           "concerns": st.get("concerns") or []}, False, severity="warning")
    if not any(not f["passed"] and f["severity"] == "blocking" for f in out):
        out.append(_f("ready", "completeness", "info", True, "eudr.check.ready"))
    return out
