"""Every field a provided value's approval request holds is named in customer words (E356) — checked from the code, not
from the requests a database happens to hold: tests/integration/test_admin_platform_words.py reads stored requests only,
so the field E348 added (`filing_role`) went unnamed until the first request carrying it was stored.
"""
from __future__ import annotations

import ast
import inspect

from core import messages
from services.governance import approval_view, provided_data


def _payload_keys(fn) -> set[str]:
    tree = ast.parse(inspect.getsource(fn))
    return {k.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "payload" for t in n.targets) and isinstance(n.value, ast.Dict)
            for k in n.value.keys if isinstance(k, ast.Constant)}


def test_every_field_of_a_provided_values_request_is_named_or_hidden():
    keys = _payload_keys(provided_data.submit)
    assert {"provided_id", "framework", "filing_role"} <= keys
    named = messages.names()["admin.approval_field"]
    assert [k for k in keys if not approval_view._HIDDEN.search(k) and k not in named] == []


def test_a_reports_role_reads_in_words():
    rows = {d["label"]: d["value"] for d in approval_view.details("provided.datapoint", {"filing_role": "solo"})}
    assert rows == {"Which report": "The entity's own"}
    rows = {d["label"]: d["value"] for d in approval_view.details("provided.datapoint", {"filing_role": "consolidated"})}
    assert rows == {"Which report": "Consolidated"}
    assert approval_view.details("provided.datapoint", {"filing_role": None}) == []
