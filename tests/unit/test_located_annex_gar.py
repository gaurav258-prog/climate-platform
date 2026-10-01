"""The credit institution's EU Taxonomy Art. 8 filing (bank_tcfd) carries the templates of Annex VI (Del. Reg. 2021/2178)
in the version the filing was frozen under — every template, row for row from the specification
(services.governance.taxonomy_forms) — and nothing else (E95). A filing frozen under the earlier report shape shows the
sections it froze after the templates, marked. Pure."""
import services.regspec as R
from services.governance.bank_taxonomy_report import EARLIER, annex
from services.governance.filing_annex import _p3esg_annex
from tests.unit.test_taxonomy_gar import BOOK

V2026 = "da_2021_2178_as_amended_2026_73"
PAYLOAD = {"assets": BOOK, "reporting_period_end": "2025-12-31",
           "_specs": {"bank_taxonomy": {"framework": "bank_taxonomy", "version": V2026, "disclosed_on": "2026-04-30"}}}


def _gar(sections):
    return next((s for s in sections if s.get("key") == "gar"), None)


def test_bank_tcfd_renders_every_template_of_the_frozen_version_and_nothing_else():
    secs = annex({}, PAYLOAD)
    assert all((s.get("spec") or {}).get("framework") == "bank_taxonomy" for s in secs)
    spec = R.load("bank_taxonomy", V2026)
    tids = {s["spec"]["template"] for s in secs}
    assert tids == {t["id"] for t in spec["templates"]}
    # Templates 1-4 twice (turnover-based and CapEx-based), titled from the specification
    t1 = [s for s in secs if s["spec"]["template"] == "T1"]
    assert {s["spec"]["basis"] for s in t1} == {"turnover", "capex"}
    assert all(R.template(spec, "T1")["title"] in s["title"] for s in t1)
    # every printed row of Template 1 is on the form, in order
    assert len([r for r in t1[0]["rows"] if r["type"] == "row"]) == len(R.template(spec, "T1")["rows"])


def test_entered_cells_are_offered_for_supply_with_their_basis():
    secs = annex({}, PAYLOAD)
    t1c = next(s for s in secs if s.get("key") == "taxonomy_t1_capex")
    keys = [c["key"] for r in t1c["rows"] if r["type"] == "row" for c in r["cells"] if c.get("supply")]
    assert keys and all(k.startswith("T1@capex.") for k in keys)          # financial guarantees, AuM … per basis
    t5 = next(s for s in secs if s["spec"]["template"] == "T5")
    assert "Entered by the institution" in t5["note"]


def test_an_earlier_shape_filing_without_a_book_keeps_its_flat_summary_marked():
    dps = {
        "taxonomy.eligible_value_eur": {"key": "taxonomy.eligible_value_eur", "label": "Eligible", "value": 1_000_000},
        "taxonomy.not_eligible_value_eur": {"key": "taxonomy.not_eligible_value_eur", "label": "Not eligible", "value": 500_000},
        "book.total_value_eur": {"key": "book.total_value_eur", "label": "Total", "value": 1_500_000},
    }
    gar = _gar(annex(dps, {"taxonomy": {"eligible": {"value_eur": 1_000_000}}}))
    assert gar is not None and gar["columns"] == ["KPI", "Amount", "% of covered assets"]
    assert gar["title"].startswith(EARLIER)
    assert annex(dps, {}) == []                       # the current shape prints no flat summary — only templates


def test_pillar3_reports_the_gar_in_template_7():
    p3 = _p3esg_annex({}, {"assets": BOOK})
    assert _gar(p3) is None and any(s.get("key") == "t7" for s in p3)
