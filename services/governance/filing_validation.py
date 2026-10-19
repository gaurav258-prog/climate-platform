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

from core import messages
from services.governance import money_format
from services.governance.filings import get_filing


def _f(rule: str, category: str, severity: str, passed: bool, message: str, ref: str | None = None) -> dict:
    """A finding in another rule set's own sentence (insurer documents, SFDR product forms, the ESRS statement, EUDR):
    kept for those rule sets until they name their findings in the catalogue; a screen shows the sentence one click
    away, behind its outcome."""
    return {"rule": rule, "category": category, "severity": severity, "passed": passed,
            "message": message, "ref": ref}


def _check(rule: str, category: str, severity: str, passed: bool, code: str, ref: str | None = None, **params) -> dict:
    """A finding in the catalogue's words (UI standard, 2026-10-16; data/reference/messages.en.json, filing.check.* and
    filing.gap.*): `msg` is the message — its label for the checklist, its detail behind the ⓘ — and `message` its
    sentence for the other readers (the exception monitor, the filing's task, a refusal to send it for approval).
    `ref` is the legal basis, shown one click away."""
    m = messages.render(code, **params)
    return {"rule": rule, "category": category, "severity": severity, "passed": passed,
            "message": m["detail"]["what"], "msg": m, "ref": ref}


def _eur(n) -> str:
    """A figure in the filing's own currency (money_format.current, set by validate_filing from the snapshot)."""
    try:
        return money_format.money(float(n), compact=False)
    except (TypeError, ValueError):
        return f"{money_format.symbol(money_format.current.get())}—"


def _name(kind: str, key: str) -> str:
    """A hazard's or a peril's customer name (the catalogue's names.<kind>); the key in plain words if it has none."""
    try:
        return messages.name(kind, key)
    except messages.MessageError:
        return key.replace("_", " ")


# ── shared checks: what is in scope, scored, of value ──────────────────

def _in_scope(n: int, noun: str, rule: str = "has_assets") -> dict:
    return (_check(rule, "completeness", "blocking", True, "filing.check.in_scope.ok", n=n, noun=noun) if n > 0
            else _check(rule, "completeness", "blocking", False, "filing.check.in_scope.fail", noun=noun))


def _value(rule: str, total, measure: str) -> dict:
    return (_check(rule, "plausibility", "blocking", True, "filing.check.value.ok", measure=measure, value=_eur(total))
            if total > 0 else _check(rule, "plausibility", "blocking", False, "filing.check.value.fail", measure=measure))


def _coverage(n: int, done: int, noun: str) -> dict:
    pct = round(100 * done / n, 1) if n else 0
    if n > 0 and done == n:
        return _check("full_coverage", "completeness", "warning", True, "filing.check.coverage.ok", n=n, noun=noun, pct=pct)
    return _check("full_coverage", "completeness", "warning", False, "filing.check.coverage.fail",
                  done=done, total=n, noun=noun, pct=pct, left=n - done)


def _emissions_sign(em: dict) -> dict:
    words = {"scope1": "scope 1", "scope2": "scope 2", "scope3": "scope 3", "i": "column i", "j": "column j"}
    neg = [words.get(k, k.replace("_", " ")) for k, v in em.items() if (v or 0) < 0]
    return (_check("emissions_non_negative", "plausibility", "warning", True, "filing.check.emissions_sign.ok") if not neg
            else _check("emissions_non_negative", "plausibility", "warning", False, "filing.check.emissions_sign.fail",
                        scopes=", ".join(neg)))


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
    return [_in_scope(n, "exposures"), _value("total_value_positive", total, "Total book value"), _gross("warning", assets, missing)]


def _gross(severity: str, assets: list, missing: int, ref: str | None = None) -> dict:
    return (_check("gross_carrying_amount_stated", "completeness", severity, True, "filing.check.gross_amount.ok",
                   ref=ref, n=len(assets)) if not missing
            else _check("gross_carrying_amount_stated", "completeness", severity, False, "filing.gap.no_gross", ref=ref,
                        n=missing, total=len(assets)))


