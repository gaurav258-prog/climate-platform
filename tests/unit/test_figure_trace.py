"""The figure trace's foundations (services.governance.figure_trace, figure_trace_s2701):

  one placement rule   the standard formula and the trace place a policy with the same function
                       (solvency2_natcat.placement): the policies placed in each region add up to the region's exposure
                       and count in the formula's own result, for every peril, on a book with every kind of policy
  the cell's law       every cell of S.27.01.01 and S.27.01.04 an instruction names is reportable and has that
                       instruction; a greyed cell has none (one parser of the refs, s2701._ref_cells)
  what a cell is       cell_of reads a region row, the other regions, a peril's total and the nat-cat total
  the graph            a group of nodes is capped and expands step by step; every edge joins two placed nodes
"""
from __future__ import annotations

from datetime import date

import pytest

import services.regspec as R
from services.governance import s2701
from services.governance import solvency2_natcat as N
from services.governance import solvency2_natcat_tables as T
from services.governance.figure_trace import CAP, STEP, Graph, parse_expand

SPEC = R.load("sii_qrt_natcat", "its_2023_894")

BOOK = [  # every kind of placement: zoned, unzoned, motor, outside Annex XIII, no country, not residential, no cover
    {"policy_id": "p1", "country": "ES", "postal_code": "46001", "sum_insured_eur": 4_000_000, "motor_sum_insured_eur": 200_000},
    {"policy_id": "p2", "country": "ES", "postal_code": None, "sum_insured_eur": 2_500_000},
    {"policy_id": "p3", "country": "PT", "postal_code": "1000", "sum_insured_eur": 1_200_000, "residential": True},
    {"policy_id": "p4", "country": "FR", "postal_code": "75001", "sum_insured_eur": 3_000_000, "residential": True},
    {"policy_id": "p5", "country": "FR", "postal_code": "13001", "sum_insured_eur": 900_000, "residential": False},
    {"policy_id": "p6", "country": "DE", "postal_code": "10115", "sum_insured_eur": 5_000_000},
    {"policy_id": "p7", "country": "US", "postal_code": None, "sum_insured_eur": 7_000_000},
    {"policy_id": "p8", "country": None, "sum_insured_eur": 800_000},
    {"policy_id": "p9", "country": "IT", "postal_code": "00100", "sum_insured_eur": 0},
    {"policy_id": "p10", "country": "GB", "postal_code": None, "sum_insured_eur": 1_500_000},
]


@pytest.mark.parametrize("ref_date", [date(2025, 12, 31), date(2027, 3, 31)])
@pytest.mark.parametrize("uk", N.UK_READINGS)
def test_the_policies_placed_in_a_region_add_up_to_the_formulas_region(ref_date, uk):
    v = T.version(ref_date)
    sf = N.natcat_scr(BOOK, ref_date=ref_date, uk_reading=uk)
    for peril, pr in sf["perils"].items():
        if not pr.get("available"):
            continue
        table = N.peril_table(v, peril)
        placed = [(pol, N.placement(pol, peril, v=v, table=table, uk_reading=uk)) for pol in BOOK]
        for line in pr["regions"]:
            members = [(p, a) for p, a in placed if a and not a.get("unlocated") and a.get("region") == line["region"]]
            assert len(members) == line["n_policies"], (peril, line["region"])
            assert round(sum(a["si"] for _, a in members)) == line["exposure_eur"], (peril, line["region"])
        other = [a for _, a in placed if a and a.get("other")]
        assert round(sum(a["si"] for a in other)) == ((pr.get("other_regions") or {}).get("exposure_eur") or 0), peril


@pytest.mark.parametrize("tid", [s2701.TID, s2701.GROUP_TID])
def test_every_reportable_cell_has_the_instruction_that_names_it(tid):
    t = R.template(SPEC, tid)
    ok = s2701.reportable(SPEC, tid)
    assert ok
    for row, col in ok:
        assert s2701.instructions_for(SPEC, tid, row, col), (row, col)
        assert s2701.cell_of(SPEC, tid, row, col)["reportable"]
    greyed = [(r["id"], c["id"]) for r in t["rows"][:40] for c in t["columns"][:12] if (r["id"], c["id"]) not in ok]
    assert greyed and all(not s2701.instructions_for(SPEC, tid, r, c) for r, c in greyed)


def test_what_a_cell_is():
    ws, col = s2701.REGION_ROW["windstorm"]["ES"], s2701.premium_column(SPEC)["windstorm"]
    c = s2701.cell_of(SPEC, "S2701", ws, "C0050")
    assert (c["peril"], c["row_role"], c["region"], c["column_role"], c["row_label"]) == \
        ("windstorm", "region", "ES", "exposure", "Kingdom of Spain")
    n, other_row = next(iter(s2701.other_region_rows(SPEC)["windstorm"].items()))
    o = s2701.cell_of(SPEC, "S2701", other_row, col)
    assert (o["row_role"], o["annex_iii_region"], o["column_role"]) == ("other_region", n, "premium")
    assert s2701.cell_of(SPEC, "S2701", "R0020", "C0010")["peril"] == "windstorm"      # the summary row of a peril
    tot = s2701.cell_of(SPEC, "S2701", "R0010", "C0030")
    assert (tot["peril"], tot["row_role"], tot["column_role"]) == (None, "nat_cat", "after")
    with pytest.raises(KeyError):
        s2701.cell_of(SPEC, "S2701", "R9999", "C0010")


def test_a_group_of_nodes_is_capped_and_expands_step_by_step():
    items = list(range(CAP + STEP + 3))
    shown, hidden = Graph().capped("policies", items)
    assert (len(shown), hidden) == (CAP, STEP + 3)
    shown, hidden = Graph({"policies": 1}).capped("policies", items)
    assert (len(shown), hidden) == (CAP + STEP, 3)
    assert Graph({"policies": 2}).capped("policies", items) == (items, 0)
    assert parse_expand(["policies-x:2", "bad", "y:", ":3", "z:9999"]) == {"policies-x": 2, "z": 400}


def test_the_graph_joins_only_placed_nodes_once():
    g = Graph()
    a = g.add("a", "law", "act")
    b = g.add("b", "spec", "spec")
    assert g.add("a", "law", "act") == a and len(g.nodes) == 2          # a node is placed once
    g.link(a, b)
    g.link(a, b)
    g.link(a, "nowhere")
    assert g.edges == [{"source": "a", "target": "b"}]
    assert g.more("policies", "book", 0, [a]) is None
    m = g.more("policies", "book", 5, [a])
    assert g.get(m)["facts"] == {"hidden": 5, "group": "policies"} and {"source": "a", "target": m} in g.edges
    with pytest.raises(ValueError):
        g.add("x", "elsewhere", "act")
