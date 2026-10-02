"""E112 guard: every framework's assurance pack states its own basis of preparation — its own label and legal basis, never
another framework's — and no report type falls back to a shared text."""
import pytest

from services.governance.assurance_methodology import FAMILY_OF, methodology, principle
from services.governance.filings import FRAMEWORKS


def _md(rt: str) -> str:
    return methodology(rt, version=1, entity="Entity X", basis_text="period 2025-12-31", period_end="2025-12-31", generated="2026-10-02T00:00:00",
                       contents="- `report.json`")


def _family(rt: str) -> str:
    return FAMILY_OF.get(rt) or f"retired:{rt}"


@pytest.mark.parametrize("rt", sorted(FRAMEWORKS))
def test_each_framework_names_its_own_framework_and_no_other(rt):
    md = _md(rt)
    fw = FRAMEWORKS[rt]
    assert fw["label"] in md and fw["basis"] in md and f"{rt} v1" in md
    for other, ofw in FRAMEWORKS.items():
        if _family(other) == _family(rt):
            continue
        assert ofw["label"] not in md, f"{rt}'s basis of preparation names {other}'s framework"
        assert ofw["basis"] not in md, f"{rt}'s basis of preparation cites {other}'s legal basis"
    assert principle(rt) and "None" not in md


@pytest.mark.parametrize("rt", sorted(FRAMEWORKS))
def test_only_the_esrs_statement_speaks_of_esrs_and_only_eudr_of_plots(rt):
    """The defect E112 fixed: the ESRS / agriculture text (sites and sourcing plots, the r² floor) on every filing."""
    md = _md(rt).replace(FRAMEWORKS[rt]["label"], "").replace(FRAMEWORKS[rt]["basis"], "")   # the text, past its own name
    if rt not in ("esrs_pack", "csrd_e1"):
        assert "ESRS" not in md and "CSRD" not in md
    if rt not in ("eudr_dds", "eudr_simplified"):           # Annex II point 3 and Annex III point 3 are about the plots
        assert "plot" not in md.lower()
    assert "r² >= 0.40" not in md and "r2 >= 0.40" not in md


def test_every_active_framework_has_a_family_and_every_family_a_framework():
    active = {rt for rt, fw in FRAMEWORKS.items() if not fw.get("retired")}
    assert active == set(FAMILY_OF)


def test_a_retired_report_says_so_and_describes_no_engine():
    for rt in (rt for rt, fw in FRAMEWORKS.items() if fw.get("retired")):
        md = _md(rt)
        assert "This report type is retired" in md and "How the figures are produced" not in md


def test_an_unknown_report_type_is_refused_not_given_a_default_text():
    with pytest.raises(ValueError):
        _md("no_such_report")
    with pytest.raises(ValueError):
        principle("no_such_report")


def test_principles_print_on_the_pdf_cover():
    for rt in FRAMEWORKS:
        principle(rt).encode("latin-1")


def test_the_pack_has_no_text_of_its_own():
    """The pack takes its basis of preparation and cover line from the one module, per report type."""
    import inspect

    import services.governance.assurance_pack as pack
    src = inspect.getsource(pack)
    assert "_METHODOLOGY" not in src and "_methodology(snap[\"report_type\"]" in src and "_principle(snap[\"report_type\"])" in src