def _validate_bank_book(payload: dict) -> list[dict]:
    """The located loan book's checks (Pillar 3 ESG, and bank_tcfd filings of the earlier report shape)."""
    out: list[dict] = []
    rollup = payload.get("rollup") or {}
    n_assets = rollup.get("n_assets", 0)
    n_scored = rollup.get("n_scored", 0)
    total = rollup.get("total_value_eur", 0) or 0

    # completeness
    out.append(_in_scope(n_assets, "assets"))
    out.append(_check("some_scored", "completeness", "blocking", True, "filing.check.scored.ok", n=n_scored, noun="assets")
               if n_scored > 0 else _check("some_scored", "completeness", "blocking", False, "filing.check.scored.fail", noun="assets"))
    out.append(_coverage(n_assets, n_scored, "assets"))

    # plausibility
    out.append(_value("total_value_positive", total, "Total book value"))
    pct = rollup.get("pct_value_at_risk")
    if pct is not None:
        ok = 0 <= pct <= 100
        out.append(_check("share_in_range", "plausibility", "warning", ok,
                          "filing.check.share_range.ok" if ok else "filing.check.share_range.fail", pct=pct))
    out.append(_emissions_sign(payload.get("financed_emissions_tco2e") or {}))
    for hz, b in (payload.get("by_hazard") or {}).items():
        ev = b.get("exposed_value_eur")
        if ev is None:
            continue                                   # a gap — reported by method_stated
        ok = ev <= total * 1.0001 or total == 0
        out.append(_check(f"hazard_within_book:{hz}", "plausibility", "warning", ok,
                          "filing.check.hazard_book.ok" if ok else "filing.check.hazard_book.fail",
                          hazard=_name("hazard", hz), value=_eur(ev), total=_eur(total)))

    # tie-out (internal reconciliation)
    buckets = rollup.get("by_bucket") or {}
    bucket_sum = sum((b.get("value_eur", 0) or 0) for b in buckets.values())
    tol = max(1.0, 0.005 * total)
    ok = abs(bucket_sum - total) <= tol
    out.append(_check("buckets_reconcile", "tie_out", "blocking", ok,
                      "filing.check.buckets.ok" if ok else "filing.check.buckets.fail",
                      value=_eur(bucket_sum), total=_eur(total)))
    var = rollup.get("value_at_risk_eur")
    if var is not None:        # at or above the bank's stated level — a part of the book, never more
        ok = var <= total + tol
        out.append(_check("var_within_book", "tie_out", "blocking", ok,
                          "filing.check.var_book.ok" if ok else "filing.check.var_book.fail", value=_eur(var), total=_eur(total)))
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
    return [
        _in_scope(n, "exposures"),
        _check("some_scored", "completeness", "blocking", True, "filing.check.scored.ok", n=scored, noun="exposures")
        if scored > 0 else _check("some_scored", "completeness", "blocking", False, "filing.check.scored.fail", noun="exposures"),
        _coverage(n, scored, "exposures"),
        _value("total_value_positive", total, "Total book value"),
        _emissions_sign(em),
    ]


def _qualitative_findings(payload: dict) -> list[dict]:
    """Tables 1-3 (the qualitative information on environmental, social and governance risk) are part of what the
    institution discloses: every row, as frozen for its undertaking and reference date, carries its text. A filing frozen
    before the text was frozen with it has none to check."""
    if payload.get("qualitative") is None:
        return []
    from services.governance.filing_annex import _p3_spec
    from services.governance.pillar3_qualitative import unanswered
    spec = _p3_spec(payload)
    left = unanswered(spec, payload["qualitative"])
    ref = f"{spec['act'].get('short') or spec['act']['title']}, Tables 1–3"
    return [_check("qualitative_tables_answered", "completeness", "blocking", True, "filing.check.qualitative.ok", ref=ref)
            if not left else
            _check("qualitative_tables_answered", "completeness", "blocking", False, "filing.gap.qualitative", ref=ref, n=len(left))]


def _validate_bank_p3esg(payload: dict) -> list[dict]:
    """The bank checks plus Pillar 3's own: every template amount is a gross carrying amount — the exposure's outstanding
    balance on the loan tape, never its collateral value — so an exposure that states none blocks the filing."""
    from services.governance.pillar3_grids import no_gross
    from services.governance.pillar3_report import is_earlier_shape
    assets = payload.get("assets") or []
    # a filing of the earlier report shape keeps the checks it was made under; a new one checks what its templates read —
    # no severity-bucket, value-at-risk or per-hazard figure is frozen any more (E97)
    base = _validate_bank_book(payload) if is_earlier_shape(payload) else _validate_p3_book(payload)
    return base + _t1_findings(payload) + _qualitative_findings(payload) + [
        _gross("blocking", assets, no_gross(assets), ref="ITS (EU) 2024/3172 Annex XL — gross carrying amount")]


