"""The control center and the platform pages, end to end on the demo data (UI standard, 2026-10-16): everything the API
sends these screens as words is customer language, every code in the data is named, and the defects found on the way
stay fixed — a reporting basis on a scenario the platform does not compute, and a decision whose change could not be
applied announced as recorded. Inside one rolled-back transaction."""
from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from core import messages
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
ADMIN, APPROVER = ("admin@meridian.demo", "Demo!admin1"), ("approver@meridian.demo", "Demo!approve1")
WORD_KEYS = re.compile(r"^(label|name|title_label|.+_label|.+_name)$")


def _words(node, path="$"):
    """Every string the screens print as words: a catalogue message's label and detail, and the *_label / *_name /
    label / name fields — never a person's or a source's own text (bodies, notes, file names, e-mails)."""
    if isinstance(node, dict):
        if "label" in node and isinstance(node.get("detail"), dict):
            yield path, node["label"]
            for k, v in node["detail"].items():
                yield f"{path}.detail.{k}", v
        for k, v in node.items():
            if isinstance(v, str) and WORD_KEYS.match(k):
                yield f"{path}.{k}", v
            elif isinstance(v, list) and k.endswith(("_labels", "_names")):
                for i, x in enumerate(v):
                    yield f"{path}.{k}[{i}]", x
            elif isinstance(v, (dict, list)):
                yield from _words(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, x in enumerate(node):
            yield from _words(x, f"{path}[{i}]")


def _clean(payload, where: str):
    bad = [(p, w) for p, w in _words(payload) if isinstance(w, str) and messages.INTERNAL.search(w)]
    assert not bad, f"{where}: internal language sent as words: {bad[:6]}"


def test_every_permission_policy_and_field_in_the_data_is_named(api):
    names = messages.names()
    perms = api.s.execute(text("SELECT code FROM permissions")).scalars().all()
    assert not sorted(p for p in perms if p not in names["admin.permission"]), "a permission has no customer name"
    rows = api.s.execute(text("SELECT DISTINCT action_key, material_fields FROM approval_policy")).mappings().all()
    assert not sorted({r["action_key"] for r in rows} - set(names["admin.policy"])), "an approval-matrix action has no name"
    assert not sorted({f for r in rows for f in (r["material_fields"] or [])} - set(names["admin.field"]))


def test_every_field_an_approval_request_holds_is_named_or_left_out(api):
    """A new kind of request with a new field fails here until the field is named (names.admin.approval_field)."""
    from services.governance.approval_view import _HIDDEN, details, title
    names = messages.names()
    rows = api.s.execute(text("SELECT request_type, title, payload FROM approval_requests")).mappings().all()
    unnamed = set()
    for r in rows:
        for d in details(r["request_type"], r["payload"] or {}):
            assert not messages.INTERNAL.search(d["value"]) or d["label"] in ("Note", "Review note", "Basis", "Reason",
                                                                              "Requester's reason", "Rationale", "File"), (r["request_type"], d)
        for k, v in (r["payload"] or {}).items():
            if _HIDDEN.search(k):
                continue
            if isinstance(v, dict):
                unnamed |= {k2 for k2 in v if k2 not in names["admin.field"] and k2 not in names["admin.approval_field"]
                            and len(k2) > 2 and r["request_type"] != "config.calc_settings"}
            elif k not in names["admin.approval_field"] and r["request_type"] != "config.calc_settings":
                unnamed.add(k)
        for d in details(r["request_type"], r["payload"] or {}):
            assert not messages.INTERNAL.search(d["label"]), (r["request_type"], d)
        t = title(r["title"])
        assert t is None or not messages.INTERNAL.search(t)
    assert not sorted(unnamed), f"request fields with no customer name: {sorted(unnamed)}"


def test_the_control_center_speaks_in_customer_words(api):
    h = _login(api, *ADMIN)
    for path in ("/v1/admin/control-center", "/v1/admin/reporting-settings", "/v1/admin/permissions", "/v1/admin/roles",
                 "/v1/admin/users", "/v1/admin/approval-policy", "/v1/admin/decision-playbook", "/v1/admin/kri-appetite",
                 "/v1/calc-settings/catalog", "/v1/ingest/connection", "/v1/webhooks/events", "/v1/webhooks",
                 "/v1/source-systems", "/v1/provided/catalog?framework=method", "/v1/provided/method/needed",
                 "/v1/intake/fx/client-rates", "/v1/billing", "/v1/sso/config"):
        r = api.get(path, headers=h)
        assert r.status_code == 200, (path, r.text[:200])
        _clean(r.json(), path)
    perms = api.get("/v1/admin/permissions", headers=h).json()
    assert all(p["name"] and p["area"] for p in perms)
    cat = api.get("/v1/calc-settings/catalog", headers=h).json()["interpretation"]
    assert cat and all(s["name"] and s["about"]["detail"]["what"] for s in cat)


def test_a_basis_the_platform_does_not_compute_is_refused_and_nothing_changes(api):
    h = _login(api, *ADMIN)
    before = api.get("/v1/admin/reporting-settings", headers=h).json()
    assert {o["value"] for o in before["options"]["scenario"]} == {"baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c"}
    for body, code in (({"scenario": "rcp85"}, "admin.basis.bad_scenario"), ({"horizon": "2040"}, "admin.basis.bad_horizon")):
        r = api.patch("/v1/admin/reporting-settings", headers=h, json=body)
        assert r.status_code == 422 and r.json()["error"]["error"] == code, r.text
    after = api.get("/v1/admin/reporting-settings", headers=h).json()
    assert (after["scenario"], after["horizon"]) == (before["scenario"], before["horizon"])


def test_a_decision_whose_change_fails_is_not_recorded_and_says_so(api):
    """The route's session commits only when it returns (core.db.session.get_session). This test gives the route a
    session that behaves the same — a savepoint undone on an error — then approves a completion request whose task has
    left Review: the change cannot be applied, the answer says the decision was not recorded, and the request is still
    waiting."""
    from api.deps import db_session
    from api.main import app
    s = api.s

    def like_production():
        sp = s.begin_nested()
        try:
            yield s
            sp.commit()
        except Exception:
            sp.rollback()
            raise
    maker, checker = _login(api, *ADMIN), _login(api, *APPROVER)
    t = api.post("/v1/reg-tasks", headers=maker, json={"title": "Not-recorded decision (test)", "criticality": "normal"}).json()
    tid = t["task_id"]
    me = s.execute(text("SELECT user_id::text FROM users WHERE email = :e"), {"e": ADMIN[0]}).scalar()
    assert api.post(f"/v1/reg-tasks/{tid}/assign", headers=maker, json={"assignee_user_id": me}).status_code == 200
    assert api.post(f"/v1/reg-tasks/{tid}/move", headers=maker, json={"status": "doing", "attestations": ["ready"]}).status_code == 200
    assert api.patch(f"/v1/reg-tasks/{tid}", headers=maker, json={"description": "Work recorded."}).status_code == 200
    assert api.post(f"/v1/reg-tasks/{tid}/move", headers=maker, json={"status": "review", "attestations": ["complete"]}).status_code == 200
    assert api.post(f"/v1/reg-tasks/{tid}/request-completion", headers=maker, json={"note": "Filed."}).status_code == 201
    rid = s.execute(text("SELECT request_id::text FROM approval_requests WHERE payload->>'task_id' = :t"), {"t": tid}).scalar()
    assert api.post(f"/v1/reg-tasks/{tid}/move", headers=maker, json={"status": "doing"}).status_code == 200   # left Review
    app.dependency_overrides[db_session] = like_production
    try:
        r = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved"})
    finally:
        app.dependency_overrides.pop(db_session, None)
    assert r.status_code == 409 and r.json()["error"]["error"] == "admin.approvals.not_applied", r.text
    assert "not recorded" in r.json()["error"]["detail"]["what"]
    assert s.execute(text("SELECT status FROM approval_requests WHERE request_id = CAST(:r AS uuid)"), {"r": rid}).scalar() == "pending"
    assert s.execute(text("SELECT status FROM regulatory_task WHERE task_id = CAST(:t AS uuid)"), {"t": tid}).scalar() == "doing"


def test_tasks_approvals_and_transmission_speak_in_customer_words(api):
    h = _login(api, *ADMIN)
    board = api.get("/v1/reg-tasks/board", headers=h).json()
    tasks = [t for c in board["columns"] for t in c["tasks"]]
    for t in tasks[:12]:
        d = api.get(f"/v1/reg-tasks/{t['task_id']}", headers=h).json()
        assert all(e["words"]["label"] for e in d["events"])
        # a file's own name (attached / removed) is the person's word, not the platform's
        _clean({"events": [e["words"] for e in d["events"] if e["kind"] not in ("attached", "removed_attachment")]}, f"task {t['task_id']}")
    r = api.get("/v1/approvals", headers=h).json()
    assert r and all(x["status_label"] for x in r)
    _clean([{"details": x["details"], "title_label": x["title_label"], "status_label": x["status_label"]} for x in r], "approvals")
    for path in ("/v1/transmission/cases", "/v1/transmission/sends", "/v1/transmission/channels"):
        body = api.get(path, headers=h).json()
        _clean(body, path)
    for c in api.get("/v1/transmission/cases", headers=h).json()["cases"][:5]:
        case = api.get(f"/v1/transmission/cases/{c['case_id']}", headers=h).json()
        _clean([m["words"] for m in case["messages"] if m["words"]], f"case {c['case_id']}")


def test_the_platform_operator_views_speak_in_customer_words(api):
    from api.routers.admin import tenants_catalog
    from api.routers.ops_console import support_queue, tenant, tenants
    ctx = {"user": {"id": None, "email": "operator@test"}, "permissions": ["platform.admin"], "org": {"org_id": None}}
    t = tenants(api.s, ctx)
    assert all(x["type_label"] for x in t["tenants"])
    _clean(t, "tenants")
    _clean(tenant(t["tenants"][0]["org_id"], api.s, ctx), "tenant")
    _clean(support_queue(api.s, ctx, status="all"), "support")
    cat = tenants_catalog(ctx)
    assert set(cat["sector_names"]) == set(cat["org_types"]) and all(cat["offering_names"].values())


def test_every_kind_of_approval_request_has_a_customer_name(api):
    """The queue names a request by its kind (web/src/lib/actionLabels.ts); nine kinds in the data had no name and showed
    as 'Provided · datapoint', 'Calibration · publish'. A new kind fails here until it is named."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] / "web" / "src" / "lib" / "actionLabels.ts").read_text(encoding="utf-8")
    named = set(re.findall(r"'([a-z_]+(?:\.[a-z_]+)+)':", src))
    kinds = set(api.s.execute(text("SELECT DISTINCT request_type FROM approval_requests")).scalars())
    assert not sorted(kinds - named), f"request kinds with no customer name: {sorted(kinds - named)}"
