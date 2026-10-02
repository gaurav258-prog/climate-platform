"""Pillar 3 ESG — report type `bank_p3esg` (ITS (EU) 2022/2453, as amended by ITS (EU) 2024/3172: Tables 1–3, Templates
1–10; the specs in data/reference/regspec/bank_p3esg). The filing prints what those templates print, nothing else (E97).

What a filing freezes: the banking book per exposure — the facts the templates read (pillar3_grids, pillar3_gar,
pillar3_other, transition_alignment), with each exposure's hazard scores (Template 5 reads them against the stated
at-risk level), without the climate-discounted valuation no template reads —; the book's count, scored count and total
(the engine run's checks); the institution's statements for Template 1 columns i–k — which emissions it estimates, how
they are attributed, and the narrative the instructions require (services.governance.pillar3_t1, E103; the EVIC-based
PCAF figure frozen from E97 to E103 is not what the template prints, and a filing of that time shows it as frozen);
the method record; plus the records every filing carries (_specs, _fx, _consolidation, provided values …).

Not frozen any more (no template prints them; they stay live analytics — GET /v1/bank/disclosure, the KRI page):
physical climate expected loss (IFRS 9-style EL; Templates 1 and 5 print the institution's accumulated impairment, not a
modelled loss), counterparty transition expected loss, real-estate collateral EPC stranding (Template 2 prints the
collateral's energy efficiency, not a brown discount or a stressed LTV), value exposed per hazard (Template 5 prints the
chronic / acute split per sector and geography row), the value-weighted Taxonomy-status summary (Templates 6–9 print the
GAR and BTAR), and the book-level value-at-risk headline (Template 5 prints no book total).

Filings frozen before E97 carry the earlier report shape. They stay readable as frozen: the templates first, then what
they froze beyond them, each part marked as from the earlier report shape.
"""
from __future__ import annotations

REPORT = "bank_p3esg"
# top-level keys only the earlier report shape froze
EARLIER_KEYS = ("expected_loss", "transition", "collateral_stranding", "by_hazard", "taxonomy")
# per exposure: the climate-discounted valuation — no template reads it
NOT_FROZEN = ("valuation",)
EARLIER = "Earlier report shape"
EARLIER_NOTE = ("Frozen under the earlier shape of this report (before E97), which also carried figures no Pillar 3 "
                "template prints. Shown as frozen; not part of the ITS templates.")
_KEPT_GROUPS = ("Financed emissions (PCAF)",)


def is_earlier_shape(payload: dict | None) -> bool:
    return any(k in (payload or {}) for k in EARLIER_KEYS)


def freeze(session, org_id, scenario, horizon, entity_ids=None, value_weights=None, translation=None, period_end=None) -> dict:
    """The payload a new filing freezes (report_snapshots._BUILDERS)."""
    from api.routers.bank import loan_book
    assets, method = loan_book(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                               translation=translation, period_end=period_end)
    book = [{k: v for k, v in a.items() if k not in NOT_FROZEN} for a in assets]
    # the method record says what the frozen figures read: the stated at-risk level, which makes an exposure sensitive
    # in Template 5 (a gap when not stated). The parameters only the valuation read are not recorded: it is not frozen.
    from services.money.params import for_org
    read = for_org(session, org_id, method.period_end)
    read.get("method.at_risk_level")
    # Template 1 columns i-k: the institution's stated estimation and attribution, and the narrative the instructions
    # require (E103) — the EVIC-based PCAF figure is not what the template prints, and is not frozen any more
    # the institution the filing is for (a solo entity or a group's top; None: the organisation) — its own narrative and
    # qualitative Tables 1-3 for the reference date are frozen with the figures
    import services.regspec as R
    from services.governance import pillar3_qualitative as Q
    from services.governance.entities import root_of
    from services.governance.pillar3_t1 import RECORD, record
    who = root_of(session, org_id, entity_ids)
    spec = R.governing("bank_p3esg", period_end=method.period_end)
    return {"assets": book,
            "rollup": {"n_assets": len(book), "n_scored": sum(1 for a in book if a.get("headline_bucket")),
                       "total_value_eur": round(sum(a.get("value_eur") or 0 for a in book))},
            RECORD: record(session, org_id, method.period_end, who), "method": read.record(),
            "qualitative": Q.frozen(session, org_id, who, method.period_end, spec) if spec else None}


def t1_total(payload: dict) -> dict | None:
    """Template 1's total row, columns i, j and k, as the filing prints them (its frozen spec, book and statements);
    None where the filing froze no per-exposure book or its version has no Template 1."""
    from services.governance.filing_annex import _p3_spec
    from services.governance.pillar3_grids import BINDING, build
    from services.governance.pillar3_t1 import RECORD
    p = payload or {}
    spec, assets = _p3_spec(p), p.get("assets") or []
    if not spec or not assets or not any(t["id"] == "T1" for t in spec["templates"]):
        return None
    total = next(rid for rid, how in BINDING["T1"]["rows"].items() if how == "computed:total")
    g = build(spec, "T1", assets, t1=p.get(RECORD))
    row = next(x for x in g["rows"] if x["id"] == total)
    return {**{c: row["values"].get(c) for c in ("i", "j", "k")}, "row": total, "stated": g["stated"]}


