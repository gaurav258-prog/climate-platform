"""Forward-risk decisions and the reporting control register speak in the catalogue's words (UI standard, 2026-10-16):
every refusal they send a screen is an oversight.* catalogue code (or a shared error.* one), never the engine's own
sentence ("action must be one of (...)", "horizon must be 2030 / 2050 / 2100", "Missing permission: ops.oversee or
admin.audit.view"), and a figure that needs the at-risk level carries the one gap format the screens name
(services.money.params.Method.gap_text). No database."""
from __future__ import annotations

import ast
import re
from datetime import date
from pathlib import Path

import pytest

from core import messages
from core.errors import UserError

ROOT = Path(__file__).resolve().parents[2]
SERVER = sorted(p for d in ("api", "services") for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)


def _oversight_codes_in_code() -> set[str]:
    found, permissions = set(), set(messages.names()["admin.permission"])      # oversight.view is a permission, not a message
    for p in SERVER:
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"oversight(\.[a-z_]+)+", n.value) \
                    and n.value not in permissions:
                found.add(n.value)
    return found


def test_every_oversight_code_is_in_the_catalogue_and_every_catalogue_code_is_used():
    named, cat = _oversight_codes_in_code(), {c for c in messages.catalogue() if c.startswith("oversight.")}
    assert named, "the decisions and controls routers name no oversight code"
    assert named <= cat, f"codes the server raises that the catalogue lacks: {sorted(named - cat)}"
    assert cat <= named, f"catalogue codes no server code raises: {sorted(cat - named)}"
    assert not [p for p in messages.check() if p.startswith("oversight.")]


def test_each_decision_route_maps_the_one_refusal_its_engine_function_can_raise():
    """Each route turns DecisionError into one code; that is only right while each engine function raises it once."""
    tree = ast.parse((ROOT / "services" / "intelligence" / "forward_decisions.py").read_text(encoding="utf-8"))
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in ("crossings", "decide", "resolve_disclosure_flag", "resolve_watch"):
        raises = [r for r in ast.walk(fns[name]) if isinstance(r, ast.Raise) and isinstance(r.exc, ast.Call)
                  and getattr(r.exc.func, "id", None) == "DecisionError"]
        assert len(raises) == 1, f"{name} raises DecisionError {len(raises)} times — give each refusal its own code"


@pytest.fixture
def decisions(monkeypatch):
    import api.routers.decisions as R
    monkeypatch.setattr(R.D, "decision_policy", lambda *_: {"requires_approval": False, "threshold_eur": None})
    return R


CTX = {"org": {"org_id": "o", "type": "bank"}, "user": {"id": "u"}}


def _refused(fn, *a, **k) -> str:
    with pytest.raises(UserError) as e:
        fn(*a, **k)
    return e.value.code


def test_decision_refusals_are_catalogue_codes(decisions, monkeypatch):
    R = decisions
    assert _refused(R._vertical, {"org": {"type": "regulator"}}) == "oversight.decisions.unsupported"

    def refuse(*_a, **_k):
        raise R.D.DecisionError("engine words")
    for fn in ("crossings", "decide", "resolve_disclosure_flag", "resolve_watch"):
        monkeypatch.setattr(R.D, fn, refuse)
    monkeypatch.setattr("services.money.params.for_org", lambda *_: _method({"method.at_risk_level": 50.0}))
    assert _refused(R.crossings, None, "disorderly_2c", "2040", ctx=CTX) == "oversight.decisions.bad_horizon"
    body = R.DecideBody(entity_id="e", scenario="disorderly_2c", horizon="2050", action="shrug")
    assert _refused(R.decide, body, None, ctx=CTX) == "oversight.decisions.bad_action"
    assert _refused(R.resolve_flag, "f", None, status="kept", ctx=CTX) == "oversight.decisions.bad_flag_outcome"
    assert _refused(R.resolve_watch, "w", None, status="ignored", ctx=CTX) == "oversight.decisions.bad_watch_outcome"


def _method(values: dict):
    from services.money.params import Method
    return Method.of({(k, None): v for k, v in values.items()}, date(2025, 12, 31))


def test_crossings_without_a_stated_level_is_the_standard_gap(decisions, monkeypatch):
    monkeypatch.setattr("services.money.params.for_org", lambda *_: _method({}))
    r = decisions.crossings(None, "disorderly_2c", "2050", ctx=CTX)
    assert r["gap"] == "not stated: method.at_risk_level" and r["crossings"] == [] and r["at_risk_threshold"] is None


def test_the_adaptation_evidence_without_a_stated_level_is_the_standard_gap(monkeypatch):
    import services.intelligence.taxonomy_adaptation as T
    monkeypatch.setattr(T, "list_sites_with_risk", lambda *_: [])
    r = T.adaptation_kpi(None, "o", _method({}))
    assert r["physical_risk"]["gap"] == "not stated: method.at_risk_level"


