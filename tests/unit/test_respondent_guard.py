"""A respondent account can reach only the supervisory portal's routes — enforced once, in the user dependency."""
from api.deps import RESPONDENT_PATHS


def test_respondent_allowlist_is_the_portal_and_nothing_else():
    assert "/v1/me/supervisors" in RESPONDENT_PATHS and "/v1/auth/" in RESPONDENT_PATHS
    for forbidden in ("/v1/me/globe", "/v1/supervisor", "/v1/bank", "/v1/admin/users", "/v1/lookup"):
        assert not forbidden.startswith(RESPONDENT_PATHS)
