"""CRCS version pinning: every filing records the regulation version it is prepared under, from the EU register.

  * current — nothing replaces the act for the period; amendments in force by the period end are listed
  * successor_in_force — an act that repeals it (in whole or in part) is in force for the period: flagged for review
  * superseded — the register says the act ended before the period did; legacy support runs six months past the end
  * a relation a reviewer dismissed does not count; a register date that contradicts itself is reported, not acted on
  * the first scan of an act records existing amendments quietly; a replacing act is raised even then; later new
    relations are raised
  * a freeze stamps the version into the hash-verified payload and warns on the run when it is not current
Runs inside a rolled-back transaction; the register is simulated where a scan is exercised."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from services.governance import reg_versions as V
from services.regulatory_monitoring import eurlex_detector as D
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


def _snap(s, celex, eov="9999-12-31", in_force=True):
    sig = {"celex": celex, "in_force": in_force, "end_of_validity": eov, "entry_into_force": ["2023-01-08"], "doc_date": "2022-11-30"}
    s.execute(text("""INSERT INTO reg_source_snapshot (celex, framework, fingerprint, signal) VALUES (:c, 'bank_p3esg', 'x', CAST(:s AS jsonb))
                      ON CONFLICT (celex) DO UPDATE SET signal = EXCLUDED.signal"""), {"c": celex, "s": json.dumps(sig)})


def _rel(s, celex, related, relation, eif):
    s.execute(text("""INSERT INTO reg_act_relation (celex, related_celex, relation, title, entry_into_force, in_force)
                      VALUES (:c, :r, :k, :t, CAST(:e AS jsonb), TRUE)
                      ON CONFLICT (celex, related_celex, relation) DO UPDATE SET entry_into_force = EXCLUDED.entry_into_force"""),
              {"c": celex, "r": related, "k": relation, "t": f"Commission Implementing Regulation (EU) {related[1:5]}/{related[6:]} of 1 January laying down",
               "e": json.dumps(eif)})


@pytest.fixture()
def s(session_rolled_back):
    session_rolled_back.execute(text("DELETE FROM reg_act_relation WHERE celex = '32022R2453'"))
    return session_rolled_back


def test_current_with_amendments(s):
    _snap(s, "32022R2453")
    _rel(s, "32022R2453", "32099R0001", "amends", ["2024-06-01"])
    _rel(s, "32022R2453", "32099R0002", "amends", ["2030-01-01"])                  # not yet in force for the period
    v = V.version_for(s, "bank_p3esg", "2025-12-31")
    assert v["status"] == "current" and [a["celex"] for a in v["amended_by"]] == ["32099R0001"]
    assert v["amended_by"][0]["title"] == "Commission Implementing Regulation (EU) 2099/0001"      # shortened to the act


def test_a_replacing_act_in_force_flags_review_and_an_ended_act_is_superseded(s):
    _snap(s, "32022R2453", eov="2026-12-30")
    _rel(s, "32022R2453", "32024R3172", "implicitly_repeals", ["2025-01-01", "2025-01-20"])
    fy25 = V.version_for(s, "bank_p3esg", "2025-12-31")
    assert fy25["status"] == "successor_in_force" and fy25["replaced_by"][0]["celex"] == "32024R3172"
    assert fy25["replaced_by"][0]["title"] == "Commission Implementing Regulation (EU) 2024/3172"
    fy26 = V.version_for(s, "bank_p3esg", "2026-12-31")
    assert fy26["status"] == "superseded" and fy26["supported_until"] == "2027-07-01"
    fy24 = V.version_for(s, "bank_p3esg", "2024-12-31")
    assert fy24["status"] == "current"                                              # the successor came later


def test_a_dismissed_relation_does_not_count_and_a_contradiction_is_reported(s):
    _snap(s, "32022R2453", eov="2019-01-12", in_force=True)                          # in force, yet 'ended' in the past
    _rel(s, "32022R2453", "32016L2341", "implicitly_repeals", ["2017-01-12"])
    s.execute(text("""INSERT INTO reg_detected_change (framework, celex, title, summary, status)
                      VALUES ('bank_p3esg', '32016L2341', 't', 's', 'dismissed')"""))
    v = V.version_for(s, "bank_p3esg", "2025-12-31")
    assert v["status"] == "current" and v["replaced_by"] == [] and "not acted on" in v["notes"][0]


def test_first_scan_is_a_quiet_baseline_but_a_replacement_is_always_raised(s, monkeypatch):
    registry = {"32022R2453": [{"related_celex": "32099R0009", "relation": "amends", "entry_into_force": ["2024-01-01"], "in_force": True, "title": "A"},
                               {"related_celex": "32099R0010", "relation": "implicitly_repeals", "entry_into_force": ["2025-01-01"], "in_force": True, "title": "B"}]}
    monkeypatch.setattr(D, "_query_relations", lambda cx, timeout=40.0: registry.get(cx, []))
    monkeypatch.setattr(s, "commit", s.flush)
    before = s.execute(text("SELECT count(*) FROM reg_detected_change WHERE celex LIKE '32099R%'")).scalar()
    first = D.scan_relations(s)
    raised = {r[0] for r in s.execute(text("SELECT celex FROM reg_detected_change WHERE celex LIKE '32099R%'")).all()}
    assert raised == {"32099R0010"} and first["new_relations"] == [("32022R2453", "32099R0010", "implicitly_repeals")]
    assert s.execute(text("SELECT 1 FROM reg_act_relation WHERE related_celex = '32099R0009'")).first()   # kept as baseline
    registry["32022R2453"].append({"related_celex": "32099R0011", "relation": "amends", "entry_into_force": ["2026-01-01"], "in_force": True, "title": "C"})
    D.scan_relations(s)
    raised = {r[0] for r in s.execute(text("SELECT celex FROM reg_detected_change WHERE celex LIKE '32099R%'")).all()}
    assert "32099R0011" in raised and "32099R0009" not in raised and before == 0


def test_a_freeze_stamps_the_version_and_warns_when_it_is_not_current(s):
    from services.governance.report_snapshots import create_snapshot
    _snap(s, "32022R2453", eov="2026-12-30")
    _rel(s, "32022R2453", "32024R3172", "implicitly_repeals", ["2025-01-01"])
    snap = create_snapshot(s, BANK_ORG, "bank_p3esg", None)
    reg = s.execute(text("SELECT payload->'_regulation' FROM report_snapshots WHERE snapshot_id = CAST(:i AS uuid)"),
                    {"i": snap["snapshot_id"]}).scalar()
    assert reg["framework"] == "bank_p3esg" and snap["reporting_basis"]["regulation_status"] == reg["status"]
    chk = next(c for c in snap["run_checks"] if c["key"] == "regulation")
    if reg["status"] != "current":
        assert chk["status"] == "warn" and "2024/3172" in chk["detail"]
