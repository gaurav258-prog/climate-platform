"""S.27.01.04 — a group's natural catastrophe risk (ITS (EU) 2023/894 Art. 34(1)(s); Annex I; instructions Annex III
S.27.01) — on the specification, in EIOPA's taxonomy under the group entry point (arg), and refused where the group's
method of calculating group solvency leaves no template to report (services.governance.group_solvency)."""
from __future__ import annotations

import json
from datetime import date

import pytest

import services.regspec as R
from core import messages
from services.governance import group_solvency as G
from services.governance import s2701
from services.governance import s2701_xbrl as X
from services.governance.datapoint_catalog import CATALOG
from services.governance.insurer_solvency import KEY
from services.governance.solvency2_natcat import natcat_scr

SPEC = R.load(s2701.FAMILY, "its_2023_894")
SOLO, GROUP = R.template(SPEC, s2701.TID), R.template(SPEC, s2701.GROUP_TID)


def test_annex_i_prints_s2704_as_s2701_and_annex_iii_names_the_same_cells():
    assert GROUP["code"] == "S.27.01.04" and "Annex III section S.27.01" in GROUP["ref"]
    assert "Article 34(1), point (s)" in GROUP["legal_basis"]["article"] and "S.27.01.04" in GROUP["legal_basis"]["quote"]
    for axis in ("rows", "columns", "blocks", "out_of_scope_blocks"):
        assert GROUP[axis] == SOLO[axis], axis
    refs = [i["ref"] for i in GROUP["instructions"] if not i["ref"].startswith("Annex")]
    assert refs == [i["ref"] for i in SOLO["instructions"] if not i["ref"].startswith("Annex")] and len(refs) == 137
    assert s2701.reportable(SPEC, s2701.GROUP_TID) == s2701.reportable(SPEC, s2701.TID) and len(s2701.reportable(SPEC)) == 710
    assert set(s2701.binding(SPEC)) == {"S2701", "S2704"} and R.coverage(SPEC, s2701.binding(SPEC))["complete"]
    assert R.validate({k: v for k, v in SPEC.items() if not k.startswith("_")}) == []


def test_the_group_requirements_are_quoted_and_the_two_misprinted_refs_are_placed_on_the_record():
    general = [i["quote"] for i in GROUP["instructions"] if i["ref"] == "Annex III S.27.01 General comments"]
    assert any(q.startswith("This information is applicable when method 1") for q in general)
    assert any(q.startswith("When combination method is being used, this information is to be submitted only for the part")
               for q in general)
    assert "This information does not apply to groups when method 2 as defined in Article 233 of Directive 2009/138/EC is " \
           "being used exclusively." in general
    printed = {i["ref"]: i for i in GROUP["instructions"] if "printed_ref" in i}
    assert {r: i["printed_ref"] for r, i in printed.items()} == {"C0260/R1400": "C0260/1400", "C0360/R1920": "C0360/R1820"}
    for i in printed.values():                    # placed by the item's own name and EIOPA's table, both on the record
        assert "EIOPA's S.27.01.04 table" in i["ref_basis"] and "Q&A" in i["ref_basis"]
    assert any("group" in i["quote"] for i in GROUP["instructions"] if i["ref"] == "C0020/R0010")   # Annex III's wording


@pytest.mark.parametrize("version", ["2.8.2", "2.10.0"])
def test_each_group_cell_is_the_solo_data_point_with_the_two_group_members(version):
    solo, group = X._load(version), X._load(version, "s2704_xbrl")
    assert group["template"] == "S.27.01.04" and group["entry_point"].endswith("/mod/arg.xsd")
    assert solo["entry_point"].endswith("/mod/ars.xsd") and group["package"] == solo["package"]
    members = {d: m["member"] for d, m in group["group_members"].items()}
    assert members == {"s2c_dim:CM": "s2c_CS:x1", "s2c_dim:SO": "s2c_SE:x44"}
    assert set(group["cells"]) == set(solo["cells"])
    for k, c in group["cells"].items():
        want = dict(solo["cells"][k]["dims"], **(members if solo["cells"][k]["dims"] else {}))   # R0002: no dimension
        assert (c["concept"], c["datatype"], c["dims"]) == (solo["cells"][k]["concept"], solo["cells"][k]["datatype"], want), k
        assert c["table"] == solo["cells"][k]["table"].replace("S.27.01.01", "S.27.01.04")
    assert set(group.get("rows_added_after_its_2023_894") or {}) == set(solo.get("rows_added_after_its_2023_894") or {})
    if version == "2.8.2":                        # EIOPA's list of switched-off rules for the group entry point
        assert group["deactivations"]["url"] == "https://dev.eiopa.europa.eu/Taxonomy/Full/deactivations/282/arg-ignore-val.xml"
        assert group["deactivations"]["bytes"] == 12674 and len(group["deactivations"]["sha256"]) == 64
    else:
        assert group["deactivations"] is None and "404" in group["deactivations_note"]


