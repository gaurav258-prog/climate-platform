"""Pure-logic tests: a pending approval loses its policy → it is withdrawn, never applied, never left decidable.

The gate re-run (`still_requires_approval`) must mirror the submit gate (`needs_approval` + the value threshold)
for EVERY governed action — one mechanism, configuration-driven — not just config.kri_appetite.
"""
from services.governance.approval_policy_sweep import (
    AUDIT_ACTION,
    POLICY_OFF_CAUSE,
    changed_fields_of,
    still_requires_approval,
    withdrawal_reason,
)

ON = {"requires_approval": True, "material_fields": [], "threshold_eur": None}
OFF = {"requires_approval": False, "material_fields": [], "threshold_eur": None}

APPETITE = {"framework": "bank_tcfd", "kri_key": "flood_exposure_pct", "reason": "board review", "amber": 12.0,
            "_maker": "u1", "_request_id": "r1"}


def test_kri_appetite_off_is_withdrawn():
    assert still_requires_approval(ON, "config.kri_appetite", APPETITE) is True
    assert still_requires_approval(OFF, "config.kri_appetite", APPETITE) is False


def test_changed_fields_ignore_governance_bookkeeping_keys():
    # _maker/_request_id are stamped on the payload by the submit path, they are not "changes"
    assert changed_fields_of("config.kri_appetite", APPETITE) == ["framework", "kri_key", "reason", "amber"]


def test_material_fields_narrowing_withdraws_non_material_requests():
    pol = {"requires_approval": True, "material_fields": ["red"], "threshold_eur": None}
    assert still_requires_approval(pol, "config.kri_appetite", APPETITE) is False     # amber only → no longer material
    assert still_requires_approval(pol, "config.kri_appetite", {**APPETITE, "red": 20.0}) is True


def test_same_mechanism_for_every_governed_action():
    site_update = {"target_id": "s1", "changes": {"name": "Depot North"}}
    site_delete = {"target_id": "s1"}
    reporting = {"scenario": "ssp245", "horizon": "2030"}
    calc = {"var_method": "historical"}
    decision = {"decision_id": "d1", "entity_id": "e1", "action": "reprice"}
    for rt, payload in [("supply.site.update", site_update), ("supply.site.delete", site_delete),
                        ("supply.plot.update", {"target_id": "p1", "changes": {"latitude": 41.0}}),
                        ("supply.plot.delete", {"target_id": "p1"}),
                        ("config.reporting_settings", reporting), ("config.calc_settings", calc),
                        ("risk.decision", decision)]:
        assert still_requires_approval(ON, rt, payload) is True, rt
        assert still_requires_approval(OFF, rt, payload) is False, rt


def test_supply_update_uses_the_changes_block_and_material_fields():
    pol = {"requires_approval": True, "material_fields": ["latitude", "longitude"], "threshold_eur": None}
    assert still_requires_approval(pol, "supply.site.update", {"target_id": "s1", "changes": {"name": "x"}}) is False
    assert still_requires_approval(pol, "supply.site.update", {"target_id": "s1", "changes": {"latitude": 1}}) is True
    # a delete has no fields — governed iff the rule is on
    assert still_requires_approval(pol, "supply.site.delete", {"target_id": "s1"}) is True
    assert changed_fields_of("supply.site.delete", {"target_id": "s1"}) is None


def test_value_threshold_raised_above_the_request():
    pol = {"requires_approval": True, "material_fields": [], "threshold_eur": 5_000_000.0}
    assert still_requires_approval(pol, "risk.decision", {"decision_id": "d", "value_eur": 1_000_000}) is False
    assert still_requires_approval(pol, "risk.decision", {"decision_id": "d", "value_eur": 9_000_000}) is True
    # value unknown on the request → stays governed (conservative: never withdraw on a guess)
    assert still_requires_approval(pol, "risk.decision", {"decision_id": "d"}) is True


def test_empty_change_never_needs_approval():
    assert still_requires_approval(ON, "config.calc_settings", {}) is False


def test_reason_names_the_policy_switch_and_says_not_applied():
    r = withdrawal_reason("Change a risk-appetite band", "admin@meridian.demo", "2026-09-12 10:00 UTC")
    assert "Policy no longer requires approval" in r
    assert "admin@meridian.demo" in r and "2026-09-12 10:00 UTC" in r
    assert "NOT applied" in r
    assert withdrawal_reason("x", None, "t").count("an administrator") == 1


def test_constants_are_the_api_contract():
    assert POLICY_OFF_CAUSE == "policy_no_longer_requires_approval"
    assert AUDIT_ACTION == "approval.withdrawn_by_policy"
