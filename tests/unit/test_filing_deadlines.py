"""A filing deadline has one home: the mandate's cited rule (data/reference/regulatory_mandates.json). The report-type
registry keeps a planning date only where no mandate fixes one by the calendar — never a second copy that can disagree
(it did: insurer_solvency 30 April against Art. 312's 14 weeks; three more report types)."""
from datetime import date

from services.governance.filings import FRAMEWORKS, due_for
from services.supervision.mandates import due_date, registry


def test_no_report_type_types_a_deadline_its_mandate_fixes():
    for m in registry()["mandates"]:
        fw = (m.get("deliverable") or {}).get("framework")
        if fw in FRAMEWORKS and due_date(m, date(2025, 12, 31)) is not None:
            assert not FRAMEWORKS[fw].get("due"), f"{fw}: the deadline is the mandate's ({m['id']}), not typed"


def test_the_deadlines_the_acts_set():
    pe = date(2025, 12, 31)
    assert due_for("insurer_solvency", pe)[0] == date(2026, 4, 8)            # 14 weeks (Art. 312 Del. Reg. 2015/35)
    assert due_for("bank_p3esg", pe)[0] == date(2026, 4, 30)                 # with the annual report, 4 months
    assert due_for("sfdr_pai", pe)[0] == date(2026, 6, 30)                   # 30 June (Art. 4 RTS 2022/1288)
    assert due_for("insurer_climate", pe)[1].endswith("planning date")       # runs from the ORSA's conclusion
    assert due_for("sfdr_precontractual", pe) == (None, None)


def test_no_nat_cat_template_is_called_s2601():
    """Nat-cat is S.27.01.01; S.26.01 is market risk (E39). Only the reader of filings frozen under the old key names it."""
    import pathlib
    hits = []
    for root in ("services", "api", "web/src", "data/reference", "scripts"):
        for f in pathlib.Path(root).rglob("*"):
            if f.suffix in (".py", ".ts", ".tsx", ".json") and "S.26.01" in f.read_text(errors="ignore"):
                hits.append(str(f))
    assert hits == ["services/governance/insurer_solvency.py"], hits
