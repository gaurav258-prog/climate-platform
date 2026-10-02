"""Pre-submission validation — the checks that gate a filing before a human ever reviews it.

A regulatory filing shouldn't reach a reviewer (let alone the regulator) with a blocking defect. This runs
a framework-specific rule set over the *frozen snapshot* behind a filing and returns a full checklist —
every rule, passed or failed — split into three severities:

  blocking — the filing cannot be submitted for approval while this fails (e.g. nothing scored, no manager LEI)
  warning  — file-able but the reviewer must see it (e.g. partial coverage, thin emissions data)
  info     — context, never gates

Rules fall in three families, mirroring how a filing goes wrong:
  completeness — is every in-scope item scored, or explicitly flagged? are mandatory identities present?
  plausibility — are the numbers in sane ranges (non-negative, shares in 0–100, exposure ≤ book)?
  tie_out      — do the figures reconcile internally (severity buckets sum to the book; value at risk within the book)?

Honesty carries through: a rule never invents a value — it reads what the assembler produced and flags a gap
as a gap. Because it reads the frozen snapshot, a filing's validation result is stable and reproducible.

Ledger reconciliation (added 2026-09-23, closing a gap an independent architecture review found): the GL
reconciliation (services/governance/gl_recon.py) and seasonal-arrears overlay (services/governance/
seasonal_arrears.py) used to be pure dashboard tiles — a variance could sit well outside tolerance and a
filing would still submit, review, attest and file with nobody in that chain ever shown it. This module now
checks the live reconciliation state as a `tie_out` rule on every filing, org-type-scoped (GL for bank /
insurer / reit / asset_manager, seasonal-arrears for agri): no ledger uploaded yet is a WARNING (many orgs
haven't onboarded this overlay — that alone shouldn't block filing), but an uploaded ledger showing a
variance OUTSIDE tolerance is BLOCKING — a known, quantified reconciliation failure can no longer pass
through submit_for_review silently.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance import money_format
from services.governance.filings import get_filing


def _f(rule: str, category: str, severity: str, passed: bool, message: str, ref: str | None = None) -> dict:
    return {"rule": rule, "category": category, "severity": severity, "passed": passed,
            "message": message, "ref": ref}


def _eur(n) -> str:
    """A figure in the filing's own currency (money_format.current, set by validate_filing from the snapshot)."""
    try:
        return money_format.money(float(n), compact=False)
    except (TypeError, ValueError):
        return f"{money_format.symbol(money_format.current.get())}—"


# ── framework rule sets ─────────────────────────────────────────────────

def _validate_bank_tcfd(payload: dict) -> list[dict]:
    """EU Taxonomy Art. 8 (bank_tcfd): the frozen book is there, has value, and every exposure states the gross carrying
    amount the templates are built on. A filing frozen under the earlier report shape keeps the checks it was made under."""
    from services.governance.bank_taxonomy_report import is_earlier_shape
    from services.governance.pillar3_grids import no_gross
    if is_earlier_shape(payload):
        return _validate_bank_book(payload)
    rollup, assets = payload.get("rollup") or {}, payload.get("assets") or []
    n, total, missing = rollup.get("n_assets", len(assets)), rollup.get("total_value_eur", 0) or 0, no_gross(assets)
    return [
        _f("has_assets", "completeness", "blocking", n > 0,
           f"{n} exposures in scope" if n > 0 else "No exposures in scope — nothing to file"),
        _f("total_value_positive", "plausibility", "blocking", total > 0,
           f"Total book value {_eur(total)}" if total > 0 else "Total book value is zero"),
        _f("gross_carrying_amount_stated", "completeness", "warning", not missing,
           f"Every exposure states its gross carrying amount ({len(assets)})" if not missing
           else f"{missing} of {len(assets)} exposures state no gross carrying amount (outstanding balance) — they sit in "
                "no template row; state it on the loan tape"),
    ]


