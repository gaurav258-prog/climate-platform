"""The control center and the platform pages speak in the catalogue's words (UI standard, 2026-10-16): every refusal and
explanation the server sends Admin, Platform, Tasks, Transmission, Billing, Single sign-on and Approvals is an admin.*
catalogue code, every code those screens show is named, and the defects found on the way stay fixed — a reporting basis
on a scenario the platform does not compute, a decision announced as recorded that was rolled back, identity-provider
addresses typed from the browser, a tenant form offering a sector its request refused. No database."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from core import messages
from core.errors import UserError

ROOT = Path(__file__).resolve().parents[2]
SERVER = sorted(p for d in ("api", "services") for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)


def _admin_codes_in_code() -> tuple[set[str], set[str]]:
    """Every admin.* code the server names: literal codes, and the prefixes of codes it builds (f"admin.x.{...}")."""
    literal, prefixes = set(), set()
    permissions = set(messages.names()["admin.permission"])            # admin.users.manage and the like: not messages
    for p in SERVER:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        parts = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in parts \
                    and n.value not in permissions and re.fullmatch(r"admin(\.[a-z_]+)+", n.value):
                literal.add(n.value)
            elif isinstance(n, ast.JoinedStr) and n.values and isinstance(n.values[0], ast.Constant) \
                    and str(n.values[0].value).startswith("admin."):
                prefixes.add(str(n.values[0].value))
    return literal, prefixes


def test_every_admin_code_the_server_names_is_in_the_catalogue():
    literal, _ = _admin_codes_in_code()
    cat, names = set(messages.catalogue()), set(messages.names())
    missing = sorted(c for c in literal if c not in cat and c not in names)
    assert not missing, f"admin codes the server raises or renders that the catalogue lacks: {missing}"


def test_no_admin_code_sits_unused_in_the_catalogue():
    """A catalogue entry no code path renders is a word nobody reads — it drifts from what the screen says."""
    literal, prefixes = _admin_codes_in_code()
    from services.calc_settings import INTERPRETATION_SCHEMA
    from services.governance.admin_view import SWITCH_CODE
    switches = {f"admin.switch.{SWITCH_CODE.get(k, k)}" for k in INTERPRETATION_SCHEMA}
    unused = sorted(c for c in messages.catalogue() if c.startswith("admin.") and c not in literal and c not in switches
                    and not any(c.startswith(p) for p in prefixes))
    assert not unused, f"admin catalogue codes no server code renders: {unused}"


def test_every_methodology_choice_has_its_words_and_every_option_a_name():
    from services.calc_settings import INTERPRETATION_SCHEMA
    from services.governance.admin_view import switch_code, switch_view
    for key, spec in INTERPRETATION_SCHEMA.items():
        assert switch_code(key) in messages.catalogue(), f"{key}: no catalogue explanation"
        v = switch_view({"key": key, **spec})                     # an unnamed option raises
        assert v["name"] and not messages.INTERNAL.search(v["name"]), key
        for o in v["options"]:
            assert o["label"] and not messages.INTERNAL.search(o["label"]), (key, o)


def test_a_reporting_basis_on_a_scenario_the_platform_does_not_compute_is_refused():
    """The editor offered 'RCP 4.5 / RCP 8.5' and 2040 and the server stored any string: every figure on that basis would
    have come back empty. The choices are now the platform's own, and anything else is refused."""
    from core.types import SCENARIO_VALUES, TIME_HORIZON_VALUES
    from services.governance.admin_view import basis_options, check_basis
    opts = basis_options()
    assert [o["value"] for o in opts["scenario"]] == list(SCENARIO_VALUES)
    assert [o["value"] for o in opts["horizon"]] == list(TIME_HORIZON_VALUES)
    for bad, code in (({"scenario": "rcp85"}, "admin.basis.bad_scenario"), ({"horizon": "2040"}, "admin.basis.bad_horizon")):
        with pytest.raises(UserError) as refused:
            check_basis(bad)
        assert refused.value.code == code
    for s in SCENARIO_VALUES:
        for h in TIME_HORIZON_VALUES:
            check_basis({"scenario": s, "horizon": h})


