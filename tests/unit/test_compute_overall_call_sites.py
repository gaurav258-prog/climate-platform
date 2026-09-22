"""_compute_overall's parameter was renamed exclude_hazards -> allow_nowcast, with inverted polarity, in
92b470d. api/routers/supply.py's hex_hazard() kept calling it with the OLD name, so every call to
GET /v1/supply/hex-hazard raised TypeError in production (found 2026-09-22, fixed the same day). No DB is
needed to catch this class of bug: a call with a keyword argument that no longer exists fails before any
query runs, so a stub session that never has to answer a real query is enough to reproduce it.
"""
import pytest

from api.routers.lookup import _compute_overall


class _StubSession:
    """Returns no rows for every query _compute_overall issues -- exercising the call, not the data."""
    def execute(self, *a, **k):
        class _R:
            def mappings(self_inner):
                return self_inner
            def all(self_inner):
                return []
        return _R()


def test_hex_hazard_style_call_succeeds():
    # the exact call hex_hazard() makes today (api/routers/supply.py) -- must not raise
    _compute_overall(_StubSession(), "8a1fb46622dffff")


def test_the_old_removed_kwarg_name_is_gone():
    # pins the rename so a future revert (or a copy-paste of the old call) fails loudly, not silently in prod
    with pytest.raises(TypeError):
        _compute_overall(_StubSession(), "8a1fb46622dffff", exclude_hazards=frozenset({"heat_acute"}))


def test_allow_nowcast_is_the_current_parameter_name():
    # must not raise: allow_nowcast is the live parameter every current call site uses
    _compute_overall(_StubSession(), "8a1fb46622dffff", allow_nowcast=frozenset({"heat_acute"}))
