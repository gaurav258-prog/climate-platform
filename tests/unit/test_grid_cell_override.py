"""Task #56 — manual entry into an integrated grid cell must require a reason (4-eyes audit) and a cell key.

The full propose → maker-can't-self-approve → checker-approves → value-lands flow is a DB round-trip verified
end-to-end against the running API; here we lock the guard rails that run before any DB write."""
from __future__ import annotations

import pytest

from services.governance.filing_overrides import OverrideError, propose_grid_cell


def test_reason_required():
    with pytest.raises(OverrideError):
        propose_grid_cell(None, "org", "user", cell_key="t2.3.8", value="1000", reason="   ")


def test_cell_key_required():
    with pytest.raises(OverrideError):
        propose_grid_cell(None, "org", "user", cell_key="", value="1000", reason="a valid reason")
