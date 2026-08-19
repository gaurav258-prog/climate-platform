"""The snapshot content hash must be deterministic and order-independent (audit T1).

The tamper-evidence of a filed snapshot rests on `payload_sha256` being reproducible: the same content
must always hash the same, regardless of dict key order, so a later re-hash can detect any change.
"""
from services.governance.report_snapshots import _canonical, _sha256


def test_canonical_is_order_independent():
    a = {"b": 1, "a": 2, "nested": {"y": 9, "x": 8}, "list": [3, 1, 2]}
    b = {"a": 2, "list": [3, 1, 2], "nested": {"x": 8, "y": 9}, "b": 1}
    assert _canonical(a) == _canonical(b)
    assert _sha256(a) == _sha256(b)


def test_hash_changes_on_any_content_change():
    base = {"x": 1, "y": [1, 2, 3]}
    assert _sha256(base) != _sha256({"x": 2, "y": [1, 2, 3]})   # value change
    assert _sha256(base) != _sha256({"x": 1, "y": [1, 2]})      # list change
    assert _sha256(base) == _sha256({"y": [1, 2, 3], "x": 1})   # reorder only → same