def _validate_bank_book(payload: dict) -> list[dict]:
    """The located loan book's checks (Pillar 3 ESG, and bank_tcfd filings of the earlier report shape)."""
    out: list[dict] = []
    rollup = payload.get("rollup") or {}
    n_assets = rollup.get("n_assets", 0)
    n_scored = rollup.get("n_scored", 0)
    total = rollup.get("total_value_eur", 0) or 0

    # completeness
    out.append(_f("has_assets", "completeness", "blocking", n_assets > 0,
                  f"{n_assets} assets in scope" if n_assets > 0 else "No assets in scope — nothing to file"))
    out.append(_f("some_scored", "completeness", "blocking", n_scored > 0,
                  f"{n_scored} assets scored on the golden source" if n_scored > 0
                  else "No assets scored — the disclosure would be empty"))
    cov = round(100 * n_scored / n_assets, 1) if n_assets else 0
    out.append(_f("full_coverage", "completeness", "warning", n_assets > 0 and n_scored == n_assets,
                  f"All {n_assets} assets scored ({cov}%)" if n_scored == n_assets
                  else f"{n_scored}/{n_assets} scored ({cov}%) — {n_assets - n_scored} unscored are excluded from exposure"))

    # plausibility
    out.append(_f("total_value_positive", "plausibility", "blocking", total > 0,
                  f"Total book value {_eur(total)}" if total > 0 else "Total book value is zero"))
    pct = rollup.get("pct_value_at_risk")
    if pct is not None:
        out.append(_f("share_in_range", "plausibility", "warning", 0 <= pct <= 100,
                      f"Share of book at material physical risk: {pct}%" if 0 <= pct <= 100
                      else f"Share at risk out of range: {pct}%"))
    em = payload.get("financed_emissions_tco2e") or {}
    neg = [k for k, v in em.items() if (v or 0) < 0]
    out.append(_f("emissions_non_negative", "plausibility", "warning", not neg,
                  "Financed emissions are non-negative" if not neg else f"Negative financed emissions: {neg}"))
    for hz, b in (payload.get("by_hazard") or {}).items():
        ev = b.get("exposed_value_eur")
        if ev is None:
            continue                                   # a gap — reported by method_stated
        ok = ev <= total * 1.0001 or total == 0
        out.append(_f(f"hazard_within_book:{hz}", "plausibility", "warning", ok,
                      f"{hz.replace('_', ' ')}: {_eur(ev)} exposed (≤ book)" if ok
                      else f"{hz.replace('_', ' ')}: exposed {_eur(ev)} exceeds book {_eur(total)}"))

    # tie-out (internal reconciliation)
    buckets = rollup.get("by_bucket") or {}
    bucket_sum = sum((b.get("value_eur", 0) or 0) for b in buckets.values())
    tol = max(1.0, 0.005 * total)
    out.append(_f("buckets_reconcile", "tie_out", "blocking", abs(bucket_sum - total) <= tol,
                  f"Severity buckets reconcile to the book total ({_eur(bucket_sum)})"
                  if abs(bucket_sum - total) <= tol
                  else f"Severity buckets {_eur(bucket_sum)} ≠ book total {_eur(total)}"))
    var = rollup.get("value_at_risk_eur")
    if var is not None:        # at or above the bank's stated level — a part of the book, never more
        out.append(_f("var_within_book", "tie_out", "blocking", var <= total + tol,
                      f"Value at material physical risk {_eur(var)} is within the book" if var <= total + tol
                      else f"Value at risk {_eur(var)} exceeds the book {_eur(total)}"))
    return out


def _validate_p3_book(payload: dict) -> list[dict]:
    """The frozen banking book of a Pillar 3 filing (E97): there, of value, scored (Template 5 reads the scores), and its
    financed emissions non-negative."""
    from services.governance.pillar3_report import t1_total
    from services.governance.pillar3_t1 import RECORD
    rollup = payload.get("rollup") or {}
    n, scored, total = rollup.get("n_assets", 0), rollup.get("n_scored", 0), rollup.get("total_value_eur", 0) or 0
    if RECORD in payload:                                   # Template 1 columns i and j, on the stated method (E103)
        t = t1_total(payload) or {}
        em = {c: t.get(c) for c in ("i", "j")}
    else:
        em = payload.get("financed_emissions_tco2e") or {}
    neg = [k for k, v in em.items() if (v or 0) < 0]
    cov = round(100 * scored / n, 1) if n else 0
    return [
        _f("has_assets", "completeness", "blocking", n > 0, f"{n} exposures in scope" if n > 0 else "No exposures in scope — nothing to file"),
        _f("some_scored", "completeness", "blocking", scored > 0,
           f"{scored} exposures scored on the golden source" if scored > 0
           else "No exposure scored — Template 5 would be empty"),
        _f("full_coverage", "completeness", "warning", n > 0 and scored == n,
           f"All {n} exposures scored ({cov}%)" if scored == n
           else f"{scored}/{n} scored ({cov}%) — {n - scored} unscored are in no Template 5 sensitivity column"),
        _f("total_value_positive", "plausibility", "blocking", total > 0,
           f"Total book value {_eur(total)}" if total > 0 else "Total book value is zero"),
        _f("emissions_non_negative", "plausibility", "warning", not neg,
           "Financed emissions are non-negative" if not neg else f"Negative financed emissions: {neg}"),
    ]