def test_web_offers_no_scenario_list_of_its_own():
    for f in ("web/src/pages/admin/Basis.tsx", "web/src/pages/admin/Supervision.tsx"):
        src = (ROOT / f).read_text(encoding="utf-8")
        assert not re.search(r"'rcp\d\d'|'hot_house_3_5c'|'orderly_1_5c'|\['current', '2030'", src), f"{f} types its own scenario list"


def test_these_pages_open_overlays_only_through_the_shared_dialog_and_drawer():
    """The mentions list on Tasks was a hand-made full-screen layer (no focus trap, no Escape); it is a Drawer now."""
    pages = [ROOT / "web/src/pages" / f"{n}.tsx" for n in
             ("Admin", "Platform", "Tasks", "Transmission", "Billing", "SingleSignOn", "Login", "Approvals")]
    pages += sorted((ROOT / "web/src/pages/admin").glob("*.tsx")) + sorted((ROOT / "web/src/pages/tasks").glob("*.tsx"))
    pages += [ROOT / "web/src/components" / f"{n}.tsx" for n in ("ClientRates", "MethodParameters")]
    for f in pages:
        assert "fixed inset-0" not in f.read_text(encoding="utf-8"), f"{f.relative_to(ROOT)} hand-makes an overlay"


def test_a_decision_that_could_not_be_applied_says_it_was_not_recorded():
    """The session rolls the whole decision back when its change cannot be applied; the words said 'Decision recorded,
    but …'. They now say it was not recorded and the request is still waiting."""
    from api.routers.approvals import _not_applied
    out = _not_applied(RuntimeError("database said no")).body()["error"]
    assert out["error"] == "admin.approvals.not_applied"
    assert out["message"] == "Decision not recorded" and "still waiting" in out["detail"]["what"]
    src = (ROOT / "api" / "routers" / "approvals.py").read_text(encoding="utf-8")
    assert "Decision recorded, but" not in src and "Approved, but" not in src


def test_the_session_rolls_back_on_an_error_so_a_refused_decision_leaves_nothing():
    """What the not-recorded words rest on: the request's session commits only when the route returns."""
    src = (ROOT / "core" / "db" / "session.py").read_text(encoding="utf-8")
    body = src[src.index("def get_session"):]
    assert re.search(r"yield session\s+session\.commit\(\)\s+except Exception:\s+session\.rollback\(\)", body)


def test_the_identity_provider_is_given_the_addresses_a_sign_in_is_checked_against():
    """The screen typed window.location.origin + a path; the SAML audience and recipient and the OIDC redirect are built
    from the platform's configured address. The screen now shows the server's own."""
    from api.routers.sso_scim import _addresses
    from services.governance import saml, sso
    a = _addresses()
    assert a["acs"] == saml.acs_url() and a["sp_entity_id"] == saml.sp_entity_id() and a["redirect"] == sso.redirect_uri()
    src = (ROOT / "web" / "src" / "pages" / "SingleSignOn.tsx").read_text(encoding="utf-8")
    assert "window.location.origin" not in src


def test_the_tenant_form_offers_only_sectors_its_request_accepts():
    """The form listed every VALID_ORG_TYPES entry (supervisory authority included) while the request's pattern refused a
    regulator — a provisioning that could only fail."""
    from api.routers.admin import TenantCreate
    from services.governance.tenant_provisioning import VALID_ORG_TYPES
    for t in VALID_ORG_TYPES:
        TenantCreate(name="A tenant", org_type=t)
        assert messages.names()["admin.sector"].get(t), f"sector {t} has no name"


def test_a_supervisory_body_is_told_the_roles_it_actually_gets():
    from services.governance.tenant_provisioning import role_templates_for
    src = (ROOT / "services" / "governance" / "tenant_provisioning.py").read_text(encoding="utf-8")
    assert '"roles": list(DEFAULT_ROLE_PERMS.keys())' not in src and '"roles": list(templates)' in src
    from services.governance.admin_view import role_label
    for t in ("bank", "regulator"):
        for r in role_templates_for(t):
            assert role_label(r)


