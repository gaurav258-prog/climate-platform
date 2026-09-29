"""Spec sign-off and the filing's record of its specification (change route, step 7).

  * two different people, one per role; the database refuses the same person twice on one file
  * a sign-off is for the file's exact bytes: a stale hash is refused, and an edited file voids earlier sign-offs
  * a Pillar 3 filing freezes the governing spec (version + sha) and its run says whether that file is signed off
  * version pinning: 2024/3172 replacing 2022/2453 is the lineage moving on, not an alarm
Runs inside a rolled-back transaction (sign-offs are append-only; nothing here may persist)."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

import services.regspec as R
from services.regspec import signoff as S
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


FW, V = "signoff_test", "its_2024_3172"      # a private copy of a spec: live sign-offs can never affect these tests


@pytest.fixture()
def s(session_rolled_back, tmp_path, monkeypatch):
    d = json.loads((R.ROOT / "bank_p3esg" / f"{V}.json").read_text())
    d.update(framework=FW, status="draft")          # draft: no implementation binding is needed to sign it
    (tmp_path / FW).mkdir()
    (tmp_path / FW / f"{V}.json").write_text(json.dumps(d))
    monkeypatch.setattr(R, "ROOT", tmp_path)
    return session_rolled_back


def _uid(s, email):
    return s.execute(text("SELECT user_id::text FROM users WHERE email = :e"), {"e": email}).scalar()


def test_two_different_people_approve_the_exact_file(s):
    spec = R.load(FW, V)
    a, b = _uid(s, "admin@meridian.demo"), _uid(s, "approver@meridian.demo")
    with pytest.raises(S.SignoffError, match="changed since you reviewed"):
        S.sign(s, FW, V, "regulatory", a, "0" * 64)
    st = S.sign(s, FW, V, "regulatory", a, spec["_sha256"])
    assert st["needs"] == ["engineering"] and not st["approved"]
    with pytest.raises(S.SignoffError, match="different person"):
        S.sign(s, FW, V, "engineering", a, spec["_sha256"])
    assert S.sign(s, FW, V, "engineering", b, spec["_sha256"])["approved"]


def test_an_edited_file_voids_earlier_signoffs(s):
    a = _uid(s, "admin@meridian.demo")
    s.execute(text("""INSERT INTO regspec_signoff (framework, version, sha256, role, user_id)
                      VALUES (:fw, :v, :h, 'regulatory', CAST(:u AS uuid))"""), {"fw": FW, "v": V, "h": "f" * 64, "u": a})
    st = S.status(s, FW, V)
    assert not st["approved"] and len(st["voided_by_edit"]) == 1 and "regulatory" in st["needs"]


def test_signoffs_are_append_only(s):
    a = _uid(s, "admin@meridian.demo")
    S.sign(s, FW, V, "regulatory", a, R.load(FW, V)["_sha256"])
    with pytest.raises(Exception, match="append-only"):
        with s.begin_nested():
            s.execute(text("DELETE FROM regspec_signoff WHERE framework = 'signoff_test'"))


def test_a_pillar3_filing_freezes_its_spec_and_the_run_checks_the_signoff(session_rolled_back):
    s = session_rolled_back                          # the real specs
    from services.governance import filings as F
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_p3esg' "
              "AND status NOT IN ('superseded', 'withdrawn')"),
              {"o": BANK_ORG})
    token = F.preflight(s, BANK_ORG, "bank", "bank_p3esg")["confirm_token"]
    fid = F.generate_filing(s, BANK_ORG, "bank", "bank_p3esg", _uid(s, "admin@meridian.demo"), confirm_token=token)["filing_id"]
    row = s.execute(text("""SELECT rs.payload->'_spec' AS spec, er.checks FROM regulatory_filing rf
                            JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
                            JOIN engine_runs er ON er.run_id = rs.run_id WHERE rf.filing_id = CAST(:f AS uuid)"""),
                    {"f": fid}).mappings().first()
    spec = row["spec"] if isinstance(row["spec"], dict) else json.loads(row["spec"])
    gov = R.governing("bank_p3esg", period_end="2025-12-31")
    assert spec["version"] == gov["version"] and spec["sha256"] == gov["_sha256"]
    checks = row["checks"] if isinstance(row["checks"], list) else json.loads(row["checks"])
    chk = next(c for c in checks if c["key"] == "specification")
    assert chk["status"] == ("pass" if spec["approved"] else "warn")


def test_the_2024_act_replacing_2022_is_lineage_not_an_alarm(session_rolled_back):
    s = session_rolled_back                          # the real specs
    from services.governance.reg_versions import version_for
    r = version_for(s, "bank_p3esg", "2025-12-31")
    assert r["status"] == "current" and "32024R3172" in r["label"] and "32022R2453" not in r["label"]
    assert r["lineage"] and r["lineage"][0]["replaced"] == "32022R2453"
    assert "32022R2453" in version_for(s, "bank_p3esg", "2024-06-30")["label"]


def test_a_sole_reviewer_signs_both_roles_only_by_declaring_it(s):
    spec = R.load(FW, V)
    a = _uid(s, "admin@meridian.demo")
    with pytest.raises(S.SignoffError, match="after signing the first yourself"):
        S.sign(s, FW, V, "regulatory", a, spec["_sha256"], sole_reviewer=True)
    S.sign(s, FW, V, "regulatory", a, spec["_sha256"])
    with pytest.raises(S.SignoffError, match="declare it"):
        S.sign(s, FW, V, "engineering", a, spec["_sha256"])
    st = S.sign(s, FW, V, "engineering", a, spec["_sha256"], sole_reviewer=True)
    assert st["approved"] and st["one_person"]
    assert "not a four-eyes review" in next(g["note"] for g in st["signed"] if g["role"] == "engineering")
