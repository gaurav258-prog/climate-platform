"""Engagement flows are configuration: every kind has an ordered flow, the entity can only take its own steps,
the supervisor closes and can reopen, and a finding needs a severity."""
import pytest

from services.supervision.engagement import allowed_next, kinds, status_label, transition_allowed


def test_every_kind_has_a_flow_that_starts_open_and_ends_closed():
    for k, v in kinds().items():
        assert v["statuses"][0] == "open" and v["closed"] == v["statuses"][-1] == "closed", k
        assert set(v["entity_sets"]) <= set(v["statuses"]) and set(v["supervisor_sets"]) <= set(v["statuses"]), k
        assert "closed" not in v["entity_sets"], f"{k}: only the supervisor closes"
        assert status_label(v["statuses"][0]) == "Open"


@pytest.mark.parametrize("kind", ["information_request", "finding"])
def test_entity_cannot_close_and_supervisor_cannot_answer_for_the_entity(kind):
    assert not transition_allowed(kind, "open", "closed", "entity")
    assert transition_allowed(kind, "open", "closed", "supervisor")
    assert transition_allowed(kind, "closed", "open", "supervisor")           # reopen
    first_entity_step = allowed_next(kind, "entity")[0]
    assert transition_allowed(kind, "open", first_entity_step, "entity")
    assert not transition_allowed(kind, "open", first_entity_step, "supervisor")
    assert not transition_allowed(kind, "open", "open", "supervisor")         # no no-op moves


def test_finding_flow_reaches_remediated_before_close():
    f = kinds()["finding"]
    assert f["statuses"] == ["open", "remediation_planned", "remediated", "closed"] and f["severities"]