def test_every_role_template_permission_and_policy_action_is_named():
    from services.governance.tenant_provisioning import role_templates_for
    perms = {p for t in ("bank", "insurer", "asset_manager", "reit", "manufacturer", "regulator")
             for ps in role_templates_for(t).values() for p in ps}
    perms |= {p for ps in role_templates_for("bank", plan="respondent").values() for p in ps}
    names = messages.names()
    assert not sorted(p for p in perms if p not in names["admin.permission"])
    assert not sorted({p.split(".")[0] for p in perms} - set(names["admin.permission_area"]))
    from services.governance.admin_view import policy_actions
    assert policy_actions() == {"supply.site.update", "supply.site.delete", "supply.plot.update", "supply.plot.delete",
                                "config.reporting_settings", "config.calc_settings", "config.kri_appetite", "risk.decision"}


def test_every_task_event_the_service_writes_has_its_words():
    from services.governance.tasks import event_words
    src = (ROOT / "services" / "governance" / "tasks.py").read_text(encoding="utf-8")
    kinds = set(re.findall(r'_event\(session, [^,]+, "([a-z_]+)"', src))
    assert kinds >= {"created", "moved", "assigned", "edited", "commented", "attached", "removed_attachment", "completion_requested"}
    for k in kinds:
        w = event_words({"kind": k, "from": "todo", "to": "doing", "note": "x.txt"})
        assert w["code"] != "admin.tasks.event.other", f"task event '{k}' has no words of its own"
    for note in ("gate confirmed · An owner is assigned", "4-eyes approved · Filed", "system:supervision_engagement · closed"):
        assert not messages.INTERNAL.search(event_words({"kind": "moved", "from": "review", "to": "done", "note": note})["label"])


def test_every_step_the_transmission_follow_up_writes_is_named():
    from services.governance.transmission import thread_words
    src = (ROOT / "services" / "transmission" / "service.py").read_text(encoding="utf-8")
    block = src[src.index("msg = {"):src.index("}.get(st, st)")]
    for body in re.findall(r'"\w+": f?"([^"]+)"', block):
        w = thread_words("Tellumen transmission", body)
        assert w["code"] != "admin.transmission.thread.other", f"the follow-up's '{body}' has no words"
    assert thread_words("system", "Stage moved: ready → submitted.")["label"] == "Moved from Ready to submit to Submitted"
    assert thread_words("Us", "Our answer") is None                         # a person's message stays as written


def test_the_hazard_bands_have_one_set_of_names():
    """names.admin.band (the stated-method axes) says what every screen says (web/src/lib/hazards.ts BUCKET_LABEL)."""
    src = (ROOT / "web" / "src" / "lib" / "hazards.ts").read_text(encoding="utf-8")
    web = dict(re.findall(r"(\w+): '([^']+)'", src[src.index("BUCKET_LABEL"):src.index("\n", src.index("BUCKET_LABEL"))]))
    assert messages.names()["admin.band"] == web


def test_a_refused_rate_row_comes_back_as_a_catalogue_message():
    src = (ROOT / "services" / "reference" / "client_fx.py").read_text(encoding="utf-8")
    sub = src[src.index("def submit"):src.index("def latest_rates")]
    assert '"reason": str(e)' not in sub and "MoneyError(\"" not in sub
    for row in ("currency", "date", "rate", "basis", "period"):
        assert f"admin.rates.row.{row}" in messages.catalogue()


def test_a_request_value_reads_as_a_number_not_in_scientific_notation():
    from services.governance.approval_view import _value
    assert _value("value_num", 123500.0) == "123,500" and _value("value_num", 0.05) == "0.05"
    assert _value("value_at_risk_eur", 1166700000) == "1,166,700,000 EUR" and _value("n_assets", 129) == "129"
