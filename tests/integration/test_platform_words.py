"""Through the HTTP API: sign-in, sessions, passkeys, password reset, onboarding links and the go-live checklist refuse
and explain in catalogue words, and a sign-in refusal never says whether an account exists (E-next: the passkey
sign-in answered 'no such account' for an unknown e-mail and 'unknown passkey' for a known one)."""
from __future__ import annotations

import pytest

from core import messages
from tests.integration.conftest import login

pytestmark = pytest.mark.integration


def _code(r) -> str:
    return r.json()["error"]["error"]


def _words(r) -> str:
    e = r.json()["error"]
    return " ".join([e["message"], *(e.get("detail") or {}).values()])


def test_a_request_without_a_valid_session_is_refused_in_words(api):
    assert (r := api.get("/v1/auth/me")).status_code == 401 and _code(r) == "platform.access.signed_out"
    r = api.get("/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401 and _code(r) == "platform.access.session_expired"
    r = api.get("/v1/auth/me", headers={"Authorization": "Bearer cp_live_" + "0" * 32})
    assert r.status_code == 401 and _code(r) == "platform.access.needs_sign_in"
    r = api.post("/v1/auth/refresh", json={"refresh_token": "rt_not-a-token"})
    assert r.status_code == 401 and _code(r) == "platform.access.session_expired"
    for r in (api.get("/v1/auth/me"), api.post("/v1/auth/refresh", json={"refresh_token": "x"})):
        assert not messages.INTERNAL.search(_words(r))


def test_a_refused_permission_names_the_permission(api):
    analyst = login(api, "analyst@meridian.demo", "Demo!analyst1")
    r = api.get("/v1/security/access-review", headers=analyst)
    assert r.status_code == 403 and _code(r) == "platform.access.missing_permission"
    assert messages.names()["admin.permission"]["admin.users.manage"] in _words(r)
    assert "admin.users.manage" not in r.text


def test_the_password_sign_in_keeps_the_codes_the_sign_in_screen_branches_on(api):
    """A wrong password and an unknown e-mail get the same refusal (invalid_credentials), as before."""
    known = api.post("/v1/auth/login", json={"email": "analyst@meridian.demo", "password": "not-the-password"})
    unknown = api.post("/v1/auth/login", json={"email": "nobody@nowhere.demo", "password": "not-the-password"})
    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json() and _code(known) == "invalid_credentials"


def test_a_passkey_sign_in_refusal_never_says_whether_the_account_exists(api):
    cred = {"id": "not-a-credential", "rawId": "not-a-credential", "type": "public-key", "response": {}}
    unknown = api.post("/v1/auth/passkey/login/verify", json={"email": "nobody@nowhere.demo", "credential": cred})
    known = api.post("/v1/auth/passkey/login/verify", json={"email": "analyst@meridian.demo", "credential": cred})
    assert unknown.status_code == known.status_code == 401
    assert unknown.json() == known.json() and _code(known) == "platform.passkey.failed"
    a = api.post("/v1/auth/passkey/login/options", json={"email": "nobody@nowhere.demo"})
    b = api.post("/v1/auth/passkey/login/options", json={"email": "analyst@meridian.demo"})
    if b.status_code == 404:                      # the demo analyst has no passkey: the same answer as no account
        assert a.json() == b.json() and _code(a) == "platform.passkey.none"


def test_expired_links_are_refused_in_words(api):
    r = api.get("/v1/auth/password/reset/not-a-token")
    assert r.status_code == 404 and _code(r) == "platform.reset.link_invalid"
    r = api.post("/v1/auth/password/reset/not-a-token", json={"password": "a-long-enough-password"})
    assert r.status_code == 400 and _code(r) == "platform.reset.link_invalid"
    r = api.get("/v1/onboarding/form/not-a-token")
    assert r.status_code == 404 and _code(r) == "platform.onboarding.form_link_invalid"
    r = api.get("/v1/onboarding/activate/not-a-token")
    assert r.status_code == 404 and _code(r) == "platform.onboarding.activation_link_invalid"
    r = api.post("/v1/onboarding/activate/not-a-token/password", json={"password": "a-long-enough-password"})
    assert r.status_code == 400 and _code(r) == "platform.onboarding.activation_link_invalid"


def test_sign_up_refuses_in_words(api):
    r = api.post("/v1/signup", json={"company_name": "Words Test Co", "org_type": "bank", "country": "IE",
                                     "admin_email": "not-an-email", "password": "a-long-enough-password"})
    assert r.status_code == 400 and _code(r) == "platform.signup.bad_email"
    assert not messages.INTERNAL.search(_words(r))


def test_the_go_live_checklist_speaks_in_words(api):
    admin = login(api, "admin@meridian.demo", "Demo!admin1")
    d = api.get("/v1/admin/onboarding", headers=admin).json()
    assert d["available"] and [p["key"] for p in d["phases"]] == ["provision", "load", "govern"]
    for s in d["steps"]:
        assert s["title"] == s["about"]["label"] and s["message"]["label"]
        words = " ".join([s["title"], s["message"]["label"], *s["message"]["detail"].values(), *s["about"]["detail"].values()])
        assert not messages.INTERNAL.search(words), (s["key"], words)


def test_the_feed_register_the_control_center_reads_is_in_words(api):
    admin = login(api, "admin@meridian.demo", "Demo!admin1")
    feeds = api.get("/v1/admin/data-feeds", headers=admin).json()["feeds"]
    assert feeds
    for f in feeds:
        assert f["name"] == f["message"]["label"] and not messages.INTERNAL.search(f["name"] + " " + f["note"]), f["key"]


def test_an_intake_names_its_sector_status_and_people(session_rolled_back):
    """What the client-intake screen shows beside each code (client_onboarding._named / _roster / provisioning)."""
    from services.governance import client_onboarding as ob
    s = session_rolled_back
    made = ob.create_intake(s, actor_user_id=None, actor_org_id=None, company_name="Words Intake Test Co",
                            org_type="asset_manager", contact_email="ops@words-intake.test", region="EU")
    ob.submit_intake_form(s, made["form_token"], {"country": "IE", "region": "EU", "roster": [
        {"email": "admin@words-intake.test", "role": "admin"}, {"email": "viewer@words-intake.test", "role": "viewer"}]})
    d = ob.get_intake(s, made["intake_id"])
    assert d["org_type_label"] == "Asset manager" and d["status_label"] == "Completed by the client"
    assert {m["role_label"] for m in d["roster"]} == {"Administrator", "Viewer"}
    listed = next(r for r in ob.list_intakes(s) if str(r["intake_id"]) == made["intake_id"])
    assert listed["org_type_label"] == "Asset manager" and listed["status_label"]
    done = ob.provision_from_intake(s, actor_user_id=None, intake_id=made["intake_id"])
    assert {u["role_label"] for u in done["users"]} == {"Administrator", "Viewer"}
