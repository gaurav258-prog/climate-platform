"""A group filing says what it was consolidated on (E78).

  * the snapshot freezes the rule (quoted), any reading Tellumen declares, and the sha of the rule file;
  * a solo filing carries no consolidation record;
  * the form shows the record with the sign-off of that exact sha — signing later counts for it, editing the file
    afterwards does not change it;
  * the rule file is signed on the same route as a template spec: two roles, the engineering role refused while the
    file fails its checks; it is listed in the spec register.
Runs on the seeded Meridian hierarchy inside a rolled-back transaction (sign-offs are append-only)."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.governance import filings as F
from services.regspec import rules
from services.regspec import signoff as S
from tests.integration.test_filing_currency import _tree
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


def _uid(s, email):
    return s.execute(text("SELECT user_id::text FROM users WHERE email = :e"), {"e": email}).scalar()


def _file(s, framework, entity_id):
    user = _uid(s, "admin@meridian.demo")
    # a live filing of this scope may already exist in the demo data: set it aside inside the rolled-back transaction
    s.execute(text("ALTER TABLE regulatory_filing DISABLE TRIGGER USER"))
    s.execute(text("""UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid)
                      AND framework = :f AND entity_id IS NOT DISTINCT FROM CAST(:e AS uuid)"""),
              {"o": BANK_ORG, "f": framework, "e": entity_id})
    s.execute(text("ALTER TABLE regulatory_filing ENABLE TRIGGER USER"))
    tok = F.preflight(s, BANK_ORG, "bank", framework, entity_id)["confirm_token"]
    return F.generate_filing(s, BANK_ORG, "bank", framework, user, confirm_token=tok, entity_id=entity_id)


def test_a_group_filing_freezes_its_rule_and_the_form_shows_its_signoff(session_rolled_back):
    s = session_rolled_back
    group, _, leasing, _ = _tree(s)
    f = _file(s, "bank_tcfd", group["entity_id"])
    cons = F.get_filing(s, BANK_ORG, f["filing_id"])["snapshot"]["payload"]["_consolidation"]
    sha = rules.load("consolidation", "regimes")["_sha256"]
    assert cons["regime"] == "crr_prudential" and cons["basis"] == "declared"
    assert cons["factors"]["equity"] == "excluded" and cons["refs"][0]["quote"]
    assert cons["declaration"]["reading"] and "confirmed_by" not in cons["declaration"]
    assert cons["rule_file"] == {"framework": "consolidation", "version": "regimes", "sha256": sha}

    view = F.form_view(s, BANK_ORG, f["filing_id"])["consolidation"]
    assert view["signoff"] == {"sha256": sha, "signed": [], "approved": False, "one_person": False}

    a, b = _uid(s, "admin@meridian.demo"), _uid(s, "approver@meridian.demo")
    S.sign(s, "consolidation", "regimes", "regulatory", a, sha)
    S.sign(s, "consolidation", "regimes", "engineering", b, sha)
    view = F.form_view(s, BANK_ORG, f["filing_id"])["consolidation"]
    assert view["signoff"]["approved"] and not view["signoff"]["one_person"]
    assert [g["role"] for g in view["signoff"]["signed"]] == ["regulatory", "engineering"]

    # a sign-off of a later version of the file is not a sign-off of the version this filing was computed on
    assert S.signed_on(s, "consolidation", "regimes", "e" * 64)["signed"] == []

    solo = _file(s, "bank_tcfd", leasing["entity_id"])
    assert "_consolidation" not in F.get_filing(s, BANK_ORG, solo["filing_id"])["snapshot"]["payload"]
    assert F.form_view(s, BANK_ORG, solo["filing_id"])["consolidation"] is None


def test_the_rule_file_cannot_be_signed_by_an_engineer_while_it_fails_its_checks(session_rolled_back, monkeypatch):
    s = session_rolled_back
    sha = rules.load("consolidation", "regimes")["_sha256"]
    monkeypatch.setattr(rules, "check", lambda doc: ["bank_tcfd: a declared reading needs its wording"])
    with pytest.raises(S.SignoffError, match="does not pass its checks"):
        S.sign(s, "consolidation", "regimes", "engineering", _uid(s, "admin@meridian.demo"), sha)


def test_the_rule_file_is_in_the_spec_register(session_rolled_back):
    entry = next(x for x in S.overview(session_rolled_back) if x["framework"] == "consolidation")
    assert entry["version"] == "regimes" and entry["templates"] == [] and entry["coverage"]["complete"]
    assert {i["subject"] for i in entry["interpretations"]} == {
        F.FRAMEWORKS[fw]["label"] for fw in ("bank_tcfd", "reit_tcfd", "assetmgmt_tcfd", "insurer_climate")}
