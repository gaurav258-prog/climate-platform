"""Issuers' real sites from public registers (the product owner's decisions of 2026-10-23). Rolled back throughout.

  record      a register site is written once per issuer, register and register id, with weight 'not stated' (0) — the
              schema refuses a register site carrying a weight
  look-through an issuer whose located sites all come from registers is named 'sites located, shares of value not
              stated' — never a share; a register site joins the issuers' sites book like any site
  review      an EEA name match waits for a person: confirmed, it becomes the issuer's site (match 'reviewed_name'),
              audited; a decided proposal is never decided again"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.loss import lookthrough
from services.reference import register_matching as M
from services.reference import register_sites as R
from tests.integration.test_loss_engine import LAT, LON
from tests.integration.test_loss_lookthrough import _holding, _manager

pytestmark = pytest.mark.integration


def _site(issuer_id: str, ref: str = "climate_trace:1") -> dict:
    return {"issuer_id": issuer_id, "source": "climate_trace", "source_ref": ref, "name": "Test power plant",
            "facility_type": "electricity-generation", "latitude": LAT, "longitude": LON, "country": "US",
            "owner_share": 0.5, "match_basis": "register_lei",
            "site_facts": {"register": "Climate TRACE", "release": "v5.10.0", "source_id": ref.split(":")[1]}}


def test_a_register_site_is_recorded_once_with_its_weight_not_stated(session_rolled_back):
    s = session_rolled_back
    issuer = s.execute(text("INSERT INTO issuers (name) VALUES ('Register test') RETURNING issuer_id::text")).scalar()
    got = R.record(s, [_site(issuer), _site(issuer)])
    assert (got["added"], got["held"], len(got["cells"])) == (1, 1, 1)
    row = s.execute(text("""SELECT weight_basis, CAST(materiality_weight AS FLOAT) w, CAST(owner_share AS FLOAT) share,
                                   match_basis, site_facts->>'register' reg FROM issuer_facilities
                            WHERE issuer_id = CAST(:i AS uuid)"""), {"i": issuer}).mappings().one()
    assert dict(row) == {"weight_basis": "not_stated", "w": 0.0, "share": 0.5, "match_basis": "register_lei",
                         "reg": "Climate TRACE"}
    with pytest.raises(IntegrityError):
        with s.begin_nested():
            s.execute(text("""INSERT INTO issuer_facilities (issuer_id, name, materiality_weight, weight_basis, source,
                                                             source_ref, match_basis, site_facts)
                              VALUES (CAST(:i AS uuid), 'weighted', 0.5, 'assets', 'climate_trace', 'climate_trace:2',
                                      'register_lei', '{}')"""), {"i": issuer})


def test_an_issuer_located_only_from_registers_has_no_share_and_says_why(session_rolled_back):
    s = session_rolled_back
    org = _manager(s)
    _fund, issuer, _pos = _holding(s, [{"weight_basis": "equal", "w": 1.0, "source": "osm", "type": "hq"}],
                                   isin="US00REGS0001")
    R.record(s, [_site(issuer, "climate_trace:11"), _site(issuer, "climate_trace:12")])
    a = lookthrough.issuers(s, org, [issuer])["issuers"][issuer]
    assert a["share"] is None and a["why"]["code"] == "lookthrough.gap.weights_not_stated"
    register = [x for x in a["sites"] if x["weight_basis"] == "not_stated"]
    assert len(register) == 2 and {x["why"]["code"] for x in register} == {"lookthrough.site.weight_not_stated"}
    held = {x["asset_id"] for x in lookthrough.held_sites(s, org) if x["issuer_id"] == issuer and not x["proxy"]}
    assert len(held) == 2                                            # both join the issuers' sites book


def _candidate(s, issuer: str) -> str:
    M.stage(s, [{"issuer_id": issuer, "register": "eea_ied", "register_ref": "eea_ied:TEST.FACILITY",
                 "register_vintage": "reporting year 2024", "name": "Test works", "latitude": LAT, "longitude": LON,
                 "country": "DE", "owner_named": "Register Test GmbH", "matched_lei": "TESTLEI0000000000001",
                 "matched_name": "REGISTER TEST GMBH", "relation": "consolidated_entity", "rule": M.RULE,
                 "site_facts": {"register": "EEA industrial register (IED / E-PRTR)", "local_id": "TEST.FACILITY"}}])
    return s.execute(text("SELECT candidate_id::text FROM issuer_site_candidates WHERE register_ref = 'eea_ied:TEST.FACILITY'")).scalar()


def test_a_confirmed_name_match_becomes_the_issuer_s_site_and_is_audited(session_rolled_back):
    s = session_rolled_back
    issuer = s.execute(text("INSERT INTO issuers (name) VALUES ('Review test') RETURNING issuer_id::text")).scalar()
    user = s.execute(text("SELECT user_id::text FROM users LIMIT 1")).scalar()
    c = _candidate(s, issuer)
    out = M.decide(s, c, user, None, True, "same company")
    assert out["status"] == "confirmed" and out["facility_id"] and len(out["cells"]) == 1
    f = s.execute(text("""SELECT source, match_basis, weight_basis, site_facts->>'matched_lei' lei FROM issuer_facilities
                          WHERE facility_id = CAST(:f AS uuid)"""), {"f": out["facility_id"]}).mappings().one()
    assert dict(f) == {"source": "eea_ied", "match_basis": "reviewed_name", "weight_basis": "not_stated",
                       "lei": "TESTLEI0000000000001"}
    assert s.execute(text("""SELECT count(*) FROM access_audit_log WHERE action = 'issuer_site.confirm'
                             AND target_id = :c"""), {"c": c}).scalar() == 1
    with pytest.raises(M.DecisionError) as e:
        M.decide(s, c, user, None, False)
    assert e.value.code == "sites.review.error.decided"


def test_a_rejected_name_match_adds_no_site_and_is_never_proposed_again(session_rolled_back):
    s = session_rolled_back
    issuer = s.execute(text("INSERT INTO issuers (name) VALUES ('Reject test') RETURNING issuer_id::text")).scalar()
    user = s.execute(text("SELECT user_id::text FROM users LIMIT 1")).scalar()
    c = _candidate(s, issuer)
    assert M.decide(s, c, user, None, False)["facility_id"] is None
    assert _candidate(s, issuer) == c                                  # staging again leaves the decision as it was
    assert s.execute(text("SELECT status FROM issuer_site_candidates WHERE candidate_id = CAST(:c AS uuid)"),
                     {"c": c}).scalar() == "rejected"
    assert s.execute(text("SELECT count(*) FROM issuer_facilities WHERE issuer_id = CAST(:i AS uuid)"),
                     {"i": issuer}).scalar() == 0
