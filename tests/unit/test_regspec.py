"""The regulatory-change route's machinery: every spec file valid, the machine diff, which version governs, coverage."""
import copy

import pytest

import services.regspec as R
from services.regspec.bindings import binding_for


def test_every_spec_file_is_valid_and_matches_its_path():
    for fw in R.frameworks():
        for s in R.versions(fw):                       # load() validates and checks framework/version against the path
            assert s["_sha256"] and len(s["_sha256"]) == 64


def test_every_adopted_spec_is_fully_covered_by_its_binding():
    for fw in R.frameworks():
        for s in R.versions(fw):
            b = binding_for(fw, s)
            if s["status"] == "adopted" and b is not None:
                cov = R.coverage(s, b)
                assert cov["complete"], (s["version"], cov)


def test_pillar3_2022_to_2024_changed_references_and_four_printed_cells():
    d = R.diff(R.load("bank_p3esg", "its_2022_2453"), R.load("bank_p3esg", "its_2024_3172"))
    assert d["kind"] == "wording"                                   # no row or column added, removed or moved
    assert not d["templates_added"] and not d["templates_removed"]
    reworded = {(c["id"], a, x["id"]) for c in d["changed"] for a in ("rows", "columns") for x in (c.get(a) or {}).get("relabelled", [])}
    assert reworded == {("T4", "columns", "b"), ("T6", "columns", "c4"), ("T7", "rows", "25"), ("T8", "rows", "9"),
                        ("T8", "rows", "11")}                        # the 2024 print shortens these cells (second pass)
    assert d["act"] == {"from": "32022R2453", "to": "32024R3172"}


def test_the_eba_draft_is_a_template_change_and_never_governs():
    d = R.diff(R.load("bank_p3esg", "its_2024_3172"), R.load("bank_p3esg", "eba_its_2026_02_draft"))
    assert d["kind"] == "template change" and "T5" in d["templates_removed"] and "CRFR2" in d["templates_added"]
    assert R.governing("bank_p3esg", period_end="2027-12-31", disclosure_date="2027-06-30")["version"] == "its_2024_3172"


@pytest.mark.parametrize("disclosed, version", [("2024-06-30", "its_2022_2453"), ("2025-03-31", "its_2024_3172")])
def test_pillar3_is_governed_by_the_disclosure_date(disclosed, version):
    assert R.governing("bank_p3esg", period_end="2024-12-31", disclosure_date=disclosed)["version"] == version


def test_coverage_names_a_new_row_and_a_stale_mapping():
    spec = copy.deepcopy(R.load("bank_p3esg", "its_2024_3172"))
    t5 = R.template(spec, "T5")
    t5["rows"].append({"id": "14", "label": "New row"})
    t5["rows"] = [r for r in t5["rows"] if r["id"] != "12"]
    cov = R.coverage(spec, binding_for("bank_p3esg"))
    assert not cov["complete"] and "T5.rows.14" in cov["missing"] and "T5.rows.12" in cov["stale"]


def test_validation_refuses_unverified_text_in_an_adopted_spec():
    spec = copy.deepcopy(R.load("bank_p3esg", "its_2024_3172"))
    spec.pop("_sha256")
    spec["templates"][0]["title"] = "UNVERIFIED"
    assert any("UNVERIFIED" in e for e in R.validate(spec))
    spec["status"] = "draft"
    assert not any("UNVERIFIED" in e for e in R.validate(spec))


def test_every_xbrl_reference_names_a_column_the_spec_has():
    """Error log E10: the export's element map once cited Template 1 columns that do not exist."""
    import json
    import re
    from pathlib import Path
    spec = R.governing("bank_p3esg", period_end="2025-12-31")
    cfg = json.loads((Path(R.ROOT).parents[2] / "config" / "eba_p3esg_binding.json").read_text())
    for name, el in cfg["elements"].items():
        for tno, col in re.findall(r"Template (\d+), column ([a-p])\b", el["its_ref"]):
            ids = {c["id"] for c in R.template(spec, f"T{tno}")["columns"]}
            assert col in ids, (name, el["its_ref"])


def test_the_xbrl_export_emits_exactly_the_listed_facts():
    """The element map file is the one list of facts: the export emits every listed fact and nothing else."""
    import re
    from pathlib import Path

    from services.governance.filing_export import p3esg_facts
    src = (Path(R.ROOT).parents[2] / "services" / "governance" / "filing_export.py").read_text()
    start = src.index("def _bank_p3esg_xbrl")
    end = src.find("\ndef ", start + 10)
    body = src[start:end if end > 0 else len(src)]
    emitted = set(re.findall(r'\bfact\("(\w+)"', body))
    assert emitted == set(p3esg_facts())