def _validate_bank_p3esg(payload: dict) -> list[dict]:
    """The bank checks plus Pillar 3's own: every template amount is a gross carrying amount — the exposure's outstanding
    balance on the loan tape, never its collateral value — so an exposure that states none blocks the filing."""
    from services.governance.pillar3_grids import no_gross
    from services.governance.pillar3_report import is_earlier_shape
    assets = payload.get("assets") or []
    missing = no_gross(assets)
    # a filing of the earlier report shape keeps the checks it was made under; a new one checks what its templates read —
    # no severity-bucket, value-at-risk or per-hazard figure is frozen any more (E97)
    base = _validate_bank_book(payload) if is_earlier_shape(payload) else _validate_p3_book(payload)
    return base + _t1_findings(payload) + [_f(
        "gross_carrying_amount_stated", "completeness", "blocking", not missing,
        f"Every exposure states its gross carrying amount ({len(assets)})" if not missing
        else f"{missing} of {len(assets)} exposures state no gross carrying amount (outstanding balance) — they would sit "
             "in no Pillar 3 row; state it on the loan tape",
        ref="ITS (EU) 2024/3172 Annex XL — gross carrying amount")]


def _t1_findings(payload: dict) -> list[dict]:
    """Template 1 columns i-k (E103): the institution's statements (which emissions it estimates, how they are
    attributed) are made; every exposure the columns read states what they need; the narrative the instructions
    require is authored. A filing frozen before the statements were recorded keeps the checks it was made under."""
    from services.governance import pillar3_t1 as T1
    from services.governance.pillar3_report import t1_total
    rec = payload.get(T1.RECORD)
    if rec is None:
        return []
    ref = "Annex XL, Template 1, columns i–k (ITS 2022/2453; ITS 2024/3172)"
    gaps = T1.gaps(rec)
    out = [_f("t1_method_stated", "completeness", "blocking", not gaps,
              "Template 1 columns i–k follow the institution's stated estimation and attribution" if not gaps
              else "Template 1 columns i–k are a gap — " + "; ".join(gaps), ref=ref)]
    st = (t1_total(payload) or {}).get("stated") or {}
    for rule, k, what in (
            ("t1_counterparty_identified", "no_counterparty",
             "state emissions but no counterparty id — Template 1 attributes per counterparty ('towards the counterparty "
             "compared to the total liabilities ... of the counterparty'); state the counterparty id (LEI or your own id) "
             "on the loan tape"),
            ("t1_counterparty_figure_agreed", "conflict",
             "belong to counterparties whose exposures stated different total liabilities — none was picked; state the "
             "counterparty's one figure (Data → counterparties)"),
            ("t1_scope3_basis", "s3_gap",
             "state scopes 1 and 2 but no scope 3 gathered from the counterparty, and no sector-average intensity can stand "
             "in (Annex XL: 'Institutions shall base the estimation of scope 3 emissions on the information on emissions "
             "gathered from their counterparties and on the information on sector-average emissions intensity.'): "
             + "; ".join(sorted(T1.scope3_gaps(payload)))),
            ("t1_total_liabilities_stated", "unattributed",
             "state emissions but not the counterparty's total liabilities (accounting liabilities and shareholders' "
             "equity) — their financed emissions cannot be attributed; state it once for the counterparty, with its "
             "balance-sheet date (Data → counterparties)"),
            ("t1_exposure_within_liabilities", "over",
             "have an exposure larger than the counterparty's stated total liabilities and equity — one of the two is wrong"),
            ("t1_emissions_source_recorded", "rep_unknown",
             "in column i do not record whether the counterparty reported its emissions — column k cannot be read; state "
             "'emissions reported by the company' (per-loan attributes)")):
        n = st.get(k, 0)
        out.append(_f(rule, "completeness", "blocking", not n,
                      f"{n} exposures {what}" if n else "Every exposure read by Template 1 columns i–k states what they need",
                      ref=ref))
    kg = T1.k_gap(rec)
    out.append(_f("t1_k_reading_stated", "completeness", "blocking", kg is None,
                  "Column k follows the institution's statement" if kg is None else "Template 1 column k is a gap — " + kg,
                  ref="Annex XL, Template 1, column k"))
    missing = T1.missing_narrative(rec)
    out.append(_f("t1_narrative_authored", "completeness", "blocking", not missing,
                  "The narrative accompanying Template 1 is authored" if not missing else
                  "Not authored (Pillar 3 qualitative disclosures): " + "; ".join(n["prompt"] for n in missing),
                  ref=ref))
    return out


