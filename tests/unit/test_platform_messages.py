"""Sign-in, onboarding, help and the platform server speak the customer's words (UI standard, 2026-10-16): every
refusal they raise and every explanation they send is a catalogue code (platform.*, or a code they reuse), a refused
permission is named, never shown as its code, and the feed register's names and notes come from the catalogue."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from core import messages
from core.errors import UserError

ROOT = Path(__file__).resolve().parents[2]
FILES = ["api/deps.py", "api/routers/auth.py", "api/routers/auth_user.py", "api/routers/passkeys_esign.py",
         "api/routers/security_admin.py", "api/routers/onboarding_intake.py", "api/routers/growth.py",
         "api/services/rbac.py", "services/governance/client_onboarding.py", "services/governance/onboarding.py",
         "services/governance/signup.py", "services/governance/config_governance.py", "services/data/feeds.py"]
ERRORS = {"UserError", "AuthError", "OnboardingError", "SignupError"}


def _raised_codes(path: Path) -> list[tuple[int, str]]:
    out = []
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ERRORS and n.args \
                and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            out.append((n.lineno, n.args[0].value))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("render", "label") \
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "messages" and n.args \
                and isinstance(n.args[0], ast.Constant):
            out.append((n.lineno, n.args[0].value))
    return out


@pytest.mark.parametrize("rel", FILES)
def test_every_code_these_files_send_is_in_the_catalogue(rel):
    cat = messages.catalogue()
    missing = [f"{rel}:{line} {code}" for line, code in _raised_codes(ROOT / rel) if code not in cat]
    assert not missing, missing


@pytest.mark.parametrize("rel", [f for f in FILES if f.startswith("api/")])
def test_no_refusal_is_built_by_hand_in_these_routers(rel):
    """A refusal is a UserError with a catalogue code, never an HTTPException carrying its own sentence — except the
    three sign-in refusals the sign-in screen branches on (api/routers/auth_user.py login)."""
    src = (ROOT / rel).read_text(encoding="utf-8")
    raised = re.findall(r'"error":\s*"([a-z_]+)"', src)
    allowed = {"invalid_credentials", "mfa_required", "mfa_invalid"} if rel.endswith("auth_user.py") else set()
    assert set(raised) <= allowed, set(raised) - allowed
    assert "str(e)" not in src


def test_the_sign_in_screen_still_finds_the_codes_it_branches_on():
    """Login.tsx opens the code field on mfa_required and says the code did not match on mfa_invalid: the login route
    must keep sending those two machine codes, and a wrong e-mail and a wrong password one and the same refusal."""
    login = (ROOT / "web/src/pages/Login.tsx").read_text(encoding="utf-8")
    route = (ROOT / "api/routers/auth_user.py").read_text(encoding="utf-8")
    for code in re.findall(r"code === '([a-z_]+)'", login):
        assert f'"error": "{code}"' in route, code
    assert route.count('"error": "invalid_credentials"') == 1


def test_every_permission_a_route_requires_is_named():
    named = messages.names()["admin.permission"]
    used = {m.group(1) for p in (ROOT / "api").rglob("*.py")
            for m in re.finditer(r'require_permission\(\s*["\']([^"\']+)["\']', p.read_text(encoding="utf-8"))}
    assert used and not used - set(named), sorted(used - set(named))


def test_a_refused_permission_is_named_not_shown_as_its_code():
    """The refusal used to read 'Missing permission: admin.users.manage' — the code itself, on the screen."""
    from api.deps import require_permission
    with pytest.raises(UserError) as refused:
        require_permission("admin.users.manage")({"permissions": ["modules.view"]})
    e = refused.value
    assert e.code == "platform.access.missing_permission" and e.status == 403
    body = e.body()["error"]
    words = " ".join([body["message"], *body["detail"].values()])
    assert messages.names()["admin.permission"]["admin.users.manage"] in words
    assert "admin.users.manage" not in words and not messages.INTERNAL.search(words)


def test_an_unnamed_permission_falls_back_to_the_general_refusal_not_a_code():
    from api.deps import require_permission
    with pytest.raises(UserError) as refused:
        require_permission("not.a.permission")({"permissions": []})
    assert refused.value.code == "error.forbidden"


def test_the_feed_register_names_and_notes_come_from_the_catalogue():
    from services.data import feeds
    src = (ROOT / "services/data/feeds.py").read_text(encoding="utf-8")
    start, end = src.index("FEEDS: list[dict] = ["), src.index("_BY_KEY = ")
    assert not re.search(r'"(?:name|note)":', src[start:end]), "a feed's words are typed into the register again"
    codes = [feeds.words_code(f["key"]) for f in feeds.FEEDS]
    assert len(set(codes)) == len(codes), "two feeds share one entry of words"
    for f in feeds.FEEDS:
        m = messages.render(feeds.words_code(f["key"]))
        assert f["name"] == m["label"] and f["note"] and f["message"]["code"] == m["code"]
        for text in (f["name"], f["note"]):
            assert not messages.INTERNAL.search(text), (f["key"], text)
            assert not re.search(r"\bv\d+(?:\.\d+)*\b|\(E\d+\)|\b[a-z]+_[a-z0-9_]+\b", text), (f["key"], text)


class _Org:
    def __init__(self, row):
        self.row = row

    def execute(self, *_a, **_k):
        return self

    def mappings(self):
        return self

    def first(self):
        return self.row


@pytest.mark.parametrize("org_type", ["bank", "manufacturer"])
@pytest.mark.parametrize("count", [0, 1, 7])
def test_the_go_live_checklist_has_words_for_every_step_and_state(monkeypatch, org_type, count):
    """Each step's title, its meaning and every state it can be in are catalogue messages: run the checklist over an
    empty and a filled workspace of both kinds (counts stubbed), and every line it sends is customer words."""
    from services.governance import onboarding
    monkeypatch.setattr(onboarding, "_scalar", lambda *_a, **_k: count)
    org = {"name": "Demo Org", "type": org_type, "legal_name": "Demo Org SA" if count else None,
           "lei": "5299001DEMO00000000" if count else None, "filing_contact_email": None, "created_at": None}
    d = onboarding.onboarding_status(_Org(org), "00000000-0000-4000-8000-000000000000")
    assert d["available"] and len(d["steps"]) == 10
    assert [p["key"] for p in d["phases"]] == list(onboarding.PHASES)
    for s in d["steps"]:
        assert s["phase"] in onboarding.PHASES and "detail" not in s
        for m in (s["about"], s["message"]):
            words = " ".join([m["label"], *m["detail"].values()])
            assert not messages.INTERNAL.search(words), (s["key"], words)
        assert s["title"] == s["about"]["label"]
    assert "Bank" in d["steps"][0]["message"]["label"] or "Agriculture" in d["steps"][0]["message"]["label"]


def test_the_go_live_checklist_names_a_missing_organisation_in_words():
    from services.governance import onboarding
    d = onboarding.onboarding_status(_Org(None), "00000000-0000-4000-8000-000000000000")
    assert d == {"available": False, "message": messages.render("platform.golive.unavailable")}


def test_config_changes_waiting_for_approval_say_so_in_words():
    """The answer's message is shown as is (web/src/components/FilingBasis.tsx): the catalogue's words, not a sentence
    with '(4-eyes)' typed where it arises."""
    src = (ROOT / "services/governance/config_governance.py").read_text(encoding="utf-8")
    assert '"message": messages.label("platform.config.pending")' in src
    assert not messages.INTERNAL.search(messages.label("platform.config.pending"))


def test_every_intake_status_role_and_sector_the_intake_screen_shows_is_named():
    """The client-intake screen reads org_type_label, status_label and role_label (client_onboarding._named/_roster):
    every status the table allows, every roster role and every sector an intake accepts has a name."""
    from services.governance import client_onboarding as ob
    mig = (ROOT / "core/db/migrations/versions/client_onboarding_20260826.py").read_text(encoding="utf-8")
    statuses = re.search(r"CHECK \(status IN \(('draft'[^)]*)\)\)", mig).group(1)
    for st in re.findall(r"'([a-z_]+)'", statuses):
        assert messages.name("platform.intake_status", st)
    for role in ob.ROSTER_ROLES:
        assert messages.name("role", role)
    assert {s["key"] for s in ob.sectors()} == ob.VALID_ORG_TYPES and all(s["label"] for s in ob.sectors())
