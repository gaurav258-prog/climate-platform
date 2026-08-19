"""How much of each mandatory filing Tellumen can produce from the data it holds — the honest coverage map.

This is now DERIVED from the canonical datapoint catalog (`datapoint_catalog.py`), which is the single source
of truth for every datapoint's source-category and ingestion lane. The coverage buckets a customer sees map
from the lane:
  computed      — lane compute/granular (produced from your book + our physical/nature engine)
  integrated    — lane provided (a datapoint the regulator wants but that comes from outside — GHG, alignment,
                  EPC — you provide it / we reconcile it)
  client        — lane report (you author — narrative/governance/transition plan)
  out_of_scope  — no lane (not something this platform produces)

Keeping this thin wrapper preserves the existing `coverage()` contract while the catalog carries the detail.
"""
from __future__ import annotations

from services.governance.datapoint_catalog import coverage as _catalog_coverage


def coverage(framework: str) -> dict | None:
    """The section-by-section coverage of a filing + a summary — derived from the datapoint catalog."""
    return _catalog_coverage(framework)