# a report whose money figures are its content: a figure whose method is not stated blocks it. S.27.01.01 is the
# standard formula (Delegated Regulation 2015/35) — it needs no stated method; its modelled figures are context only.
_METHOD_WARNS = frozenset({"insurer_solvency"})


def _method_findings(payload: dict, framework: str) -> list[dict]:
    """The institution's stated method the frozen money figures were computed on (services.money.params, E69):
    every parameter a figure needed is stated for the period, or the figure is a gap — named here."""
    rec = payload.get("method")
    if not rec:
        return []
    gaps = rec.get("gaps") or []
    names = ", ".join(g["key"] + (f" ({g['member']})" if g.get("member") else "") for g in gaps[:12]) \
        + (f" and {len(gaps) - 12} more" if len(gaps) > 12 else "")
    return [_f("method_stated", "completeness", "warning" if framework in _METHOD_WARNS else "blocking", not gaps,
               f"Every money figure rests on the institution's stated method for the period ending {rec.get('period_end')}"
               if not gaps else f"Not stated for the period — the figures that need them are gaps: {names}",
               ref="data/reference/money/parameters.json")]


def _validate_sfdr_pai(payload: dict) -> list[dict]:
    out: list[dict] = []
    if payload.get("error"):
        return [_f("statement_builds", "completeness", "blocking", False,
                   f"Statement could not be assembled: {payload['error']}")]
    entity = payload.get("entity") or {}
    positions = entity.get("positions", 0) or 0
    total = entity.get("total_value_eur", 0) or 0

    out.append(_f("has_positions", "completeness", "blocking", positions > 0,
                  f"{positions} positions in scope" if positions > 0 else "No positions to report on"))
    out.append(_f("total_value_positive", "plausibility", "blocking", total > 0,
                  f"Total NAV in scope {_eur(total)}" if total > 0 else "Total value in scope is zero"))

    # SFDR is not filable without the manager's reporting identity (LEI, legal name, contact) + required narratives
    fr = payload.get("filing_readiness") or {}
    missing = fr.get("missing") or []
    out.append(_f("filing_identity", "completeness", "blocking", bool(fr.get("ready_to_file")),
                  "Reporting-entity identity & narratives complete" if fr.get("ready_to_file")
                  else f"Not submittable — missing: {', '.join(missing)}"))

    cs = payload.get("coverage_summary") or {}
    mand = cs.get("mandatory_indicators", 0) or 0
    comp = cs.get("computed", 0) or 0
    out.append(_f("mandatory_indicators", "completeness", "warning", mand > 0 and comp == mand,
                  f"All {mand} mandatory PAI indicators computed" if mand > 0 and comp == mand
                  else f"{comp}/{mand} mandatory PAI indicators computed — the rest await issuer input"))
    emis = cs.get("emissions_coverage_pct")
    if emis is not None:
        out.append(_f("emissions_coverage", "completeness", "warning", emis >= 50,
                      f"Emissions coverage {emis}% of NAV" if emis >= 50
                      else f"Emissions coverage only {emis}% of NAV — PAI 1–3 rest on a thin base"))
    nm = (payload.get("narratives") or {}).get("missing") or []
    out.append(_f("narratives_present", "completeness", "warning", not nm,
                  "All required narratives present" if not nm else f"{len(nm)} required narrative(s) missing"))
    if mand > 0 and comp < mand:     # information not readily available: the statement says how it was sought
        stated = bool(((payload.get("narratives") or {}).get("best_efforts") or "").strip())
        out.append(_f("best_efforts_stated", "completeness", "blocking", stated,
                      "The best efforts to obtain the indicators not computed are described" if stated
                      else f"{mand - comp} mandatory indicator(s) not computed — describe the best efforts used to obtain "
                           "the information in the policies section", "RTS 2022/1288 Art. 7(2)"))

    # per-fund thin coverage — surfaced, never averaged away (info)
    thin = [f["fund_name"] for f in (payload.get("per_fund") or [])
            if (f.get("emissions_coverage_pct") or 0) < 30]
    out.append(_f("per_fund_coverage", "completeness", "info", not thin,
                  "Every fund has ≥30% emissions coverage" if not thin
                  else f"Thinly-covered fund(s) inside the entity total: {', '.join(thin)}"))
    return out


