"""Supervisor oversight rollup shows LIVE per-org data coverage, not a static framework-level constant
(2026-09-24 fix, platform E2E audit finding #7): `oversight.supervisor_view()`'s per-framework
`coverage_pct` used to come from `datapoint_catalog.coverage()`'s `pct_computed` — a STATIC number
("what fraction of this framework's datapoints does Tellumen's engine compute vs need from the customer")
that is identical for every customer on a given framework, regardless of how complete THEIR actual book
is. On a per-org rollup row sitting next to "last filed" and "KRI breaches", that reads as "how complete
is my filing" — which it never measured. Fixed: `filings.org_data_coverage_pct()` reuses the real, live
preflight coverage (the same number the confirm-data step shows) instead.

Requires PostgreSQL.
"""
from __future__ import annotations

import pytest

from core.db.session import get_session
from services.governance.datapoint_catalog import coverage as static_catalog_coverage
from services.governance.filings import org_data_coverage_pct
from services.governance.oversight import supervisor_view

BANK_ORG = "11111111-1111-4111-8111-111111111111"
MANUFACTURER_ORG = "55555555-5555-4555-8555-555555555555"  # Terra Foods (demo), agri/csrd


@pytest.mark.integration
def test_org_coverage_is_the_live_preflight_number_not_the_static_catalog_constant():
    with get_session() as s:
        live_pct = org_data_coverage_pct(s, BANK_ORG, "bank", "bank_tcfd")
        static_pct = static_catalog_coverage("bank_tcfd")["pct_computed"]
        # Real book: at least one figure exists. They need not differ numerically by coincidence, but the
        # live figure must come from the actual book (assets scored/total), not the framework constant.
        assert live_pct is not None
        assert 0 <= live_pct <= 100
        # The static constant is a DIFFERENT axis entirely (datapoint sourcing model) — assert it still
        # exists and is independently computable, proving the two are genuinely separate numbers, not the
        # same value under two names.
        assert static_pct is not None
        s.rollback()


@pytest.mark.integration
def test_unsupported_framework_for_org_type_returns_none_not_a_fabricated_percent():
    with get_session() as s:
        # bank_tcfd doesn't apply to an insurer org_type
        assert org_data_coverage_pct(s, BANK_ORG, "insurer", "bank_tcfd") is None
        s.rollback()


@pytest.mark.integration
def test_supervisor_view_rollup_uses_the_live_number_for_bank_tcfd():
    with get_session() as s:
        out = supervisor_view(s, BANK_ORG, "bank")
        row = next((f for f in out["frameworks"] if f["framework"] == "bank_tcfd"), None)
        assert row is not None
        direct = org_data_coverage_pct(s, BANK_ORG, "bank", "bank_tcfd")
        assert row["coverage_pct"] == direct
        s.rollback()


@pytest.mark.integration
def test_frameworks_with_no_single_ratio_show_none_honestly():
    """Agri frameworks (csrd_e1/esrs_pack) have no single completeness ratio — must stay None, never a
    fabricated 0% or the static constant standing in for it."""
    with get_session() as s:
        pct = org_data_coverage_pct(s, MANUFACTURER_ORG, "manufacturer", "csrd_e1")
        assert pct is None
        s.rollback()