def test_control_register_refusals_are_catalogue_codes(monkeypatch):
    import api.routers.controls as R
    assert _refused(R._reader, {"permissions": ["reports.view"]}) == "error.forbidden"
    assert _refused(R._regulated, {"org": {"type": "regulator"}}) == "oversight.controls.not_for_supervisors"
    ctx = {"org": {"org_id": "o", "type": "bank"}, "user": {"id": "u"}, "permissions": ["ops.oversee"]}
    assert _refused(R.put_owner, "C-NOPE-99", R.Owner(), None, ctx=ctx) == "error.not_found"

    def not_active(*_a, **_k):
        raise ValueError("The owner must be an active user of this organisation.")
    monkeypatch.setattr(R.C, "set_owner", not_active)
    control = R.C.register()["controls"][0]["id"]
    assert _refused(R.put_owner, control, R.Owner(owner_user_id="x"), None, ctx=ctx) == "oversight.controls.owner_not_active"


def test_the_routers_hand_no_engine_text_to_the_screen():
    for f in ("api/routers/decisions.py", "api/routers/controls.py"):
        src = (ROOT / f).read_text(encoding="utf-8")
        assert "HTTPException" not in src, f"{f} answers a refusal in its own words"
        assert "str(e)" not in src, f"{f} passes an exception's text to the screen"


def test_the_control_tower_receives_each_finding_in_the_catalogue_words(monkeypatch):
    """The exception feed dropped each finding's catalogue message, so the Control Tower could only print the sentence
    inline or a generic line; it now passes the message (its short label for the row, its detail behind the ⓘ)."""
    import services.governance.filing_validation as FV
    from services.governance.exception_monitor import exceptions

    class Rows(list):
        def mappings(self):
            return self

        def all(self):
            return list(self)

    calls = iter([Rows([{"filing_id": "f", "framework": "pillar3_esg", "period_label": "FY2025", "status": "draft"}]), Rows()])

    class Session:
        def execute(self, *_a, **_k):
            return next(calls)

    m = messages.render("error.not_found")
    monkeypatch.setattr(FV, "validate_filing", lambda *_: {"findings": [
        {"rule": "r", "category": "completeness", "severity": "blocking", "passed": False, "message": m["detail"]["what"], "msg": m}]})
    item = exceptions(Session(), "o")["exceptions"][0]
    assert item["msg"]["label"] == m["label"] and item["message"] == m["detail"]["what"]


STORED_ITEMS = [   # every shape services/governance/controls.py has stored in control_test_result.detail
    {"filing_id": "f", "framework": "bank_p3esg", "period": "FY2025", "message": "2 of 132 exposures state no gross carrying amount.", "severity": "blocking"},
    {"check": "Two people can approve", "hint": "Only one person can approve."},
    {"check": "Reporting identity complete", "hint": None},
    {"framework": "—", "period": "—", "note": "Two people can approve"},
    {"framework": "bank_tcfd", "period": "FY2025", "note": "released without an approval request"},
    {"feed": "Copernicus CAMS", "status": "overdue", "last_refresh": "2026-08-02T06:00:00+00:00"},
    {"feed": "ECB rates", "status": "failed", "last_refresh": None},
    {"hazard": "flood", "version": "flood-jrc-v3.0", "r2_oos": 0.31, "gate": 0.4},
    {"framework": "bank_p3esg", "indicator": "Share at risk", "onset_at": "2026-08-24T00:00:00+00:00"},
    {"last_scan": "2026-08-27T00:00:00+00:00", "days_ago": 13},
    {"framework": "bank_tcfd", "period": "FY2025", "due_date": "2026-04-28"},
    *({"note": n} for n in ("No live filing to test against.", "This check does not apply to the organisation's sector.",
                            "Nothing released yet.", "No active model in the registry.", "No open red breach.",
                            "No source scan on record.", "No obligation past its due date.")),
]


@pytest.mark.parametrize("item", STORED_ITEMS)
def test_every_stored_control_item_has_customer_words(item):
    from services.governance.controls import named
    [x] = named([item])
    assert {k: x[k] for k in item} == item, "a stored field changed — the message is added beside them"
    words = [x["msg"]["label"], *x["msg"]["detail"].values()]
    assert all(not messages.INTERNAL.search(w) for w in words), words
    assert not any(re.search(r"\b(framework|period|r2_oos|days_ago|due_date|onset_at|hint|note|check)\s*:", w) for w in words), words


def test_a_control_test_that_could_not_run_never_shows_its_cause():
    from services.governance.controls import item_message
    m = item_message({"note": "could not test: KeyError: 'calibrations_current'"})
    assert m["code"] == "oversight.control.not_tested"
    assert "KeyError" not in str(m) and "calibrations_current" not in str(m)


def test_a_new_test_run_stores_each_items_catalogue_message(monkeypatch):
    """New rows carry the readiness check's and the filing finding's own message; older rows are named by named()."""
    import services.governance.controls as C
    fail = messages.render("horizon.readiness.second_approver.failing")
    ev = {"readiness": {"second_approver": {"key": "second_approver", "label": "Two people can approve", "ok": False, "hint": fail["detail"]["what"],
                                            "message": fail}},
          "findings": {"r": [{"filing_id": "f", "framework": "bank_p3esg", "period": "FY2025", "passed": False, "severity": "warning",
                              "message": "m", "msg": messages.render("error.not_found")}]}}
    assert C._from_readiness(ev, ["second_approver"])[3][0]["msg"]["code"] == "horizon.readiness.second_approver.failing"
    assert C._from_findings(ev, ["r"])[3][0]["msg"]["code"] == "error.not_found"