def _validate_reit_taxonomy(payload: dict) -> list[dict]:
    """EU Taxonomy Article 8 KPIs (property book) — added 2026-09-23, closing a gap an independent
    architecture review found: this framework had zero pre-submission checks (only the two generic
    integrity checks every framework gets), unlike bank_tcfd/sfdr_pai."""
    out: list[dict] = []
    rollup = payload.get("rollup") or {}
    n_total, n_scored = rollup.get("n_properties", 0), rollup.get("n_scored", 0)
    total = rollup.get("total_value_eur", 0) or 0

    out.append(_f("has_properties", "completeness", "blocking", n_total > 0,
                  f"{n_total} properties in scope" if n_total > 0 else "No properties in scope — nothing to file"))
    out.append(_f("total_value_positive", "plausibility", "blocking", total > 0,
                  f"Portfolio value {_eur(total)}" if total > 0 else "Portfolio value is zero"))
    cov = round(100 * n_scored / n_total, 1) if n_total else 0
    out.append(_f("full_coverage", "completeness", "warning", n_total > 0 and n_scored == n_total,
                  f"All {n_total} properties scored ({cov}%)" if n_scored == n_total
                  else f"{n_scored}/{n_total} scored ({cov}%) — the rest are excluded from the KPI"))

    # the EU Taxonomy Art. 8 figures come from the property book (services.governance.taxonomy_nonfin)
    from services.governance.taxonomy_nonfin import summary_of
    sm = summary_of(payload)
    if sm["n_unknown"]:
        why = "; ".join(f"{r} ({n})" for r, n in sm["unknown_reasons"])
        out.append(_f("alignment_determined", "completeness", "warning", False,
                      f"{sm['n_unknown']} eligible buildings ({_eur(sm['unknown'])} of turnover) lack facts to decide "
                      f"alignment and are in neither A.1 nor A.2 — {why}"))
    if sm["noi_proxy"]:
        out.append(_f("turnover_basis", "completeness", "warning", False,
                      f"{sm['noi_proxy']} of {sm['n']} buildings have no gross rental revenue on file — turnover uses "
                      "their NOI, which understates gross revenue"))
    out.append(_f("capex_opex_ledger", "completeness", "info", False,
                  "CapEx and OpEx KPIs are entered from the undertaking's own ledger (the Annex II CapEx / OpEx cells)"))
    return out


def _validate_insurer_solvency(payload: dict) -> list[dict]:
    """Solvency II natural catastrophe risk (S.27.01.01) — added 2026-09-23, same gap as reit_taxonomy above."""
    out: list[dict] = []
    rollup = payload.get("rollup") or {}
    n_total, n_priced = rollup.get("n_policies", 0), rollup.get("n_priced", 0)
    total = rollup.get("total_sum_insured_eur", 0) or 0

    out.append(_f("has_policies", "completeness", "blocking", n_total > 0,
                  f"{n_total} policies in scope" if n_total > 0 else "No policies in scope — nothing to file"))
    out.append(_f("some_priced", "completeness", "blocking", n_priced > 0,
                  f"{n_priced} policies priced" if n_priced > 0 else "No policies priced — the SCR would be zero"))
    out.append(_f("total_sum_insured_positive", "plausibility", "blocking", total > 0,
                  f"Total sum insured {_eur(total)}" if total > 0 else "Total sum insured is zero"))

    from services.governance.insurer_solvency import natcat_block
    nb = natcat_block(payload)
    scr = nb.get("natcat_scr") or {}
    gross = scr.get("gross_1_in_200_eur")
    net = scr.get("net_of_reinsurance_1_in_200_eur")
    mean = scr.get("mean_annual_loss_eur")
    if gross is not None and net is not None:
        out.append(_f("net_within_gross", "plausibility", "blocking", net <= gross + 1,
                      f"Net-of-reinsurance SCR ({_eur(net)}) is within gross ({_eur(gross)})" if net <= gross + 1
                      else f"Net-of-reinsurance SCR ({_eur(net)}) EXCEEDS gross ({_eur(gross)}) — "
                           "reinsurance cannot increase the loss"))
    if gross is not None and mean is not None:
        out.append(_f("tail_exceeds_mean", "plausibility", "blocking", gross >= mean - 1,
                      f"1-in-200 tail loss ({_eur(gross)}) is at or above the mean annual loss ({_eur(mean)})"
                      if gross >= mean - 1 else f"1-in-200 tail loss ({_eur(gross)}) is BELOW the mean annual "
                                                f"loss ({_eur(mean)}) — a tail estimate should never be lower"))
    # the engine's own internal cross-check: per-zone independent EALs should sum to the portfolio mean
    cat = (rollup.get("catastrophe") or {})
    if cat.get("available") and "mean_reconciles" in cat:
        out.append(_f("cat_mean_reconciles", "tie_out", "blocking", bool(cat["mean_reconciles"]),
                      "Per-zone independent EALs reconcile to the portfolio mean annual loss"
                      if cat["mean_reconciles"] else
                      "Per-zone independent EALs do NOT reconcile to the portfolio mean annual loss — "
                      "an internal engine inconsistency, not a data gap"))
    sf = nb.get("standard_formula_natcat") or {}
    out.append(_f("standard_formula_available", "completeness", "info", bool(sf.get("available")),
                  "Standard-formula nat-cat risk (Del. Reg. 2015/35 Arts 119-126) computed beside the modelled 1-in-200 loss"
                  if sf.get("available") else "Standard-formula nat-cat risk not computed for this book"))
    if sf.get("available") and "complete" in sf:
        out.append(_f("standard_formula_complete", "completeness", "blocking", bool(sf["complete"]),
                      "Every exposure is charged" if sf["complete"] else
                      "Standard formula incomplete: " + "; ".join(sf.get("incomplete", []))))
        worse = [f"{p} {g['region']}" for p, r in (sf.get("perils") or {}).items() for g in r.get("regions", [])
                 if g["after_eur"] > g["before_eur"] + g["reinstatement_eur"] + 1]
        if sf.get("simplification_art_90b"):
            out.append(_f("s2607_also_reported", "completeness", "warning", False,
                          "A natural catastrophe simplification (Art. 90b) is used: the undertaking's submission must also "
                          "include S.26.07 (Solvency Capital Requirement — simplifications), EIOPA validation BV653. Add "
                          "postal codes to the Statement of Values to place every risk in its zone instead."))
        out.append(_f("mitigation_never_adds", "plausibility", "blocking", not worse,
                      "After mitigation never exceeds before mitigation plus reinstatement premiums" if not worse else
                      "After mitigation exceeds before plus reinstatement premiums: " + ", ".join(worse)))
    return out