# Template 1's per-exposure checks: the rule, the count it reads (pillar3_report.t1_total "stated"); the failing message
# is the pre-filing check's (pillar3_report.T1_EXPOSURE_GAPS), so both say the same thing.
_T1_EXPOSURE_RULES = (("t1_counterparty_identified", "no_counterparty"), ("t1_counterparty_figure_agreed", "conflict"),
                      ("t1_scope3_basis", "s3_gap"), ("t1_total_liabilities_stated", "unattributed"),
                      ("t1_exposure_within_liabilities", "over"), ("t1_emissions_source_recorded", "rep_unknown"))


def _t1_findings(payload: dict) -> list[dict]:
    """Template 1 columns i-k (E103): the institution's statements (which emissions it estimates, how they are
    attributed) are made; every exposure the columns read states what they need; the narrative the instructions
    require is authored. A filing frozen before the statements were recorded keeps the checks it was made under."""
    from services.governance import pillar3_t1 as T1
    from services.governance.pillar3_report import T1_EXPOSURE_GAPS, t1_total
    rec = payload.get(T1.RECORD)
    if rec is None:
        return []
    ref = "Annex XL, Template 1, columns i–k (ITS 2022/2453; ITS 2024/3172)"
    kinds = T1.gap_kinds(rec)
    out = [_check("t1_method_stated", "completeness", "blocking", True, "filing.check.emissions_method.ok", ref=ref) if not kinds
           else _check("t1_method_stated", "completeness", "blocking", False, f"filing.gap.emissions_{kinds[0]}", ref=ref)]
    st = (t1_total(payload) or {}).get("stated") or {}
    for rule, k in _T1_EXPOSURE_RULES:
        n = st.get(k, 0)
        out.append(_check(rule, "completeness", "blocking", True, "filing.check.emissions_inputs.ok", ref=ref) if not n
                   else _check(rule, "completeness", "blocking", False, T1_EXPOSURE_GAPS[k], ref=ref, n=n,
                               reasons=T1.scope3_reasons(payload) if k == "s3_gap" else None))
    k_ref = "Annex XL, Template 1, column k"
    out.append(_check("t1_k_reading_stated", "completeness", "blocking", True, "filing.check.reported_share.ok", ref=k_ref)
               if not T1.k_gap_open(rec) else
               _check("t1_k_reading_stated", "completeness", "blocking", False, "filing.gap.reported_share_basis", ref=k_ref))
    missing = T1.missing_narrative(rec)
    out.append(_check("t1_narrative_authored", "completeness", "blocking", True, "filing.check.emissions_narrative.ok", ref=ref)
               if not missing else
               _check("t1_narrative_authored", "completeness", "blocking", False, "filing.gap.emissions_narrative", ref=ref,
                      items="; ".join(n["prompt"] for n in missing)))
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
    from services.money import params
    gaps = rec.get("gaps") or []
    short = {k: v["short"] for k, v in params.parameters().items()}
    named = [short.get(g["key"], "A method choice") + (f" ({g['member']})" if g.get("member") else "") for g in gaps[:12]]
    names = ", ".join(named) + (f" and {len(gaps) - 12} more" if len(gaps) > 12 else "")
    severity = "warning" if framework in _METHOD_WARNS else "blocking"
    ref = "The institution's stated method (Methodology)"
    return [_check("method_stated", "completeness", severity, True, "filing.check.method.ok", ref=ref,
                   period_end=rec.get("period_end")) if not gaps
            else _check("method_stated", "completeness", severity, False, "filing.check.method.fail", ref=ref, names=names)]