def _payload(st: dict | None) -> dict:
    sf = natcat_scr([{"country": "DE", "postal_code": "01067", "sum_insured_eur": 1e8}], ref_date=date(2025, 12, 31))
    p = {KEY: {"standard_formula_natcat": sf}, "_specs": {s2701.FAMILY: {"version": "its_2023_894"}},
         "_provided_attested": [{"key": "provided.S2704.R0750.C0040", "value": 5e6},
                                {"key": "provided.S2701.R0750.C0040", "value": 7e6}]}
    return {**p, "_group_solvency": st} if st is not None else p


def _st(**kw) -> dict:
    return {"group_entity_id": "g", "group_name": "Group", "period_end": "2025-12-31", "method": "method_1",
            "status": "complete", "undertakings": [], "not_stated": [], "nested": [], "excluded_from_template": [], **kw}


def test_a_group_filing_reports_s2704_under_arg_and_reads_its_own_cells():
    p = _payload(_st(method="combination"))
    assert s2701.tid_of(p) == "S2704" and s2701.tid_of(_payload(None)) == "S2701"
    from services.governance.filing_annex import _supplied
    g = s2701.grid(SPEC, p[KEY]["standard_formula_natcat"], _supplied(p), "S2704")
    assert g["R0750"]["C0040"] == 5e6                                # the group's S.27.01.04 cell, never the solo one
    xml = X.instance(p, {"lei": "5299000J2N45DDNE4Y28", "name": "Group", "note": "test"}, "consolidated")
    assert "/mod/arg.xsd" in xml and "s2c_CS:x1" in xml and "s2c_SE:x44" in xml and "S.27.01.04 natural catastrophe" in xml
    solo = X.instance(_payload(None), {"lei": "5299000J2N45DDNE4Y28", "name": "Solo", "note": "test"}, "solo")
    assert "/mod/ars.xsd" in solo and "s2c_CS" not in solo


@pytest.mark.parametrize("st,code", [
    (None, "filing.refused.xbrl_group_refresh"),
    (_st(method=None, status="not_stated", not_stated=["Re"]), "filing.refused.xbrl_group_not_stated"),
    (_st(method="method_2"), "filing.refused.xbrl_group_method_two"),
    (_st(status="nested", nested=[{"undertaking": "A", "held_through": "B"}]), "filing.refused.xbrl_group_nested"),
    (_st(method=None, status="no_related", undertakings=[]), "filing.refused.xbrl_group_no_related"),
])
def test_a_group_without_a_method_1_part_is_refused_with_its_reason(st, code):
    with pytest.raises(X.XbrlError) as e:
        X.instance(_payload(st), {"lei": "x", "name": "x", "note": "x"}, "consolidated")
    assert e.value.code == code
    r = messages.render(code, **e.value.params)
    assert r["label"] and "{" not in r["detail"]["what"]           # every value filled in the customer's words


def test_a_combination_leaves_the_method_2_books_out_and_nothing_else():
    w = {"g": 1.0, "a": 1.0, "b": 0.6, "b_branch": 0.6}
    assert G.part_weights(w, _st(method="combination", excluded_from_template=["b", "b_branch"])) == \
        {"g": 1.0, "a": 1.0, "b": 0.0, "b_branch": 0.0}
    assert G.part_weights(w, _st(method=None, status="not_stated")) == w


def test_the_statement_is_a_closed_choice_per_related_undertaking():
    dp = next(d for d in CATALOG["insurer_solvency"] if d["key"] == G.KEY)
    assert dp["unit"] == "choice" and dp["breakdown"] == "related_undertaking" and dp["choices"] == G.CHOICES
    for code in ("disclose.provided.choice", "disclose.provided.group_only", "disclose.provided.not_related"):
        assert messages.render(code, figure="x", choices="y")["label"]
    assert json.loads(open("data/reference/messages.en.json").read())["messages"]["filing.refused.xbrl_group_method_two"]


def test_every_quote_of_the_nat_cat_spec_is_the_acts_own_wording():
    """Each quote — legal bases, every S.27.01.01 and S.27.01.04 instruction — is found word for word in ITS (EU) 2023/894
    as retrieved from the Publications Office (data/sources/legal/32023R0894); a misprinted ref is printed so in Annex III."""
    from services.reference import legal_texts as L
    quotes = [SPEC["legal_basis"]["quote"], GROUP["legal_basis"]["quote"]] + \
        [i["quote"] for t in (SOLO, GROUP) for i in t["instructions"]]
    assert len(quotes) == 285 and [q for q in quotes if L.contains(q) != "32023R0894"] == []
    for i in (i for i in GROUP["instructions"] if "printed_ref" in i):
        assert L.contains(f"{i['printed_ref']} {i['item']} {i['quote'][:60]}") == "32023R0894", i["printed_ref"]