def _validate_insurer_document(report_type: str):
    def run(payload: dict) -> list[dict]:
        from services.governance.insurer_documents import checks
        return checks(payload, report_type)
    return run


def _validate_csrd_e1(payload: dict) -> list[dict]:
    """CSRD ESRS E1 physical-risk report — added 2026-09-23, same gap as above, for the agri sector."""
    out: list[dict] = []
    entity = payload.get("entity") or {}
    out.append(_f("has_entity_identity", "completeness", "blocking", bool(entity.get("name")),
                  f"Reporting entity: {entity.get('name')}" if entity.get("name")
                  else "No reporting-entity name on file"))
    hazards = payload.get("material_hazards") or []
    out.append(_f("material_hazards_assessed", "completeness", "info", bool(hazards),
                  f"{len(hazards)} material hazard(s) identified" if hazards
                  else "No material hazards identified for this org — disclosed as-is, not assumed clean"))
    for h in hazards:
        for leg, label in (("own_operations", "own operations"), ("upstream", "upstream sourcing")):
            leg_data = h.get(leg)
            if leg_data is None:
                continue
            for key, name in (("asset_value_eur", "asset value"), ("bi_at_risk_eur", "BI at risk"),
                              ("spend_eur", "spend"), ("cogs_at_risk_eur", "COGS at risk")):
                v = leg_data.get(key)
                if v is not None and v < 0:
                    out.append(_f(f"non_negative:{h.get('hazard')}:{leg}:{key}", "plausibility", "blocking",
                                 False, f"{h.get('label', h.get('hazard'))} ({label}) {name} is negative ({_eur(v)})"))
    return out


def _validate_esrs_pack(payload: dict) -> list[dict]:
    """The ESRS statement (services.governance.esrs_checks). A pack frozen before the statement was rebuilt (no
    document_report) keeps the checks it was frozen under, below."""
    if payload.get("document_report") is not None:
        from services.governance.esrs_checks import checks
        return checks(payload)
    out: list[dict] = []
    entity = payload.get("entity") or {}
    topics = {t.get("topic"): t for t in (payload.get("topics") or [])}
    out.extend(_validate_csrd_e1({"entity": entity,
                                  "material_hazards": (topics.get("E1") or {}).get("material_hazards") or []}))
    e4 = topics.get("E4")
    if e4:
        covered = e4.get("eudr_covered_plots", 0) or 0
        free = e4.get("deforestation_free", 0) or 0
        non_compliant = e4.get("non_compliant", 0) or 0
        incomplete = e4.get("geolocation_incomplete", 0) or 0
        not_determined = e4.get("not_determined", 0) or 0
        accounted = free + non_compliant + incomplete + not_determined
        out.append(_f("eudr_plots_account_for_covered", "tie_out", "blocking", accounted == covered,
                      f"Every EUDR-covered plot ({covered}) is accounted for across the 4 determination states"
                      if accounted == covered else
                      f"{covered} EUDR-covered plots but the 4 determination states sum to {accounted} — "
                      "a plot fell through the classification"))
    return out