def _validate_sfdr_pai(payload: dict) -> list[dict]:
    from services.governance.filings import sfdr_missing, sfdr_reason
    out: list[dict] = []
    if payload.get("error"):
        m = sfdr_reason(payload["error"])
        return [_check("statement_builds", "completeness", "blocking", False, m["code"], **m["params"])]
    entity = payload.get("entity") or {}
    positions = entity.get("positions", 0) or 0
    total = entity.get("total_value_eur", 0) or 0

    out.append(_check("has_positions", "completeness", "blocking", True, "filing.check.in_scope.ok", n=positions, noun="positions")
               if positions > 0 else _check("has_positions", "completeness", "blocking", False, "filing.check.in_scope.fail", noun="positions"))
    out.append(_value("total_value_positive", total, "Net asset value in scope"))

    # a statement covers 1 January - 31 December, each impact the average of the four quarter ends (Art. 4(1), 6(3))
    rp = payload.get("reference_period")
    ref = "RTS 2022/1288 Art. 4(1), 6(3)"
    out.append(_check("reference_period", "completeness", "blocking", True, "filing.check.sfdr_period.ok", ref=ref,
                      start=rp["start"], end=rp["end"], dates=", ".join(rp["impact_dates"])) if rp
               else _check("reference_period", "completeness", "blocking", False, "filing.check.sfdr_period.fail", ref=ref))
    by_code = {m["code"]: m for m in sfdr_missing((payload.get("filing_readiness") or {}).get("missing") or [])}
    for rule, code, ok_code, r in (("filing_identity", "filing.gap.sfdr_identity", "filing.check.sfdr_identity.ok", None),
                                   ("holdings_on_impact_dates", "filing.gap.sfdr_holdings", "filing.check.sfdr_holdings.ok",
                                    "RTS 2022/1288 Art. 6(3)"),
                                   ("sections_answered", "filing.gap.sfdr_answers", "filing.check.sfdr_answers.ok",
                                    "RTS 2022/1288 Art. 5-9")):
        m = by_code.get(code)
        out.append(_check(rule, "completeness", "blocking", True, ok_code, ref=r) if m is None
                   else _check(rule, "completeness", "blocking", False, code, ref=r, **m["params"]))

    cs = payload.get("coverage_summary") or {}
    mand = cs.get("mandatory_indicators", 0) or 0
    comp = cs.get("computed", 0) or 0
    out.append(_check("mandatory_indicators", "completeness", "warning", True, "filing.check.pai_indicators.ok", n=mand)
               if mand > 0 and comp == mand else
               _check("mandatory_indicators", "completeness", "warning", False, "filing.gap.pai_indicators", done=comp, total=mand))
    emis = cs.get("emissions_coverage_pct")
    if emis is not None:
        out.append(_check("emissions_coverage", "completeness", "warning", emis >= 50,
                          "filing.check.emissions_coverage.ok" if emis >= 50 else "filing.check.emissions_coverage.fail", pct=emis))
    # per-fund thin coverage — surfaced, never averaged away (info)
    thin = [f["fund_name"] for f in (payload.get("per_fund") or [])
            if (f.get("emissions_coverage_pct") or 0) < 30]
    out.append(_check("per_fund_coverage", "completeness", "info", True, "filing.check.fund_coverage.ok") if not thin
               else _check("per_fund_coverage", "completeness", "info", False, "filing.check.fund_coverage.fail",
                           funds=", ".join(thin)))
    return out


def _validate_reit_taxonomy(payload: dict) -> list[dict]:
    """EU Taxonomy Article 8 KPIs (property book) — added 2026-09-23, closing a gap an independent
    architecture review found: this framework had zero pre-submission checks (only the two generic
    integrity checks every framework gets), unlike bank_tcfd/sfdr_pai."""
    out: list[dict] = []
    rollup = payload.get("rollup") or {}
    n_total, n_scored = rollup.get("n_properties", 0), rollup.get("n_scored", 0)
    total = rollup.get("total_value_eur", 0) or 0

    out.append(_in_scope(n_total, "properties", "has_properties"))
    out.append(_value("total_value_positive", total, "Portfolio value"))
    out.append(_coverage(n_total, n_scored, "properties"))

    # the EU Taxonomy Art. 8 figures come from the property book (services.governance.taxonomy_nonfin)
    from services.governance.taxonomy_nonfin import summary_of
    sm = summary_of(payload)
    if sm["n_unknown"]:
        out.append(_check("alignment_determined", "completeness", "warning", False, "filing.check.alignment.fail",
                          n=sm["n_unknown"], value=_eur(sm["unknown"]),
                          reasons="; ".join(f"{r} ({n})" for r, n in sm["unknown_reasons"])))
    if sm["noi_proxy"]:
        out.append(_check("turnover_basis", "completeness", "warning", False, "filing.check.turnover_basis.fail",
                          n=sm["noi_proxy"], total=sm["n"]))
    out.append(_check("capex_opex_ledger", "completeness", "info", False, "filing.check.capex_opex.info"))
    return out