# ── form ──────────────────────────────────────────────────────────────────────
def form(payload: dict) -> list[dict]:
    """The filing's datapoints: Template 1's financed emissions (total row, columns i, j, k, on the institution's stated
    method) and the frozen book's size. A filing frozen before the statements were recorded shows the PCAF figure it
    froze instead; a frozen earlier-shape filing also shows what it froze beyond them, each group marked as such (its
    keys unchanged, so its overrides still apply)."""
    from services.governance.filing_form import _dp, _located_book_form
    from services.governance.pillar3_t1 import RECORD, gaps, k_gap
    located = _located_book_form(REPORT, payload)
    if RECORD in (payload or {}):
        t = t1_total(payload) or {}
        why = "; ".join(gaps(payload[RECORD])) or None
        why_k = why or k_gap(payload[RECORD])
        groups = [{"group": "Template 1 · financed emissions (total row)", "datapoints": [
            _dp("emissions.total", "GHG financed emissions — column i", t.get("i"), "tco2e", note=why),
            _dp("emissions.scope3", "Of which Scope 3 financed emissions — column j", t.get("j"), "tco2e", note=why),
            _dp("emissions.company_reported_pct", "Share of the portfolio derived from company-specific reporting — column k",
                t.get("k"), "pct", note=why_k)]}]
    else:
        groups = [g for g in located if g["group"] in _KEPT_GROUPS]
    r = payload.get("rollup") or {}
    n = r.get("n_assets", len(payload.get("assets") or []))
    groups.append({"group": "Frozen banking book", "datapoints": [
        _dp("book.n_assets", "Exposures in the frozen book", n, "num", source="book",
            note=f"{r.get('n_scored', 0)} of {n} scored on the golden source (Template 5 reads the scores)")]})
    if is_earlier_shape(payload):
        groups += [{"group": f"{EARLIER} · {g['group']}", "datapoints": g["datapoints"], "note": EARLIER_NOTE}
                   for g in located if g["group"] not in _KEPT_GROUPS]
    return groups


# ── annex ─────────────────────────────────────────────────────────────────────
def earlier_sections(payload: dict) -> list[dict]:
    """What an earlier-shape filing froze beyond the templates (the credit-risk analytics), marked; [] for a new one."""
    if not is_earlier_shape(payload):
        return []
    from services.governance.filing_annex import _bank_analytics_sections
    return [{**s, "title": f"{EARLIER} · {s['title']}", "note": " ".join(n for n in (EARLIER_NOTE, s.get("note")) if n)}
            for s in _bank_analytics_sections(payload)]


# ── export ────────────────────────────────────────────────────────────────────
XLSX_HEADERS = ["asset_name", "counterparty_sector", "nace_code", "country", "immovable_collateral", "instrument_type",
                "outstanding_loan_balance_eur", "counterparty_ref", "counterparty_total_liabilities_eur",
                "counterparty_total_liabilities_date", "residual_maturity_years", "ifrs9_stage", "accumulated_impairment_eur",
                "ghg1", "ghg2", "ghg3", "epc_label", "ep_score_kwh_m2", "taxonomy_status", "taxonomy_objective",
                "headline_hazard", "headline_score"]


def xlsx_rows(payload: dict) -> list[list]:
    """The frozen book as the templates read it, one exposure per row (the templates follow as blocks)."""
    return [[a.get(h) for h in XLSX_HEADERS] for a in payload.get("assets") or []]


# ── confirm-data step ─────────────────────────────────────────────────────────
def preflight(session, org_id, basis: dict, entity_ids=None, value_weights=None, translation=None) -> dict:
    """Over exactly the book the filing will freeze: how many exposures are scored (Template 5 reads the scores) and how
    many state the gross carrying amount every template amount is. No book-level at-risk figure: no template prints one."""
    from services.governance.pillar3_grids import no_gross
    p = freeze(session, org_id, basis["scenario"], basis["horizon"], entity_ids, value_weights, translation)
    r, assets = p["rollup"], p["assets"]
    n_total, n_done = r["n_assets"], r["n_scored"]
    gaps = []
    if n_total and n_done < n_total:
        gaps.append(f"{n_total - n_done} of {n_total} exposures not yet scored — Template 5 cannot place them")
    missing = no_gross(assets)
    if missing:
        gaps.append(f"{missing} of {len(assets)} exposures state no gross carrying amount (outstanding balance) — they "
                    "sit in no template row")
    from services.governance import pillar3_t1 as T1
    gaps += [f"Template 1 columns i–k — {g}" for g in T1.gaps(p[T1.RECORD])]
    if T1.k_gap(p[T1.RECORD]):
        gaps.append(f"Template 1 column k — {T1.k_gap(p[T1.RECORD])}")
    st = (t1_total(p) or {}).get("stated") or {}
    for k, what in (("no_counterparty", "state emissions but no counterparty id"),
                    ("conflict", "belong to counterparties whose total liabilities are in conflict"),
                    ("unattributed", "have no counterparty total liabilities stated"),
                    ("s3_gap", "need a scope 3 that is neither gathered nor given by a stated sector-average intensity")):
        if st.get(k):
            gaps.append(f"Template 1 columns i–k — {st[k]} exposures {what}")
    gaps += [f"Template 1 narrative not authored: {n['prompt']}" for n in T1.missing_narrative(p[T1.RECORD])]
    if p.get("qualitative") is not None:
        import services.regspec as R
        from services.governance.pillar3_qualitative import unanswered
        left = unanswered(R.governing("bank_p3esg", period_end=p[T1.RECORD]["reference_date"]), p["qualitative"])
        if left:
            gaps.append(f"Qualitative Tables 1–3: {len(left)} row(s) not answered for this institution and reference date "
                        f"({', '.join(left[:6])}{' …' if len(left) > 6 else ''})")
    return {"coverage": {"label": "exposures scored", "done": n_done, "total": n_total,
                         "pct": round(100 * n_done / n_total, 1) if n_total else 0},
            "total_value_eur": r["total_value_eur"], "value_at_risk_eur": None, "noun": "exposures", "gaps": gaps}
