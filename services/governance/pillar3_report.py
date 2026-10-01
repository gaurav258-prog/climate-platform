"""Pillar 3 ESG — report type `bank_p3esg` (ITS (EU) 2022/2453, as amended by ITS (EU) 2024/3172: Tables 1–3, Templates
1–10; the specs in data/reference/regspec/bank_p3esg). The filing prints what those templates print, nothing else (E97).

What a filing freezes: the banking book per exposure — the facts the templates read (pillar3_grids, pillar3_gar,
pillar3_other, transition_alignment), with each exposure's hazard scores (Template 5 reads them against the stated
at-risk level), without the climate-discounted valuation no template reads —; the book's count, scored count and total
(the engine run's checks); the counterparties' financed emissions (Template 1 columns i–j print financed emissions; the
PCAF-attributed figure is kept: the held spec quotes no instruction for those columns, so whether they ask for PCAF
attribution is not settled here — kept, and said so); the method record; plus the records every filing carries (_specs,
_fx, _consolidation, provided values …).

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
    from services.scoring.pcaf import attributed_financed_emissions
    assets, method = loan_book(session, org_id, scenario, horizon, entity_ids=entity_ids, value_weights=value_weights,
                               translation=translation, period_end=period_end)
    pcaf = attributed_financed_emissions(assets, exposure_key="outstanding_loan_balance_eur", evic_key="evic_eur",
                                         scope_keys=("ghg1", "ghg2", "ghg3"))
    book = [{k: v for k, v in a.items() if k not in NOT_FROZEN} for a in assets]
    # the method record says what the frozen figures read: the stated at-risk level, which makes an exposure sensitive
    # in Template 5 (a gap when not stated). The parameters only the valuation read are not recorded: it is not frozen.
    from services.money.params import for_org
    read = for_org(session, org_id, method.period_end)
    read.get("method.at_risk_level")
    return {"assets": book,
            "rollup": {"n_assets": len(book), "n_scored": sum(1 for a in book if a.get("headline_bucket")),
                       "total_value_eur": round(sum(a.get("value_eur") or 0 for a in book))},
            "financed_emissions_tco2e": pcaf["attributed"], "financed_emissions_pcaf": pcaf,
            "method": read.record()}


# ── form ──────────────────────────────────────────────────────────────────────
def form(payload: dict) -> list[dict]:
    """The filing's datapoints: the counterparties' financed emissions (Template 1 columns i–j) and the frozen book's size.
    A frozen earlier-shape filing also shows what it froze beyond them, each group marked as such (its keys unchanged,
    so its overrides still apply)."""
    from services.governance.filing_form import _dp, _located_book_form
    located = _located_book_form(REPORT, payload)
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
                "outstanding_loan_balance_eur", "residual_maturity_years", "ifrs9_stage", "accumulated_impairment_eur",
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
    return {"coverage": {"label": "exposures scored", "done": n_done, "total": n_total,
                         "pct": round(100 * n_done / n_total, 1) if n_total else 0},
            "total_value_eur": r["total_value_eur"], "value_at_risk_eur": None, "noun": "exposures", "gaps": gaps}