def _validate_insurer_solvency(payload: dict) -> list[dict]:
    """Solvency II natural catastrophe risk (S.27.01.01) — added 2026-09-23, same gap as reit_taxonomy above."""
    out: list[dict] = []
    rollup = payload.get("rollup") or {}
    n_total, n_priced = rollup.get("n_policies", 0), rollup.get("n_priced", 0)
    total = rollup.get("total_sum_insured_eur", 0) or 0

    out.append(_check("has_policies", "completeness", "blocking", True, "filing.check.in_scope.ok", n=n_total, noun="policies")
               if n_total > 0 else _check("has_policies", "completeness", "blocking", False, "filing.check.in_scope.fail", noun="policies"))
    out.append(_check("some_priced", "completeness", "blocking", True, "filing.check.priced.ok", n=n_priced)
               if n_priced > 0 else _check("some_priced", "completeness", "blocking", False, "filing.check.priced.fail"))
    out.append(_value("total_sum_insured_positive", total, "Total sum insured"))

    from services.governance.insurer_solvency import natcat_block
    nb = natcat_block(payload)
    scr = nb.get("natcat_scr") or {}
    gross = scr.get("gross_1_in_200_eur")
    net = scr.get("net_of_reinsurance_1_in_200_eur")
    mean = scr.get("mean_annual_loss_eur")
    if gross is not None and net is not None:
        ok = net <= gross + 1
        out.append(_check("net_within_gross", "plausibility", "blocking", ok,
                          "filing.check.net_gross.ok" if ok else "filing.check.net_gross.fail", net=_eur(net), gross=_eur(gross)))
    if gross is not None and mean is not None:
        ok = gross >= mean - 1
        out.append(_check("tail_exceeds_mean", "plausibility", "blocking", ok,
                          "filing.check.tail_mean.ok" if ok else "filing.check.tail_mean.fail", gross=_eur(gross), mean=_eur(mean)))
    # the engine's own internal cross-check: per-zone independent EALs should sum to the portfolio mean
    cat = (rollup.get("catastrophe") or {})
    if cat.get("available") and "mean_reconciles" in cat:
        ok = bool(cat["mean_reconciles"])
        out.append(_check("cat_mean_reconciles", "tie_out", "blocking", ok,
                          "filing.check.zones.ok" if ok else "filing.check.zones.fail"))
    sf = nb.get("standard_formula_natcat") or {}
    sf_ref = "Delegated Regulation (EU) 2015/35, Articles 119-126"
    out.append(_check("standard_formula_available", "completeness", "info", bool(sf.get("available")),
                      "filing.check.sf_available.ok" if sf.get("available") else "filing.check.sf_available.fail", ref=sf_ref))
    if sf.get("available") and "complete" in sf:
        out.append(_check("standard_formula_complete", "completeness", "blocking", True, "filing.check.sf_complete.ok", ref=sf_ref)
                   if sf["complete"] else
                   _check("standard_formula_complete", "completeness", "blocking", False, "filing.check.sf_complete.fail",
                          ref=sf_ref, items="; ".join(sf.get("incomplete", []))))
        worse = [f"{_name('hazard', p)} {g.get('region_name') or g['region']}" for p, r in (sf.get("perils") or {}).items()
                 for g in r.get("regions", []) if g["after_eur"] > g["before_eur"] + g["reinstatement_eur"] + 1]
        if sf.get("simplification_art_90b"):
            out.append(_check("s2607_also_reported", "completeness", "warning", False, "filing.check.simplification.fail",
                              ref="Delegated Regulation (EU) 2015/35, Article 90b; template S.26.07; EIOPA validation BV653"))
        out.append(_check("mitigation_never_adds", "plausibility", "blocking", True, "filing.check.mitigation.ok") if not worse
                   else _check("mitigation_never_adds", "plausibility", "blocking", False, "filing.check.mitigation.fail",
                               items=", ".join(worse)))
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
    out.append(_check("has_entity_identity", "completeness", "blocking", True, "filing.check.entity.ok", name=entity["name"])
               if entity.get("name") else _check("has_entity_identity", "completeness", "blocking", False, "filing.check.entity.fail"))
    hazards = payload.get("material_hazards") or []
    out.append(_check("material_hazards_assessed", "completeness", "info", True, "filing.check.material_hazards.ok", n=len(hazards))
               if hazards else _check("material_hazards_assessed", "completeness", "info", False, "filing.check.material_hazards.fail"))
    for h in hazards:
        for leg, label in (("own_operations", "own operations"), ("upstream", "upstream sourcing")):
            leg_data = h.get(leg)
            if leg_data is None:
                continue
            for key, name in (("asset_value_eur", "asset value"), ("bi_at_risk_eur", "business interruption at risk"),
                              ("spend_eur", "spend"), ("cogs_at_risk_eur", "cost of goods at risk")):
                v = leg_data.get(key)
                if v is not None and v < 0:
                    out.append(_check(f"non_negative:{h.get('hazard')}:{leg}:{key}", "plausibility", "blocking", False,
                                      "filing.check.negative.fail", hazard=h.get("label") or _name("hazard", h.get("hazard") or ""),
                                      leg=label, measure=name, value=_eur(v)))
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
        ok = accounted == covered
        out.append(_check("eudr_plots_account_for_covered", "tie_out", "blocking", ok,
                          "filing.check.plots.ok" if ok else "filing.check.plots.fail", n=covered, sum=accounted))
    return out


