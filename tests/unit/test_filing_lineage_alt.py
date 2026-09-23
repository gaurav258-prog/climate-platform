"""Every framework outside filing_lineage._LIST_CFG must point to a real alternate lineage mechanism, not a
bare 'not supported' — closes a gap an independent architecture review flagged as unverified (2026-09-23):
sfdr_pai / csrd_e1 / esrs_pack / reit_taxonomy / insurer_solvency all genuinely have one, just not through
this spatial-cell endpoint."""
from __future__ import annotations

from services.governance.filing_lineage import _ALT_LINEAGE, _LIST_CFG
from services.governance.filings import FRAMEWORKS


def test_every_framework_not_in_list_cfg_has_an_alt_lineage_message():
    uncovered = set(FRAMEWORKS) - set(_LIST_CFG) - set(_ALT_LINEAGE)
    assert not uncovered, f"framework(s) with neither spatial nor alternate lineage documented: {uncovered}"


def test_list_cfg_and_alt_lineage_dont_overlap():
    # a framework is either spatially traced here, or points elsewhere — never both/ambiguous
    assert not (set(_LIST_CFG) & set(_ALT_LINEAGE))
