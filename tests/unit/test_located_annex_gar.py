"""The bank TCFD located annex must render the FULL Green Asset Ratio grid (Templates 6–8, by
counterparty class) when a per-asset book is present — the same grid Pillar 3 renders — not the flat
eligibility summary. Falls back to the flat summary only when there is no per-asset book. Pure."""
from services.governance.filing_annex import (
    _gar_grid_section,
    _located_annex,
    _p3esg_annex,
)

_ASSETS = [
    {"nace_code": "C25", "outstanding_loan_balance_eur": 2_000_000_000, "taxonomy_status": "eligible"},
    {"nace_code": "C25", "outstanding_loan_balance_eur": 200_000_000, "taxonomy_status": "aligned"},
    {"nace_code": "T97", "outstanding_loan_balance_eur": 30_000_000, "taxonomy_status": ""},  # household
    {"nace_code": "O84", "outstanding_loan_balance_eur": 500_000_000, "taxonomy_status": ""},  # govt (excluded)
]


def _gar(sections):
    return next((s for s in sections if "green asset ratio" in s["title"].lower()), None)


def test_bank_tcfd_renders_full_counterparty_grid_when_assets_present():
    secs = _located_annex({}, {"assets": _ASSETS})
    gar = _gar(secs)
    assert gar is not None
    # full grid → 4 columns (counterparty / gross / eligible / aligned), not the flat 3-col summary
    assert gar["columns"] == ["Counterparty class", "Gross carrying amount", "Taxonomy-eligible", "Taxonomy-aligned"]
    assert "counterparty" in gar["title"].lower()
    # general governments row is present and flagged as excluded from covered assets
    labels = " ".join(r["cells"][0]["text"] for r in gar["rows"]).lower()
    assert "general governments" in labels and "excluded from covered assets" in labels


def test_bank_tcfd_falls_back_to_flat_summary_without_assets():
    dps = {
        "taxonomy.eligible_value_eur": {"key": "taxonomy.eligible_value_eur", "label": "Eligible", "value": 1_000_000},
        "taxonomy.not_eligible_value_eur": {"key": "taxonomy.not_eligible_value_eur", "label": "Not eligible", "value": 500_000},
        "book.total_value_eur": {"key": "book.total_value_eur", "label": "Total", "value": 1_500_000},
    }
    secs = _located_annex(dps, {})  # no assets
    gar = _gar(secs)
    assert gar is not None
    assert gar["columns"] == ["KPI", "Amount", "% of covered assets"]  # the flat summary shape
    assert "summary" in gar["title"].lower()


def test_gar_grid_shared_helper_matches_between_bank_and_p3esg():
    # The same helper output feeds both annexes — the grid is identical.
    bank = _gar(_located_annex({}, {"assets": _ASSETS}))
    p3 = _gar(_p3esg_annex({}, {"assets": _ASSETS}))
    direct = _gar_grid_section(_ASSETS)
    assert bank["rows"] == p3["rows"] == direct["rows"]


def test_bank_taxonomy_renders_annexvi_t0_and_objective_axis():
    from services.governance.filing_annex import _located_annex
    secs = _located_annex({}, {"assets": _ASSETS})
    titles = " ".join(s["title"] for s in secs)
    assert "Template 0 — Summary of KPIs" in titles
    assert "by environmental objective" in titles
    t3 = next(s for s in secs if "by environmental objective" in s["title"])
    labels = [r["cells"][0]["text"] for r in t3["rows"]]
    # all six official objectives, in order
    assert labels[0] == "Climate change mitigation" and labels[1] == "Climate change adaptation"
    assert len(labels) == 6
    # the adaptation objective (the one we assess) carries a computed eligible amount, not a dash
    cca = t3["rows"][1]["cells"]
    assert cca[1]["text"] != "—"
    # a non-assessed objective is honestly declared "—"
    assert t3["rows"][0]["cells"][1]["text"] == "—"
