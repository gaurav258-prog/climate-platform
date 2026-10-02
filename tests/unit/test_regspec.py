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


def _doc_spec(items):
    return {"framework": "x", "version": "v", "act": {"celex": "3"}, "status": "adopted", "legal_basis": {"article": "Art. 1", "templates_in": "Annex II",
                                                                                                 "instructions_in": "Annex II", "quote": "q"},
            "applies": {"from": "2023-01-01", "until": None, "basis": "disclosure_date"},
            "templates": [{"id": "AII", "title": "t", "ref": "r", "structure": "document", "items": items}]}


def test_a_document_template_is_validated_diffed_and_covered_by_item():
    """A template printed as a document to complete (SFDR Annexes II–V): items in reading order, each with a kind."""
    items = [{"id": "h", "kind": "heading", "label": "Environmental and/or social characteristics"},
             {"id": "q", "kind": "question", "label": "Does this financial product have a sustainable investment objective?", "parent": "h"},
             {"id": "q.yes", "kind": "choice", "label": "Yes", "parent": "q"},
             {"id": "d", "kind": "definition", "label": "Sustainable investment means …"}]
    old = _doc_spec(items)
    assert R.validate(old) == []
    assert R.validate(_doc_spec(items + [{"id": "z", "kind": "banner", "label": "x", "parent": "nope"}])) != []
    new = _doc_spec(items[:2] + [{**items[2], "label": "Yes, it does"}, items[3], {"id": "q.no", "kind": "choice", "label": "No", "parent": "q"}])
    d = R.diff(old, new)
    assert d["changed"][0]["items"]["added"] == ["q.no"] and d["changed"][0]["items"]["relabelled"][0]["id"] == "q.yes"
    assert d["kind"] == "template change"
    cov = R.coverage(new, {"AII": {"items": {"q": "computed", "q.yes": "computed"}}})
    assert cov["missing"] == ["AII.items.q.no"] and not cov["complete"]     # headings and definitions are printed, not bound