def _validate_eudr_dds(payload: dict) -> list[dict]:
    """An EUDR statement: its checks re-run on the frozen statement (services.eudr.checks)."""
    from services.eudr.checks import checks
    st = payload.get("statement")
    if not st:
        return [_check("statement_frozen", "completeness", "blocking", False, "filing.check.eudr_statement.fail")]
    return checks(st)


def _validate_eudr_simplified(payload: dict) -> list[dict]:
    """An EUDR simplified declaration: its checks re-run on the frozen declaration (services.eudr.declaration)."""
    from services.eudr.declaration import checks
    st = payload.get("declaration")
    return checks(st) if st else [_check("declaration_frozen", "integrity", "blocking", False, "filing.check.eudr_declaration.fail")]


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
        return _check("ledger_reconciled", "tie_out", "warning", True, "filing.check.arrears.none")
    s = r.get("summary") or {}
    genuine_pct = round(100 * (s.get("n_genuine") or 0) / s["n_past_due"], 1) if s.get("n_past_due") else 0
    unclassified = s.get("n_not_checked_no_country", 0) or 0
    if unclassified:
        return _check("ledger_reconciled", "tie_out", "warning", True, "filing.check.arrears.no_country",
                      n=s.get("n_past_due", 0), pct=genuine_pct, m=unclassified)
    return _check("ledger_reconciled", "tie_out", "warning", True, "filing.check.arrears.ok",
                  n=s.get("n_past_due", 0), pct=genuine_pct)


def _gl_finding(r: dict) -> dict:
    """Pure: interpret a gl_recon.reconciliation() result as a validation finding. An uploaded ledger with a
    variance OUTSIDE tolerance is BLOCKING — the actual gap this closes (see module docstring); no ledger at
    all is only a WARNING, since not every org has onboarded this overlay yet."""
    if not r.get("available"):
        return _check("ledger_reconciled", "tie_out", "warning", True, "filing.check.ledger.none")
    var_pct = r.get("variance_pct")
    tol = r.get("tolerance_pct")
    if r.get("reconciled"):
        return _check("ledger_reconciled", "tie_out", "blocking", True, "filing.check.ledger.ok", var=var_pct, tol=tol)
    return _check("ledger_reconciled", "tie_out", "blocking", False, "filing.check.ledger.fail", var=var_pct, tol=tol,
                  reported=_eur(r.get("reported_book_eur")), ledger=_eur(r.get("gl_book_eur")))


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
    basis = {"closing": "closing rate", "average": "average rate"}
    out = [_check("fx_rates_current", "currency", "warning", True, "filing.check.fx_current.ok") if not revisions
           else _check("fx_rates_current", "currency", "warning", False, "filing.check.fx_current.fail", n=len(revisions),
                       items="; ".join(f"{r['currency']} {basis.get(r['basis'], r['basis'])} on {r['as_of']}" for r in revisions[:3]))]
    n = fx.get("n_stale_rates") or 0
    out.append(_check("fx_rates_fresh", "currency", "warning", True, "filing.check.fx_fresh.ok") if n == 0
               else _check("fx_rates_fresh", "currency", "warning", False, "filing.check.fx_fresh.fail", n=n))
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
    findings.append(_check("snapshot_frozen", "integrity", "blocking", bool(snap),
                           "filing.check.frozen.ok" if snap else "filing.check.frozen.fail"))
    if snap:
        ok = bool(snap.get("hash_verified"))
        findings.append(_check("hash_verified", "integrity", "blocking", ok,
                               "filing.check.fingerprint.ok" if ok else "filing.check.fingerprint.fail"))
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
    """Each failing blocking check in a line: its catalogue label, or (a rule set that names its findings in its own
    sentence) that sentence."""
    return [(f.get("msg") or {}).get("label") or f["message"]
            for f in result["findings"] if f["severity"] == "blocking" and not f["passed"]]