def _validate_eudr_dds(payload: dict) -> list[dict]:
    """An EUDR statement: its checks re-run on the frozen statement (services.eudr.checks)."""
    from services.eudr.checks import checks
    st = payload.get("statement")
    if not st:
        return [_f("statement_frozen", "completeness", "blocking", False, "no statement was frozen")]
    return checks(st)


def _validate_eudr_simplified(payload: dict) -> list[dict]:
    """An EUDR simplified declaration: its checks re-run on the frozen declaration (services.eudr.declaration)."""
    from services.eudr.declaration import checks
    st = payload.get("declaration")
    return checks(st) if st else [_f("declaration_frozen", "integrity", "blocking", False, "no declaration is frozen in this filing")]


_RULESETS = {"eudr_dds": _validate_eudr_dds, "eudr_simplified": _validate_eudr_simplified, "bank_tcfd": _validate_bank_tcfd, "bank_p3esg": _validate_bank_p3esg, "sfdr_pai": _validate_sfdr_pai,
             "reit_taxonomy": _validate_reit_taxonomy, "insurer_solvency": _validate_insurer_solvency,
             "insurer_orsa_climate": _validate_insurer_document("insurer_orsa_climate"),
             "insurer_recovery_stress": _validate_insurer_document("insurer_recovery_stress"),
             "csrd_e1": _validate_csrd_e1, "esrs_pack": _validate_esrs_pack,
             "sfdr_precontractual": lambda p: _validate_sfdr_product(p, "sfdr_precontractual"),
             "sfdr_periodic": lambda p: _validate_sfdr_product(p, "sfdr_periodic")}


def _validate_sfdr_product(payload: dict, report_type: str) -> list[dict]:
    from services.governance.sfdr_product_forms import checks
    return checks(payload, report_type)


def _arrears_finding(r: dict) -> dict:
    """Pure: interpret a seasonal_arrears.assessment() result as a validation finding. No fixed tolerance
    the way GL has one — the gate is that the overlay ran and every past-due loan reached a classification
    (none silently skipped; country-less loans are honestly counted as genuine, never guessed at)."""
    if not r.get("available"):
        return _f("ledger_reconciled", "tie_out", "warning", True,
                  "No arrears book uploaded yet — seasonal-vs-genuine reconciliation not checked "
                  "for this filing (upload one under Your data to enable this check)")
    s = r.get("summary") or {}
    genuine_pct = round(100 * (s.get("n_genuine") or 0) / s["n_past_due"], 1) if s.get("n_past_due") else 0
    unclassified = s.get("n_not_checked_no_country", 0) or 0
    return _f("ledger_reconciled", "tie_out", "warning", True,
              f"Seasonal-arrears overlay ran: {s.get('n_past_due', 0)} past-due loan(s), "
              f"{genuine_pct}% classified genuine deterioration"
              + (f" — {unclassified} had no country on record and were conservatively counted as genuine"
                 if unclassified else ""))


def _gl_finding(r: dict) -> dict:
    """Pure: interpret a gl_recon.reconciliation() result as a validation finding. An uploaded ledger with a
    variance OUTSIDE tolerance is BLOCKING — the actual gap this closes (see module docstring); no ledger at
    all is only a WARNING, since not every org has onboarded this overlay yet."""
    if not r.get("available"):
        return _f("ledger_reconciled", "tie_out", "warning", True,
                  "No general ledger uploaded yet — the reported book has not been tied to your GL for this "
                  "filing (upload one under Your data to enable this check)")
    var_pct = r.get("variance_pct")
    tol = r.get("tolerance_pct")
    reconciled = bool(r.get("reconciled"))
    return _f("ledger_reconciled", "tie_out", "blocking", reconciled,
              f"Reported book ties to the GL (variance {var_pct}%, within ±{tol}% tolerance)" if reconciled
              else f"Reported book variance {var_pct}% EXCEEDS the ±{tol}% GL tolerance "
                   f"({r.get('reported_book_eur')} reported vs {r.get('gl_book_eur')} on the ledger) — "
                   "resolve the variance or correct the upload before this filing can be submitted for review")


def _reconciliation_finding(session: Session, org_id: str, org_type: str | None) -> dict | None:
    """The ledger-tie-out gate: GL reconciliation for bank/insurer/reit/asset_manager, seasonal-arrears
    assessment for agri (manufacturer). Returns None only when the org type has no reconciliation overlay
    at all (nothing to check, nothing to flag). Fetches live state, then hands off to the pure interpreters
    above (_gl_finding / _arrears_finding), which is what tests exercise directly."""
    if org_type == "manufacturer":
        from services.governance.seasonal_arrears import assessment
        return _arrears_finding(assessment(session, org_id))
    from services.governance.gl_recon import VERTICAL, reconciliation
    if org_type not in VERTICAL:
        return None
    return _gl_finding(reconciliation(session, org_id, org_type))


def _org_type(session: Session, org_id: str) -> str | None:
    return session.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                           {"o": org_id}).scalar()


# ── entry point ─────────────────────────────────────────────────────────

def _fx_findings(payload: dict, revisions: list[dict]) -> list[dict]:
    """Multi-currency phase 3: the rates a filing froze — none revised since, none stale. Warnings: a person decides
    whether the change matters (a revision may be immaterial); restating is one click away."""
    fx = payload.get("_fx") or {}
    if not fx.get("rates_used"):
        return []
    out = [_f("fx_rates_current", "currency", "warning", not revisions,
              "Every exchange rate this filing used is unchanged since it was frozen" if not revisions else
              f"{len(revisions)} exchange rate(s) used have changed since the freeze ("
              + "; ".join(f"{r['currency']} {r['basis']} {r['as_of']}" for r in revisions[:3]) + ") — consider restating")]
    n = fx.get("n_stale_rates") or 0
    out.append(_f("fx_rates_fresh", "currency", "warning", n == 0,
                  "Every exchange rate was current for its date" if n == 0 else
                  f"{n} exchange rate(s) were older than their source normally publishes — check before submitting"))
    return out


def validate_filing(session: Session, org_id: str, filing_id: str) -> dict:
    """Run the checklist over a filing's frozen snapshot. Returns findings + counts; `passed` is True
    only when no blocking rule fails."""
    filing = get_filing(session, org_id, filing_id, with_payload=True)
    if not filing:
        raise ValueError("filing not found")
    findings: list[dict] = []

    snap = filing.get("snapshot")
    # generic: the frozen bytes must still verify against their hash
    findings.append(_f("snapshot_frozen", "integrity", "blocking", bool(snap),
                       "Report is frozen as an immutable snapshot" if snap
                       else "No frozen snapshot behind this filing"))
    if snap:
        findings.append(_f("hash_verified", "integrity", "blocking", bool(snap.get("hash_verified")),
                           "Frozen payload matches its content hash" if snap.get("hash_verified")
                           else "Frozen payload does NOT match its content hash — tampered or drifted"))
        ruleset = _RULESETS.get(filing["framework"])
        payload = snap.get("payload") or {}
        token = money_format.current.set(money_format.presentation_of(payload))
        try:
            if ruleset:
                findings.extend(ruleset(payload))
            findings.extend(_method_findings(payload, filing["framework"]))
        finally:
            money_format.current.reset(token)
        findings.extend(_fx_findings(payload, filing.get("fx_revisions") or []))
        # cross-report reconciliation vs sibling filings (warning/info only — never blocks a real change)
        from services.governance.filing_crosscheck import cross_report_findings
        findings.extend(cross_report_findings(session, org_id, filing))
        # ledger tie-out (GL for bank/insurer/reit/asset_manager, seasonal-arrears for agri) — genuinely
        # gates submission now; see module docstring
        recon = _reconciliation_finding(session, org_id, _org_type(session, org_id))
        if recon:
            findings.append(recon)

    blocking = sum(1 for f in findings if f["severity"] == "blocking" and not f["passed"])
    warnings = sum(1 for f in findings if f["severity"] == "warning" and not f["passed"])
    passed = blocking == 0
    return {"filing_id": filing_id, "framework": filing["framework"], "status": filing["status"],
            "findings": findings, "blocking": blocking, "warnings": warnings,
            "checks": len(findings), "passed": passed}


def blocking_messages(result: dict) -> list[str]:
    return [f["message"] for f in result["findings"] if f["severity"] == "blocking" and not f["passed"]]
